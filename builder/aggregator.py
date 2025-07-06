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

from aave.check_contracts import get_aave_balances, ERC20_ABI, RPC_URLS
from vault.vault_reader import VaultReader
from config.networks import NETWORK_TOKENS, COMMON_TOKENS
from cowswap.cow_client import get_quote

class BalanceAggregator:
    """
    Master aggregator that combines balances from multiple protocols.
    Currently supports:
    - Aave (Base)
    - DeTrade Core USDC Vault (Base)
    """
    
    def __init__(self):
        self.vault_reader = VaultReader()
        
        # Hardcoded refund configuration
        self.MERKLE_REFUND_ENABLED = False  # Set to True to enable merkle refund calculation
        self.MERKLE_REFUND = {
            "address": "0x067ae75628177FD257c2B1e500993e1a0baBcBd1",
            "token": "aBasGHO",
            "amount": "0.447",  # Amount in token units
            "network": "base"
        }
        
    def get_all_balances(self, address: str) -> Dict[str, Any]:
        """
        Fetches and combines balances from all supported protocols
        """
        # Get UTC timestamp before any on-chain requests
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        print("\n" + "="*80)
        print("FETCHING PROTOCOL BALANCES")
        print("="*80)
        
        # Convert address to checksum format
        checksum_address = Web3.to_checksum_address(address)
        
        # Initialize result structure
        result = {
            "protocols": {
                "aave": {},
                "detrade-core-usdc": {}
            },
            "merkle_refund": {}
        }
        
        # Get Aave balances
        try:
            print("\n" + "="*80)
            print("AAVE BALANCE CHECKER")
            print("="*80 + "\n")
            aave_balances = get_aave_balances()
            if aave_balances:
                # Extract content directly to avoid double "aave" key
                result["protocols"]["aave"] = {
                    "positions": aave_balances["aave"],
                    "net_position": aave_balances["net_position"]
                }
                print("✓ Aave positions fetched successfully")
                
                # Add detailed logging for Aave
                if "aave" in aave_balances and aave_balances["aave"]:
                    print("\nAave positions:")
                    for position in aave_balances["aave"]:
                        print(f"\n{position['symbol']}:")
                        print(f"  Contract: {position['contract']}")
                        print(f"  Raw balance: {position['raw_balance']}")
                        print(f"  Underlying: {position['underlying_symbol']} ({position['underlying_asset']})")
                        if position['eurc_conversion']:
                            print(f"  EURC value: {position['eurc_conversion']['eurc_value']}")
                            print(f"  Conversion rate: {position['eurc_conversion']['conversion_rate']}")
                            print(f"  Source: {position['eurc_conversion']['conversion_source']}")
                    
                    if "net_position" in aave_balances:
                        net_pos = aave_balances["net_position"]
                        print(f"\nNet position:")
                        print(f"  Total supply EURC: {net_pos['total_supply_eurc']}")
                        print(f"  Total debt EURC: {net_pos['total_debt_eurc']}")
                        print(f"  Net position EURC: {net_pos['net_position_eurc']}")
        except Exception as e:
            print(f"✗ Error fetching Aave positions: {str(e)}")
            result["protocols"]["aave"] = {"positions": [], "net_position": {"total_supply_eurc": "0", "total_debt_eurc": "0", "net_position_eurc": "0"}}
        
        # Get Vault balances
        try:
            print("\n" + "="*80)
            print("DETRADE CORE USDC VAULT")
            print("="*80 + "\n")
            vault_data = self.vault_reader.get_vault_data()
            if vault_data:
                result["protocols"]["detrade-core-usdc"] = vault_data["detrade-core-usdc"]
                print("✓ Vault positions fetched successfully")
                
                # Add detailed logging for Vault
                vault_info = vault_data["detrade-core-usdc"]
                print(f"\nVault data:")
                print(f"  Shares: {vault_info['shares']}")
                print(f"  Share price: {vault_info['share_price']}")
                print(f"  USDC value: {vault_info['usdc_value']}")
                print(f"  EURC value: {vault_info['eurc_value']}")
                print(f"  Conversion rate: {vault_info['conversion_rate']}")
                print(f"  Source: {vault_info['conversion_source']}")
        except Exception as e:
            print(f"✗ Error fetching Vault positions: {str(e)}")
            result["protocols"]["detrade-core-usdc"] = {"shares": "0", "share_price": "0", "usdc_value": "0", "eurc_value": "0"}
        
        # Get Merkle refund (only if enabled)
        if self.MERKLE_REFUND_ENABLED:
            try:
                print("\n" + "="*80)
                print("MERKLE REFUND CALCULATION")
                print("="*80 + "\n")
                merkle_refund_data = self.get_merkle_refund_eurc_value()
                if merkle_refund_data:
                    result["merkle_refund"] = merkle_refund_data["merkle_refund"]
                    print("✓ Merkle refund calculated successfully")
                    
                    # Add detailed logging for Merkle refund
                    refund_info = merkle_refund_data["merkle_refund"]
                    print(f"\nMerkle refund data:")
                    print(f"  Address: {refund_info['address']}")
                    print(f"  Token: {refund_info['token']}")
                    print(f"  Amount: {refund_info['amount']} {refund_info['token']}")
                    print(f"  EURC value: {refund_info['eurc_value']}")
                    print(f"  Conversion rate: {refund_info['conversion_rate']}")
                    print(f"  Source: {refund_info['conversion_source']}")
                    if 'error' in refund_info:
                        print(f"  Error: {refund_info['error']}")
            except Exception as e:
                print(f"✗ Error calculating Merkle refund: {str(e)}")
                result["merkle_refund"] = {
                    "address": self.MERKLE_REFUND["address"],
                    "token": self.MERKLE_REFUND["token"],
                    "amount": self.MERKLE_REFUND["amount"],
                    "amount_wei": "0",
                    "eurc_value": "0",
                    "conversion_rate": "0",
                    "conversion_source": "Error",
                    "price_impact": "N/A",
                    "fallback_used": True,
                    "error": str(e)
                }
        else:
            print("\n" + "="*80)
            print("MERKLE REFUND CALCULATION")
            print("="*80 + "\n")
            print("⚠️  Merkle refund calculation is disabled (already claimed)")
            print("   Set MERKLE_REFUND_ENABLED = True to re-enable")
            result["merkle_refund"] = {
                "enabled": False,
                "reason": "Already claimed - rewards have been distributed"
            }
        
        return result
        
    def get_merkle_refund_eurc_value(self) -> dict:
        """
        Calculate EURC value for the hardcoded Merkle refund (aBasGHO)
        """
        try:
            # Setup web3
            w3 = Web3(Web3.HTTPProvider(RPC_URLS[ self.MERKLE_REFUND["network"] ]))
            abasgho_address = NETWORK_TOKENS[self.MERKLE_REFUND["network"]][self.MERKLE_REFUND["token"]]["address"]
            abasgho_decimals = NETWORK_TOKENS[self.MERKLE_REFUND["network"]][self.MERKLE_REFUND["token"]]["decimals"]
            abasgho_contract = w3.eth.contract(address=abasgho_address, abi=ERC20_ABI)
            # Get underlying asset address (GHO)
            underlying_address = abasgho_contract.functions.UNDERLYING_ASSET_ADDRESS().call()
            # Get decimals of underlying (GHO)
            underlying_contract = w3.eth.contract(address=underlying_address, abi=ERC20_ABI)
            underlying_decimals = underlying_contract.functions.decimals().call()
            # Convert amount to wei (GHO)
            amount_wei = str(int(Decimal(self.MERKLE_REFUND["amount"]) * Decimal(10**underlying_decimals)))
            # Get EURC quote via CoWSwap
            quote_result = get_quote(
                network=self.MERKLE_REFUND["network"],
                sell_token=underlying_address,
                buy_token=COMMON_TOKENS[self.MERKLE_REFUND["network"]]["EURC"]["address"],
                amount=amount_wei,
                token_decimals=underlying_decimals,
                token_symbol="GHO"
            )
            if quote_result["quote"] and 'quote' in quote_result["quote"]:
                eurc_amount_wei = quote_result["quote"]["quote"]["buyAmount"]
                return {
                    "merkle_refund": {
                        "address": self.MERKLE_REFUND["address"],
                        "token": self.MERKLE_REFUND["token"],
                        "amount": self.MERKLE_REFUND["amount"],
                        "amount_wei": amount_wei,
                        "eurc_value": eurc_amount_wei,
                        "conversion_rate": quote_result["conversion_details"]["rate"],
                        "conversion_source": quote_result["conversion_details"]["source"],
                        "price_impact": quote_result["conversion_details"]["price_impact"],
                        "fallback_used": quote_result["conversion_details"]["fallback"],
                        "underlying_address": underlying_address
                    }
                }
            else:
                return {
                    "merkle_refund": {
                        "address": self.MERKLE_REFUND["address"],
                        "token": self.MERKLE_REFUND["token"],
                        "amount": self.MERKLE_REFUND["amount"],
                        "amount_wei": amount_wei,
                        "eurc_value": "0",
                        "conversion_rate": "0",
                        "conversion_source": "Failed",
                        "price_impact": "N/A",
                        "fallback_used": True,
                        "error": "Failed to get quote",
                        "underlying_address": underlying_address
                    }
                }
        except Exception as e:
            return {
                "merkle_refund": {
                    "address": self.MERKLE_REFUND["address"],
                    "token": self.MERKLE_REFUND["token"],
                    "amount": self.MERKLE_REFUND["amount"],
                    "amount_wei": "0",
                    "eurc_value": "0",
                    "conversion_rate": "0",
                    "conversion_source": "Error",
                    "price_impact": "N/A",
                    "fallback_used": True,
                    "error": str(e)
                }
            }

def build_overview(all_balances: Dict[str, Any], address: str) -> Dict[str, Any]:
    """Build overview section with positions"""
    
    # Initialize positions dictionary
    positions = {}
    
    # Process Aave net position only
    if "protocols" in all_balances and "aave" in all_balances["protocols"] and "net_position" in all_balances["protocols"]["aave"]:
        net_pos = all_balances["protocols"]["aave"]["net_position"]
        positions["aave.net_position"] = net_pos["net_position_eurc"]
    
    # Process Vault position
    if "protocols" in all_balances and "detrade-core-usdc" in all_balances["protocols"]:
        vault_data = all_balances["protocols"]["detrade-core-usdc"]
        positions["vault.detrade_core_usdc"] = vault_data["eurc_value"]
    
    # Process Merkle refund position (only if enabled and has value)
    if ("merkle_refund" in all_balances and 
        "eurc_value" in all_balances["merkle_refund"] and 
        all_balances["merkle_refund"].get("enabled", True)):
        refund_data = all_balances["merkle_refund"]
        positions["merkle_refund.abasgho"] = refund_data["eurc_value"]
    
    # Sort positions by value in descending order
    sorted_positions = dict(sorted(
        positions.items(),
        key=lambda x: Decimal(x[1]),
        reverse=True
    ))
    
    # Calculate total value from positions (all in EURC wei)
    total_value_eurc_wei = sum(Decimal(value) for value in sorted_positions.values())
    
    # Convert to EURC with 6 decimals for display
    total_value_eurc = total_value_eurc_wei / Decimal(10**6)
    
    return {
        "nav": {
            "eurc_wei": str(total_value_eurc_wei),
            "eurc": f"{total_value_eurc:.6f}"
        },
        "positions": sorted_positions
    }

def main():
    """
    Main function to aggregate all balance data.
    Uses command line argument if provided, otherwise uses default address.
    """
    # Default address
    DEFAULT_ADDRESS = '0xd201B0947AE7b057B0751e227B07D37b1a771570'
    
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
    
    # Build the final result with overview, protocols and vault sections
    overview = build_overview(all_balances, address)
    
    # Format created_at to match timestamp format
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    final_result = {
        "timestamp": timestamp,
        "created_at": created_at,
        "address": address,
        **overview,  # Add overview (nav and positions)
        "protocols": all_balances["protocols"]
    }
    
    # Display final result
    print("\n" + "="*80)
    print("FINAL AGGREGATED RESULT")
    print("="*80 + "\n")
    print(json.dumps(final_result, indent=2))
    
    return final_result

if __name__ == "__main__":
    main()
