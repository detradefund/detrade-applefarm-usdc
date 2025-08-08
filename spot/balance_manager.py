from web3 import Web3
import sys
import os
from pathlib import Path
from typing import Dict, Any
from decimal import Decimal
import time
import requests
import json

# Add parent directory to PYTHONPATH
root_path = str(Path(__file__).parent.parent)
sys.path.append(root_path)

from config.networks import NETWORK_TOKENS, RPC_URLS
from utils.retry import Web3Retry, APIRetry

# Production address from environment variable
PRODUCTION_ADDRESS = os.getenv('PRODUCTION_ADDRESS', '0x66DbceE7feA3287B3356227d6F3DfF3CeFbC6F3C')

class SpotBalanceManager:
    """Manages spot token balances across networks"""
    
    def __init__(self):
        # Initialize Web3 connections for each network
        self.connections = {
            "etherlink": Web3(Web3.HTTPProvider(RPC_URLS['etherlink']))
        }
        
        # Initialize contracts for each network
        self.contracts = self._init_contracts()

    def _init_contracts(self) -> Dict[str, Any]:
        """Initialize contracts for all supported tokens"""
        contracts = {}
        
        # Standard ERC20 ABI for balanceOf function
        abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }
        ]
        
        # Initialize contracts for each network
        for network, w3 in self.connections.items():
            # Get all tokens for the network
            for symbol, token_data in NETWORK_TOKENS[network].items():
                # Skip yield-bearing tokens
                if token_data.get("type") == "yield-bearing":
                    continue
                    
                if symbol not in contracts:
                    contracts[symbol] = {}
                
                contracts[symbol][network] = w3.eth.contract(
                    address=Web3.to_checksum_address(token_data["address"]),
                    abi=abi
                )
                
        return contracts

    def _get_wxtz_usdc_price(self) -> tuple[str, dict]:
        """
        Get WXTZ price in USDC from GeckoTerminal API
        Returns (price_rate, conversion_details)
        """
        try:
            # API endpoint for the USDC/WXTZ pool on Etherlink
            url = "https://api.geckoterminal.com/api/v2/search/pools?query=0x508060a01f11d6a2eb774b55aeba95931265e0cc&network=etherlink&page=1"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("data") and len(data["data"]) > 0:
                pool_data = data["data"][0]
                attributes = pool_data.get("attributes", {})
                
                # Get WXTZ price in USDC (quote_token_price_base_token)
                wxtz_usdc_price = attributes.get("quote_token_price_base_token")
                
                if wxtz_usdc_price:
                    return str(wxtz_usdc_price), {
                        "source": "GeckoTerminal API",
                        "price_impact": "Live market rate",
                        "rate": str(wxtz_usdc_price),
                        "fee_percentage": "N/A",
                        "fallback": False,
                        "note": f"Live WXTZ/USDC rate from pool {attributes.get('name', 'USDC/WXTZ')}"
                    }
            
            # Fallback if no data found
            return "0.8", {
                "source": "Fallback rate",
                "price_impact": "N/A",
                "rate": "0.8",
                "fee_percentage": "N/A",
                "fallback": True,
                "note": "API returned no data, using fallback rate"
            }
            
        except Exception as e:
            # Fallback in case of API error
            print(f"Warning: Failed to fetch WXTZ price from GeckoTerminal: {str(e)}")
            return "0.8", {
                "source": "Error fallback",
                "price_impact": "N/A",
                "rate": "0.8",
                "fee_percentage": "N/A",
                "fallback": True,
                "note": f"API error: {str(e)[:100]}, using fallback rate"
            }

    def get_balances(self, address: str) -> Dict[str, Any]:
        """
        Get all token balances for an address including native XTZ, WXTZ, applXTZ and USDC.
        """
        print("SPOT BALANCE MANAGER - Etherlink XTZ, WXTZ, Apple XTZ & USDC")
        
        print("\nProcessing method:")
        print("  - Getting native XTZ balance")
        print("  - Querying balanceOf(address) for WXTZ, Apple XTZ and USDC tokens")
        print("  - Getting live WXTZ/USDC price from GeckoTerminal (single API call)")
        print("  - USDC: 1 USDC = 1 USDC (no conversion needed)")
        
        # Get WXTZ/USDC price once for XTZ/WXTZ/applXTZ conversions
        wxtz_usdc_rate, price_conversion_details = self._get_wxtz_usdc_price()
        print(f"\nWXTZ/USDC rate: {wxtz_usdc_rate} (source: {price_conversion_details['source']})")
        print("  → Using same rate for XTZ, WXTZ and applXTZ")
        print("  → USDC uses direct 1:1 conversion")
        
        checksum_address = Web3.to_checksum_address(address)
        result = {}
        total_usd_wei = 0
        
        try:
            # Process Etherlink network
            network = "etherlink"
            print(f"\nProcessing network: {network}")
            network_total = 0
            
            # Initialize network structure
            network_result = {}
            
            # 1. Get native XTZ balance
            try:
                print("\nProcessing native XTZ balance:")
                w3 = self.connections[network]
                xtz_balance_wei = Web3Retry.get_balance(w3, checksum_address)
                xtz_balance_normalized = Decimal(xtz_balance_wei) / Decimal(10**18)
                print(f"  Amount: {xtz_balance_normalized:.6f} XTZ")
                
                if xtz_balance_wei > 0:
                    # Convert XTZ to USDC using same rate as WXTZ (1 XTZ = 1 WXTZ)
                    usdc_amount = str(int(Decimal(xtz_balance_wei) * Decimal(wxtz_usdc_rate) * Decimal(10**6) / Decimal(10**18)))
                    
                    network_total += int(usdc_amount)
                    total_usd_wei += int(usdc_amount)
                    
                    # Add XTZ data
                    network_result["XTZ"] = {
                        "amount": str(xtz_balance_wei),
                        "decimals": 18,
                        "value": {
                            "WXTZ": {
                                "amount": str(xtz_balance_wei),  # 1:1 conversion
                                "decimals": 18,
                                "conversion_details": {
                                    "source": "Direct",
                                    "price_impact": "0.0000%",
                                    "rate": "1.000000",
                                    "fee_percentage": "0.0000%",
                                    "fallback": False,
                                    "note": "1 XTZ = 1 WXTZ (conceptual parity)"
                                }
                            },
                            "USDC": {
                                "amount": usdc_amount,
                                "decimals": 6,
                                "formatted": f"{Decimal(usdc_amount) / Decimal(10**6):.6f}",
                                "conversion_details": price_conversion_details
                            }
                        }
                    }
                else:
                    print("  → Balance is 0, skipping")
                    
            except Exception as e:
                print(f"Error checking native XTZ balance: {str(e)}")
            
            # 2. Process ERC20 tokens (WXTZ, applXTZ and USDC)
            for token_type, network_contracts in self.contracts.items():
                if network not in network_contracts:
                    continue
                    
                contract = network_contracts[network]
                balance = Web3Retry.call_contract_function(
                    contract.functions.balanceOf(checksum_address).call
                )
                
                token_symbol = token_type
                decimals = NETWORK_TOKENS[network][token_symbol]["decimals"]
                balance_normalized = Decimal(balance) / Decimal(10**decimals)
                
                print(f"\nProcessing token: {token_symbol}")
                print(f"  Amount: {balance_normalized:.6f} {token_symbol}")
                
                if balance > 0:
                    if token_symbol == "USDC":
                        # USDC: Direct 1:1 conversion (no price conversion needed)
                        usdc_amount = str(balance)  # Already in USDC wei (6 decimals)
                        
                        network_total += int(usdc_amount)
                        total_usd_wei += int(usdc_amount)
                        
                        # Add USDC data (only USDC value, no WXTZ intermediate)
                        network_result[token_symbol] = {
                            "amount": str(balance),
                            "decimals": decimals,
                            "value": {
                                "USDC": {
                                    "amount": usdc_amount,
                                    "decimals": 6,
                                    "formatted": f"{Decimal(usdc_amount) / Decimal(10**6):.6f}",
                                    "conversion_details": {
                                        "source": "Direct",
                                        "price_impact": "0.0000%",
                                        "rate": "1.000000",
                                        "fee_percentage": "0.0000%",
                                        "fallback": False,
                                        "note": "1 USDC = 1 USDC (no conversion needed)"
                                    }
                                }
                            }
                        }
                    else:
                        # Other tokens (WXTZ, applXTZ) use WXTZ/USDC rate
                        if token_symbol == "WXTZ":
                            # Direct conversion for WXTZ
                            wxtz_amount = balance
                            conversion_note = "Direct WXTZ balance"
                        else:  # applXTZ
                            # applXTZ converts 1:1 to WXTZ
                            wxtz_amount = balance
                            conversion_note = "1 applXTZ = 1 WXTZ (fixed rate)"
                        
                        # Convert to USDC using live rate
                        usdc_amount = str(int(Decimal(wxtz_amount) * Decimal(wxtz_usdc_rate) * Decimal(10**6) / Decimal(10**18)))
                        
                        network_total += int(usdc_amount)
                        total_usd_wei += int(usdc_amount)
                        
                        # Add token data
                        network_result[token_symbol] = {
                            "amount": str(balance),
                            "decimals": decimals,
                            "value": {
                                "WXTZ": {
                                    "amount": str(wxtz_amount),
                                    "decimals": 18,
                                    "conversion_details": {
                                        "source": "Direct",
                                        "price_impact": "0.0000%",
                                        "rate": "1.000000",
                                        "fee_percentage": "0.0000%",
                                        "fallback": False,
                                        "note": conversion_note
                                    }
                                },
                                "USDC": {
                                    "amount": usdc_amount,
                                    "decimals": 6,
                                    "formatted": f"{Decimal(usdc_amount) / Decimal(10**6):.6f}",
                                    "conversion_details": price_conversion_details
                                }
                            }
                        }
                else:
                    print("  → Balance is 0, skipping")
            
            # Add network totals only if there are balances
            if network_total > 0:
                network_result["totals"] = {
                    "wei": network_total,
                    "formatted": f"{network_total/1e6:.6f}"  # USDC has 6 decimals
                }
                # Only add network to result if it has balances
                result[network] = network_result
        
            # Add protocol total only if there are balances
            if total_usd_wei > 0:
                result["totals"] = {
                    "wei": total_usd_wei,
                    "formatted": f"{total_usd_wei/1e6:.6f}"  # USDC has 6 decimals
                }

            print("\n[Spot] Calculation complete")
            return result
            
        except Exception as e:
            print(f"\nError processing spot balances: {str(e)}")
            return result

    def format_balance(self, balance: int, decimals: int) -> str:
        """Format raw balance to human readable format"""
        return str(Decimal(balance) / Decimal(10**decimals))

    def get_supported_networks(self) -> list:
        """Implementation of abstract method"""
        return list(self.connections.keys())
    
    def get_protocol_info(self) -> dict:
        """Implementation of abstract method"""
        return {
            "name": "Spot Tokens - XTZ, WXTZ, Apple XTZ & USDC",
            "tokens": {
                "XTZ": {
                    "etherlink": {
                        "address": "native",
                        "decimals": 18,
                        "name": "Tezos",
                        "symbol": "XTZ"
                    }
                },
                "WXTZ": {
                    "etherlink": NETWORK_TOKENS["etherlink"]["WXTZ"]
                },
                "applXTZ": {
                    "etherlink": NETWORK_TOKENS["etherlink"]["applXTZ"]
                },
                "USDC": {
                    "etherlink": NETWORK_TOKENS["etherlink"]["USDC"]
                }
            }
        }

def main():
    import json
    
    # Use command line argument if provided, otherwise use production address
    test_address = sys.argv[1] if len(sys.argv) > 1 else PRODUCTION_ADDRESS
    
    manager = SpotBalanceManager()
    balances = manager.get_balances(test_address)
    
    print("\n" + "="*80)
    print("FINAL RESULT:")
    print("="*80 + "\n")
    print(json.dumps(balances, indent=2))

if __name__ == "__main__":
    main() 