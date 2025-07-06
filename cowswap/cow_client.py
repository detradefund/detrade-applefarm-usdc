import requests
from datetime import datetime, timezone
import sys
from pathlib import Path
import os
from dotenv import load_dotenv
import json
from decimal import Decimal
import time

"""
CoW Protocol (CoW Swap) API client.
Handles token price discovery and quote fetching for EURC conversions.
Used by balance managers to value non-EURC assets.
"""

# Add parent directory to PYTHONPATH
sys.path.append(str(Path(__file__).parent.parent))

from config.networks import NETWORK_TOKENS
from utils.retry import APIRetry

# Load environment variables
load_dotenv()

# Zero address for price quotes
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

def get_quote(
    network: str,
    sell_token: str,
    buy_token: str,
    amount: str,
    token_decimals: int = 18,
    token_symbol: str = None
) -> dict:
    """
    Get a quote from CowSwap.
    
    Args:
        network: The network to use (ethereum, base)
        sell_token: The token to sell
        buy_token: The token to buy (EURC)
        amount: The amount to sell in wei
        token_decimals: The number of decimals for the token
        token_symbol: The symbol of the token (optional)
        
    Returns:
        dict: The quote response
    """
    # EURC has 6 decimals
    buy_decimals = 6
    
    # Get quote from CowSwap
    quote = get_cowswap_quote(
        network=network,
        sell_token=sell_token,
        buy_token=buy_token,
        amount=amount,
        sell_decimals=token_decimals,
        buy_decimals=buy_decimals
    )
    
    return quote

def get_cowswap_quote(
    network: str,
    sell_token: str,
    buy_token: str,
    amount: str,
    sell_decimals: int,
    buy_decimals: int
) -> dict:
    """
    Fetches price quote from CoW Protocol API for token conversion with fallback mechanism.
    
    Args:
        network: Network identifier ('ethereum' or 'base')
        sell_token: Address of token to sell
        buy_token: Address of token to buy (EURC)
        amount: Amount to sell in wei (as string)
        sell_decimals: Decimals of the sell token
        buy_decimals: Decimals of the buy token
    
    Returns:
        Dict containing:
        - quote: API response with buy amount, etc.
        - conversion_details: Information about the conversion method used
    """
    api_network = "mainnet" if network == "ethereum" else network
    api_url = f"https://api.cow.fi/{api_network}/api/v1/quote"

    def make_request(params):
        response = APIRetry.post(api_url, json=params)
        return response.json() if response.ok else response.text

    base_params = {
        "sellToken": sell_token,
        "buyToken": buy_token,
        "from": ZERO_ADDRESS,
        "receiver": ZERO_ADDRESS,
        "validTo": int(datetime.now(timezone.utc).timestamp() + 3600),  # 1 hour validity
        "appData": "0x0000000000000000000000000000000000000000000000000000000000000000",
        "partiallyFillable": False,
        "sellTokenBalance": "erc20",
        "buyTokenBalance": "erc20",
        "kind": "sell"
    }

    # Try direct quote first
    params = {**base_params, "sellAmountBeforeFee": str(amount)}
    quote = make_request(params)

    # If successful, return with direct quote details
    if isinstance(quote, dict) and 'quote' in quote:
        eurc_amount = int(quote['quote']['buyAmount'])
        
        # Calculate rate properly considering decimals
        sell_amount = Decimal(quote['quote']['sellAmount'])
        buy_amount = Decimal(quote['quote']['buyAmount'])
        
        # Normalize both amounts to their decimal places
        sell_normalized = sell_amount / Decimal(10**sell_decimals)
        buy_normalized = buy_amount / Decimal(10**buy_decimals)
        
        # Calculate rate as buy/sell
        rate = buy_normalized / sell_normalized
        
        return {
            "quote": quote,
            "conversion_details": {
                "source": "CoWSwap",
                "price_impact": quote['quote'].get('priceImpact', 'N/A'),
                "rate": str(rate),
                "fee_percentage": str(Decimal(quote['quote'].get('feeAmount', '0')) / Decimal(amount) * 100),
                "fallback": False,
                "note": "Direct CoWSwap quote"
            }
        }

    # If amount too small, try fallback with reference amount
    if isinstance(quote, str) and "SellAmountDoesNotCoverFee" in quote:
        # Use 1000 tokens as reference
        reference_amount = str(1000 * 10**sell_decimals)
        params = {**base_params, "sellAmountBeforeFee": reference_amount}
        fallback_quote = make_request(params)

        if isinstance(fallback_quote, dict) and 'quote' in fallback_quote:
            # Calculate rate using reference quote
            sell_amount = Decimal(fallback_quote['quote']['sellAmount'])
            buy_amount = Decimal(fallback_quote['quote']['buyAmount'])
            
            # Normalize amounts based on token decimals
            sell_normalized = sell_amount / Decimal(10**sell_decimals)
            buy_normalized = buy_amount / Decimal(10**buy_decimals)
            
            # Calculate rate as buy/sell
            rate = buy_normalized / sell_normalized
            
            # Apply rate to original amount
            original_amount_normalized = Decimal(amount) / Decimal(10**sell_decimals)
            estimated_value = int(original_amount_normalized * rate * Decimal(10**buy_decimals))

            return {
                "quote": {
                    "quote": {
                        "buyAmount": str(estimated_value),
                        "sellAmount": amount,
                        "feeAmount": "0"
                    }
                },
                "conversion_details": {
                    "source": "CoWSwap-Fallback",
                    "price_impact": "N/A",
                    "rate": f"{float(rate):.6f}",
                    "fee_percentage": "N/A",
                    "fallback": True,
                    "note": "Using reference amount of 1000 tokens for price discovery"
                }
            }

    # If all attempts fail
    return {
        "quote": None,
        "conversion_details": {
            "source": "Failed",
            "price_impact": "N/A",
            "rate": "0",
            "fee_percentage": "N/A",
            "fallback": True,
            "note": "All quote attempts failed"
        }
    }

if __name__ == "__main__":
    """
    Test script for CoW Protocol quote functionality.
    Attempts to get EURC quote for 10000 USDS.
    """
    # EURC address
    EURC_ADDRESS = "0x60a3e35cc302bfa44cb288bc5a4f316fdb1adb42"
    
    # Test with 10000 USDS (18 decimals)
    amount = str(10000 * 10**18)
    
    result = get_quote(
        network="base",
        sell_token=NETWORK_TOKENS["base"]["USDS"]["address"],
        buy_token=EURC_ADDRESS,
        amount=amount
    )
    
    if result["quote"] and 'quote' in result["quote"]:
        quote = result["quote"]["quote"]
        buy_amount = int(quote['buyAmount'])
        
        print("\nTest USDS to EURC conversion:")
        print(f"Input: 10000 USDS ({amount} wei)")
        print(f"Output: {buy_amount/10**6:.6f} EURC ({buy_amount} wei)")
        print("Conversion details:", json.dumps(result["conversion_details"], indent=2))
    else:
        print(f"Error getting quote: {result}") 