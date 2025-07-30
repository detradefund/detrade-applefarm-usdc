import sys
from pathlib import Path
from typing import Dict, Any
import json
from decimal import Decimal
from web3 import Web3
from datetime import datetime, timezone
import time
import os

# Add parent directory and project root to PYTHONPATH
root_path = str(Path(__file__).parent.parent)
sys.path.append(root_path)
sys.path.append(str(Path(__file__).parent.parent))

from superlend.check_balance import get_superlend_balances
from shares.supply_reader import SupplyReader

class BalanceAggregator:
    """
    Master aggregator that combines balances from multiple protocols.
    Currently supports:
    - Superlend (Etherlink) - slUSDC monitoring
    """
    
    def __init__(self):
        self.supply_reader = SupplyReader()
        
    def get_all_balances(self, address: str) -> Dict[str, Any]:
        """
        Fetches balances from Superlend protocol on Etherlink
        """
        # Get UTC timestamp before any on-chain requests
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        print("\n" + "="*80)
        print("FETCHING SUPERLEND BALANCES")
        print("="*80)
        
        # Convert address to checksum format
        checksum_address = Web3.to_checksum_address(address)
        
        # Initialize result structure
        result = {
            "protocols": {
                "superlend": {
                    "etherlink": {}
                }
            }
        }
        
        # Get Superlend balances
        try:
            print("\n" + "="*80)
            print("SUPERLEND BALANCE CHECKER (ETHERLINK)")
            print("="*80 + "\n")
            superlend_balances = get_superlend_balances()
            if superlend_balances:
                # Organiser les positions par token
                etherlink_positions = {}
                for position in superlend_balances["superlend"]:
                    token_symbol = position["symbol"]
                    etherlink_positions[token_symbol] = {
                        "staking_contract": position["contract"],
                        "amount": position["raw_balance"],
                        "decimals": position["decimals"],
                        "formatted_balance": position["formatted_balance"],
                        "value": {
                            "USDC": {
                                "amount": position["usdc_value"]["usdc_value"],
                                "decimals": position["decimals"],
                                "formatted": position["usdc_value"]["usdc_formatted"],
                                "conversion_details": {
                                    "source": position["usdc_value"]["conversion_source"],
                                    "rate": position["usdc_value"]["conversion_rate"],
                                    "note": "1 slUSDC = 1 USDC (underlying)"
                                }
                            }
                        }
                    }
                
                # Calculer les totaux pour Etherlink
                etherlink_total_wei = sum(
                    int(token_data["value"]["USDC"]["amount"]) 
                    for token_data in etherlink_positions.values() 
                    if token_data.get("value") and token_data["value"].get("USDC")
                )
                etherlink_total_formatted = str(Decimal(etherlink_total_wei) / Decimal(10**6))
                
                # Ajouter les totaux
                if etherlink_positions:
                    etherlink_positions["totals"] = {
                        "wei": etherlink_total_wei,
                        "formatted": etherlink_total_formatted
                    }
                
                result["protocols"]["superlend"]["etherlink"] = etherlink_positions
                
                # Ajouter les totaux pour le protocole Superlend
                result["protocols"]["superlend"]["totals"] = {
                    "wei": etherlink_total_wei,
                    "formatted": etherlink_total_formatted
                }
                
                print("✓ Superlend positions fetched successfully")
                
                # Add detailed logging for Superlend
                if etherlink_positions:
                    print("\nSuperlend Etherlink positions:")
                    for token_symbol, token_data in etherlink_positions.items():
                        # Exclure les totaux du logging des positions
                        if token_symbol == "totals":
                            print(f"\nEtherlink totals:")
                            print(f"  Total USDC value: {token_data['formatted']}")
                            print(f"  Total USDC value (wei): {token_data['wei']}")
                            continue
                        print(f"\n{token_symbol}:")
                        print(f"  Contract: {token_data['staking_contract']}")
                        print(f"  Raw balance: {token_data['amount']}")
                        print(f"  Formatted balance: {token_data['formatted_balance']}")
                        if token_data.get('value') and token_data['value'].get('USDC'):
                            usdc_data = token_data['value']['USDC']
                            print(f"  USDC value: {usdc_data['formatted']}")
                            print(f"  USDC value (wei): {usdc_data['amount']}")
                            print(f"  Conversion rate: {usdc_data['conversion_details']['rate']}")
                            print(f"  Source: {usdc_data['conversion_details']['source']}")
        except Exception as e:
            print(f"✗ Error fetching Superlend positions: {str(e)}")
            result["protocols"]["superlend"]["etherlink"] = {}
            result["protocols"]["superlend"]["totals"] = {
                "wei": 0,
                "formatted": "0.0"
            }
        
        return result


def build_overview(all_balances: Dict[str, Any], address: str) -> Dict[str, Any]:
    """Build overview section with Superlend positions"""
    
    # Initialize positions dictionary
    positions = {}
    
    # Process Superlend positions
    if "protocols" in all_balances and "superlend" in all_balances["protocols"] and "etherlink" in all_balances["protocols"]["superlend"]:
        etherlink_positions = all_balances["protocols"]["superlend"]["etherlink"]
        for token_symbol, token_data in etherlink_positions.items():
            # Exclure les totaux des positions
            if token_symbol == "totals":
                continue
            if token_data.get("value") and token_data["value"].get("USDC"):
                positions[f"superlend.etherlink.{token_symbol}"] = token_data["value"]["USDC"]["amount"]
    
    # Sort positions by value in descending order
    sorted_positions = dict(sorted(
        positions.items(),
        key=lambda x: Decimal(x[1]),
        reverse=True
    ))
    
    # Calculate total value from positions (all in USDC wei - 6 decimals)
    total_value_usdc_wei = sum(Decimal(value) for value in sorted_positions.values())
    
    # Convert to USDC with 6 decimals for display
    total_value_usdc = total_value_usdc_wei / Decimal(10**6)
    
    return {
        "nav": {
            "usdc_wei": str(total_value_usdc_wei),
            "usdc": f"{total_value_usdc:.6f}"
        },
        "positions": sorted_positions
    }

def main():
    """
    Main function to aggregate Superlend balance data.
    Uses command line argument if provided, otherwise uses production address from .env.
    """
    # Get production address from environment
    from dotenv import load_dotenv
    load_dotenv()
    DEFAULT_ADDRESS = os.getenv('PRODUCTION_ADDRESS', '0xA6548c1F8D3F3c97f75deE8D030B942b6c88B6ce')
    
    # Get address from command line argument if provided
    address = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADDRESS
    
    if not Web3.is_address(address):
        print(f"Error: Invalid address format: {address}")
        return None
        
    # Create aggregator and get balances
    aggregator = BalanceAggregator()
    
    # Add retry logic for RPC calls
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            all_balances = aggregator.get_all_balances(address)
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print(f"All {max_retries} attempts failed")
                raise
    
    # Build the final result with overview and protocols sections
    overview = build_overview(all_balances, address)
    
    # Get total supply and calculate share price
    try:
        print("\n" + "="*80)
        print("CALCULATING SHARE PRICE")
        print("="*80 + "\n")
        
        total_supply_wei = aggregator.supply_reader.get_total_supply()
        total_supply_formatted = aggregator.supply_reader.format_total_supply()
        
        # Calculate share price: NAV / Total Supply
        nav_usdc_wei = Decimal(overview["nav"]["usdc_wei"])
        supply_wei = Decimal(total_supply_wei)
        
        if supply_wei > 0:
            # Share price in USDC (with 18 decimals precision)
            share_price_wei = nav_usdc_wei * Decimal(10**18) / supply_wei
            share_price_formatted = share_price_wei / Decimal(10**6)  # Convert back to USDC (6 decimals)
        else:
            share_price_wei = Decimal(0)
            share_price_formatted = Decimal(0)
        
        print(f"Total Supply: {total_supply_formatted} dtUSDC")
        print(f"NAV: {overview['nav']['usdc']} USDC")
        print(f"Share Price: {share_price_formatted:.6f} USDC per dtUSDC")
        
    except Exception as e:
        print(f"✗ Error calculating share price: {str(e)}")
        total_supply_wei = "0"
        total_supply_formatted = "0.0"
        share_price_formatted = Decimal(0)
    
    # Format created_at to match timestamp format
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Update nav with share price information
    enhanced_nav = {
        "usdc_wei": overview["nav"]["usdc_wei"],
        "usdc": overview["nav"]["usdc"],
        "share_price": f"{share_price_formatted:.6f}",
        "total_supply": total_supply_wei
    }
    
    final_result = {
        "timestamp": timestamp,
        "created_at": created_at,
        "address": address,
        "nav": enhanced_nav,
        "positions": overview["positions"],
        "protocols": all_balances["protocols"]
    }
    
    # Display final result
    print("\n" + "="*80)
    print("FINAL SUPERLEND AGGREGATED RESULT")
    print("="*80 + "\n")
    print(json.dumps(final_result, indent=2))
    
    return final_result

if __name__ == "__main__":
    main()
