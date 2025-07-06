from web3 import Web3
from decimal import Decimal
import os
from dotenv import load_dotenv
from pathlib import Path
import sys
import logging
from utils.retry import Web3Retry

"""
DeTrade Core USDC Vault reader.
Simplified implementation to read shares, share price and USDC value.
Now includes EURC conversion via CoW Swap.
"""

# Configure logging
class CustomFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.INFO:
            self._style._fmt = '%(message)s'
        return super().format(record)

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(CustomFormatter())
logger.addHandler(handler)
logger.setLevel(logging.ERROR)

# Add parent directory to PYTHONPATH
root_path = str(Path(__file__).parent.parent)
sys.path.append(root_path)

from config.networks import RPC_URLS, NETWORK_TOKENS, COMMON_TOKENS
from cowswap.cow_client import get_quote

# Contract configuration
CONTRACT_ADDRESS = "0x8092cA384D44260ea4feaf7457B629B8DC6f88F0"
CONTRACT_NAME = "DeTrade Core USDC Vault"

class VaultReader:
    """
    Simplified reader for DeTrade Core USDC Vault on Base network.
    Now includes EURC conversion functionality.
    """
    
    def __init__(self, address: str = None, rpc_url: str = None):
        # Use provided address or load from environment variable
        self.user_address = address or os.getenv('PRODUCTION_ADDRESS', '0xd201B0947AE7b057B0751e227B07D37b1a771570')
        
        # Contract configuration
        self.contract_address = CONTRACT_ADDRESS
        
        # Initialize Web3 connection
        rpc_url = rpc_url or RPC_URLS['base']
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to RPC endpoint")
        
        # Setup contract with essential functions
        self.abi = [
            {
                "name": "totalSupply",
                "inputs": [],
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "name": "totalAssets",
                "inputs": [],
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "name": "balanceOf",
                "inputs": [{"name": "account", "type": "address"}],
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "name": "asset",
                "inputs": [],
                "outputs": [{"name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.contract_address),
            abi=self.abi
        )
    
    def get_underlying_asset(self) -> str:
        """Get the underlying asset address"""
        asset_address = Web3Retry.call_contract_function(
            self.contract.functions.asset().call
        )
        return asset_address
    
    def get_user_shares(self) -> str:
        """Get user shares count in wei"""
        user_balance = Web3Retry.call_contract_function(
            self.contract.functions.balanceOf(self.user_address).call
        )
        return str(user_balance)

    def get_share_price(self) -> str:
        """Calculate the price of one vault share in USDC wei"""
        total_assets = Web3Retry.call_contract_function(
            self.contract.functions.totalAssets().call
        )
        total_supply = Web3Retry.call_contract_function(
            self.contract.functions.totalSupply().call
        )
        
        if total_supply == "0":
            return "0"
        
        # Calculate price: (totalAssets * 10^18) / totalSupply
        # totalAssets is in 6 decimals (USDC), totalSupply is in 18 decimals
        # We want price in USDC wei (6 decimals)
        price_raw = (Decimal(total_assets) * Decimal('1000000000000000000')) / Decimal(total_supply)
        return str(int(price_raw))

    def get_usdc_value(self) -> str:
        """Calculate the USDC value of user shares in wei"""
        user_shares = self.get_user_shares()
        share_price = self.get_share_price()
        
        # Calculate value: (user_shares * share_price) / 10^18
        # user_shares is in 18 decimals, share_price is in 6 decimals
        value_raw = (Decimal(user_shares) * Decimal(share_price)) / Decimal('1000000000000000000')
        return str(int(value_raw))

    def get_eurc_value(self) -> dict:
        """Convert USDC value to EURC using CoW Swap"""
        usdc_value_wei = self.get_usdc_value()
        
        try:
            # Get quote from CoW Swap
            quote_result = get_quote(
                network="base",
                sell_token=NETWORK_TOKENS["base"]["USDC"]["address"],
                buy_token=COMMON_TOKENS["base"]["EURC"]["address"],
                amount=usdc_value_wei,
                token_decimals=6
            )
            
            if quote_result["quote"] and 'quote' in quote_result["quote"]:
                eurc_amount_wei = quote_result["quote"]["quote"]["buyAmount"]
                
                return {
                    "eurc_value": eurc_amount_wei,
                    "conversion_rate": quote_result["conversion_details"]["rate"],
                    "price_impact": quote_result["conversion_details"]["price_impact"],
                    "conversion_source": quote_result["conversion_details"]["source"],
                    "fallback_used": quote_result["conversion_details"]["fallback"]
                }
            else:
                return {
                    "eurc_value": "0",
                    "conversion_rate": "0",
                    "price_impact": "N/A",
                    "conversion_source": "Failed",
                    "fallback_used": True,
                    "error": "Failed to get quote"
                }
                
        except Exception as e:
            return {
                "eurc_value": "0",
                "conversion_rate": "0",
                "price_impact": "N/A",
                "conversion_source": "Error",
                "fallback_used": True,
                "error": str(e)
            }

    def get_vault_data(self) -> dict:
        """Returns vault data with both USDC and EURC values in wei"""
        vault_data = {
            "shares": self.get_user_shares(),
            "share_price": self.get_share_price(),
            "usdc_value": self.get_usdc_value()
        }
        
        # Add EURC conversion
        eurc_data = self.get_eurc_value()
        vault_data.update(eurc_data)
        
        # Return with protocol key
        data = {
            "detrade-core-usdc": vault_data
        }
        
        return data

def main():
    """CLI utility to check DeTrade Core USDC Vault data"""
    try:
        reader = VaultReader()
        data = reader.get_vault_data()
        
        # Print the dictionary
        import json
        print(json.dumps(data, indent=2))
        
    except Exception as e:
        logger.error(f"\n❌ Error: {str(e)}\n")
        raise

if __name__ == "__main__":
    main() 