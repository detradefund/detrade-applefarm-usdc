from web3 import Web3
import sys
from pathlib import Path
from typing import Dict, Any
from decimal import Decimal
import time

# Add parent directory to PYTHONPATH
root_path = str(Path(__file__).parent.parent)
sys.path.append(root_path)

from config.networks import NETWORK_TOKENS, RPC_URLS
from cowswap.cow_client import get_quote
from utils.retry import Web3Retry, APIRetry

# Production address
PRODUCTION_ADDRESS = "0x66DbceE7feA3287B3356227d6F3DfF3CeFbC6F3C"

class SpotBalanceManager:
    """Manages spot token balances across networks"""
    
    def __init__(self):
        # Initialize Web3 connections for each network
        self.connections = {
            "ethereum": Web3(Web3.HTTPProvider(RPC_URLS['ethereum'])),
            "base": Web3(Web3.HTTPProvider(RPC_URLS['base']))
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

    def _get_usdc_value(self, network: str, token_symbol: str, amount: str) -> tuple[str, dict]:
        """
        Get USDC value for a given token amount using CoWSwap
        Returns (usdc_amount, conversion_details)
        """
        try:
            # Get token contract address and decimals
            token_address = NETWORK_TOKENS[network][token_symbol]["address"]
            token_decimals = NETWORK_TOKENS[network][token_symbol]["decimals"]

            # Get quote from CoW Protocol
            result = get_quote(
                network=network,
                sell_token=token_address,
                buy_token=NETWORK_TOKENS[network]["USDC"]["address"],
                amount=amount,
                token_decimals=token_decimals,
                token_symbol=token_symbol
            )

            if result["quote"]:
                return result["quote"]["quote"]["buyAmount"], result["conversion_details"]

            return "0", result["conversion_details"]

        except Exception as e:
            return "0", {
                "source": "Error",
                "price_impact": "N/A",
                "rate": "0",
                "fee_percentage": "N/A",
                "fallback": True,
                "note": f"Technical error: {str(e)[:200]}"
            }

    def _convert_to_usdc(self, amount_18_decimals: str) -> str:
        """Convert amount from 18 decimals to 6 decimals (USDC)"""
        try:
            amount = Decimal(amount_18_decimals) / Decimal(10 ** 18)
            return str(int((amount * Decimal(10 ** 6)).quantize(Decimal('1.'))))
        except:
            return "0"

    def get_balances(self, address: str) -> Dict[str, Any]:
        """
        Get all token balances for an address.
        """
        # Remove the title print since it's handled in the aggregator
        # print("SPOT BALANCE MANAGER")
        
        print("\nProcessing method:")
        print("  - Querying native ETH balance")
        print("  - Querying balanceOf(address) for each token")
        print("  - Converting non-WETH tokens to WETH via CoWSwap")
        
        checksum_address = Web3.to_checksum_address(address)
        result = {}
        total_weth_wei = 0
        
        try:
            # Process each network
            for network in self.get_supported_networks():
                print(f"\nProcessing network: {network}")
                network_total = 0
                
                # Initialize network structure
                network_result = {}
                
                try:
                    # Check native ETH balance first
                    native_balance = self.connections[network].eth.get_balance(checksum_address)
                    
                    print(f"\nProcessing native ETH:")
                    print(f"  Amount: {Decimal(native_balance) / Decimal(10**18):.6f} ETH")
                    
                    if native_balance > 0:
                        # Native ETH is already in WETH terms
                        network_total += native_balance
                        total_weth_wei += native_balance
                        
                        # Add native ETH data
                        network_result["ETH"] = {
                            "amount": str(native_balance),
                            "decimals": 18,
                            "value": {
                                "WETH": {
                                    "amount": str(native_balance),
                                    "decimals": 18,
                                    "conversion_details": {
                                        "source": "Direct",
                                        "price_impact": "0.0000%",
                                        "rate": "1.000000",
                                        "fee_percentage": "0.0000%",
                                        "fallback": False,
                                        "note": "Direct 1:1 conversion (ETH = WETH)"
                                    }
                                }
                            }
                        }
                    else:
                        print("  → Balance is 0, skipping")
                except Exception as e:
                    print(f"Error checking native ETH balance: {str(e)}")
                
                # Process each token type
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
                        if token_symbol == "WETH":
                            # WETH is already in WETH terms
                            weth_amount = balance
                            conversion_details = {
                                "source": "Direct",
                                "price_impact": "0.0000%",
                                "rate": "1.000000",
                                "fee_percentage": "0.0000%",
                                "fallback": False,
                                "note": "Direct 1:1 conversion (WETH)"
                            }
                        else:
                            # Convert other tokens to WETH via CoWSwap
                            weth_amount, conversion_details = self._get_weth_value(network, token_symbol, str(balance))
                        
                        network_total += int(weth_amount)
                        total_weth_wei += int(weth_amount)
                        
                        # Add token data
                        network_result[token_symbol] = {
                            "amount": str(balance),
                            "decimals": decimals,
                            "value": {
                                "WETH": {
                                    "amount": str(weth_amount),
                                    "decimals": 18,
                                    "conversion_details": conversion_details
                                }
                            }
                        }
                    else:
                        print("  → Balance is 0, skipping")
                
                # Add network totals only if there are balances
                if network_total > 0:
                    network_result["totals"] = {
                        "wei": network_total,
                        "formatted": f"{network_total/1e18:.6f}"
                    }
                    # Only add network to result if it has balances
                    result[network] = network_result
            
            # Add protocol total only if there are balances
            if total_weth_wei > 0:
                result["totals"] = {
                    "wei": total_weth_wei,
                    "formatted": f"{total_weth_wei/1e18:.6f}"
                }

            print("\n[Spot] Calculation complete")
            return result
            
        except Exception as e:
            print(f"\nError processing spot balances: {str(e)}")
            return result

    def _get_weth_value(self, network: str, token_symbol: str, amount: str) -> tuple[str, dict]:
        """
        Get WETH value for a given token amount using CoWSwap
        Returns (weth_amount, conversion_details)
        """
        try:
            # Get token contract address and decimals
            token_address = NETWORK_TOKENS[network][token_symbol]["address"]
            token_decimals = NETWORK_TOKENS[network][token_symbol]["decimals"]

            # Get quote from CoW Protocol
            result = get_quote(
                network=network,
                sell_token=token_address,
                buy_token=NETWORK_TOKENS[network]["WETH"]["address"],
                amount=amount,
                token_decimals=token_decimals,
                token_symbol=token_symbol
            )

            if result["quote"]:
                return result["quote"]["quote"]["buyAmount"], result["conversion_details"]

            return "0", result["conversion_details"]

        except Exception as e:
            return "0", {
                "source": "Error",
                "price_impact": "N/A",
                "rate": "0",
                "fee_percentage": "N/A",
                "fallback": True,
                "note": f"Technical error: {str(e)[:200]}"
            }

    def format_balance(self, balance: int, decimals: int) -> str:
        """Format raw balance to human readable format"""
        return str(Decimal(balance) / Decimal(10**decimals))

    def get_supported_networks(self) -> list:
        """Implementation of abstract method"""
        return list(self.connections.keys())
    
    def get_protocol_info(self) -> dict:
        """Implementation of abstract method"""
        return {
            "name": "Spot Tokens",
            "tokens": {
                "USDC": {
                    network: NETWORK_TOKENS[network]["USDC"]
                    for network in self.get_supported_networks()
                },
                "USR": {
                    "ethereum": NETWORK_TOKENS["ethereum"]["USR"],
                    "base": NETWORK_TOKENS["base"]["PT-USR-24APR2025"]["underlying"]["USR"]
                },
                "crvUSD": {
                    "ethereum": NETWORK_TOKENS["ethereum"]["crvUSD"]
                },
                "GHO": {
                    "ethereum": NETWORK_TOKENS["ethereum"]["GHO"]
                },
                "fxUSD": {
                    "ethereum": NETWORK_TOKENS["ethereum"]["fxUSD"]
                },
                "scrvUSD": {
                    "ethereum": NETWORK_TOKENS["ethereum"]["scrvUSD"]
                },
                "CVX": {
                    "ethereum": NETWORK_TOKENS["ethereum"]["CVX"]
                },
                "CRV": {
                    "ethereum": NETWORK_TOKENS["ethereum"]["CRV"]
                },
                "PENDLE": {  # Add PENDLE token
                    "ethereum": NETWORK_TOKENS["ethereum"]["PENDLE"]
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