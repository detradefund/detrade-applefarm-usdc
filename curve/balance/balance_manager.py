"""
Curve Protocol balance manager - Version simplifiée.
Gère uniquement la récupération du balanceOf pour les LP tokens.
"""

from typing import Dict, Optional, List, Tuple, Any
from decimal import Decimal
import json
from pathlib import Path
import sys
from web3 import Web3
import argparse
import time
from datetime import datetime
import os
from dotenv import load_dotenv

# Add parent directory to PYTHONPATH
sys.path.append(str(Path(__file__).parent.parent.parent))

from config.networks import RPC_URLS, NETWORK_TOKENS
from curve.markets.pools import get_lp_token_address, get_pool_abi, get_available_pools, get_pool_address

# Load environment variables
load_dotenv()

# Get production address from environment variable
DEFAULT_ADDRESS = os.getenv('PRODUCTION_ADDRESS', "0x66DbceE7feA3287B3356227d6F3DfF3CeFbC6F3C")

class CurveBalanceManager:
    """
    Manages Curve Protocol interactions - Version simplifiée.
    Ne gère que la récupération des balances LP token.
    """
    
    def __init__(self, network: str, w3: Web3):
        """
        Initialize the Curve balance manager.
        
        Args:
            network: Network identifier ('etherlink', 'base', etc.)
            w3: Web3 instance for blockchain interaction
        """
        self.network = network
        self.w3 = w3
        self.abis_path = Path(__file__).parent.parent / "abis"
        
    def get_pool_tokens(self, pool_name: str) -> List[Dict[str, Any]]:
        """
        Détecte automatiquement les tokens qui constituent le pool en utilisant N_COINS() et coins(index).
        
        Args:
            pool_name: Name of the pool
            
        Returns:
            List of token info dictionaries with address, symbol, name, decimals
        """
        # Get pool configuration
        pool_address = get_pool_address(self.network, pool_name)
        abi_name = get_pool_abi(self.network, pool_name)
        
        # Load pool ABI
        with open(self.abis_path / f"{abi_name}.json") as f:
            pool_abi = json.load(f)
            
        pool_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(pool_address),
            abi=pool_abi
        )
        
        # Get number of coins in the pool
        try:
            n_coins = pool_contract.functions.N_COINS().call()
            print(f"🔍 Pool {pool_name} has {n_coins} tokens")
        except Exception as e:
            print(f"Error getting N_COINS: {e}")
            return []
        
        tokens = []
        
        # Use CurveStableSwap ABI for token info (contains ERC20 functions)
        with open(self.abis_path / "CurveStableSwap.json") as f:
            erc20_abi = json.load(f)
        
        # Get each token's information
        for i in range(n_coins):
            try:
                # Get token address
                token_address = pool_contract.functions.coins(i).call()
                print(f"  Token {i}: {token_address}")
                
                # Create token contract to get metadata
                token_contract = self.w3.eth.contract(
                    address=self.w3.to_checksum_address(token_address),
                    abi=erc20_abi
                )
                
                # Get token info
                try:
                    symbol = token_contract.functions.symbol().call()
                except:
                    symbol = f"TOKEN_{i}"
                    
                try:
                    name = token_contract.functions.name().call()
                except:
                    name = f"Token {i}"
                    
                try:
                    decimals = token_contract.functions.decimals().call()
                except:
                    decimals = 18  # Default
                
                # Check if we have this token in our NETWORK_TOKENS config
                known_token = None
                if self.network in NETWORK_TOKENS:
                    for token_key, token_data in NETWORK_TOKENS[self.network].items():
                        if token_data["address"].lower() == token_address.lower():
                            known_token = token_data
                            symbol = token_data["symbol"]
                            name = token_data["name"]
                            decimals = token_data["decimals"]
                            break
                
                token_info = {
                    "index": i,
                    "address": token_address,
                    "symbol": symbol,
                    "name": name,
                    "decimals": decimals,
                    "known_token": known_token is not None
                }
                
                tokens.append(token_info)
                print(f"    ✅ {symbol} ({name}) - {decimals} decimals")
                
            except Exception as e:
                print(f"  ❌ Error getting token {i}: {e}")
                continue
        
        return tokens
        
    def get_lp_balance(self, pool_name: str, user_address: str) -> Decimal:
        """
        Get the balance of LP tokens for a user.
        
        Args:
            pool_name: Name of the pool
            user_address: Address of the user
            
        Returns:
            LP token balance in wei
        """
        # Get pool configuration
        lp_token_address = get_lp_token_address(self.network, pool_name)
        abi_name = get_pool_abi(self.network, pool_name)
        
        # Load appropriate ABI
        with open(self.abis_path / f"{abi_name}.json") as f:
            curve_abi = json.load(f)
            
        lp_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(lp_token_address),
            abi=curve_abi
        )
        
        # Get LP token balance
        balance = lp_contract.functions.balanceOf(
            self.w3.to_checksum_address(user_address)
        ).call()
        
        return Decimal(balance)

    def get_pool_balances(self, pool_name: str) -> Dict[str, Any]:
        """
        Get complete pool information including tokens.
        
        Args:
            pool_name: Name of the pool
            
        Returns:
            Dictionary containing complete pool data
        """
        # Get basic pool info
        pool_info = {
            "pool_name": pool_name,
            "pool_address": get_pool_address(self.network, pool_name),
            "lp_token": get_lp_token_address(self.network, pool_name),
            "network": self.network
        }
        
        # Add token information
        tokens = self.get_pool_tokens(pool_name)
        pool_info["tokens"] = tokens
        pool_info["n_coins"] = len(tokens)
        
        return pool_info

    def simulate_withdrawals(self, pool_name: str, lp_amount_wei: int) -> List[Dict[str, Any]]:
        """
        Simule les retraits possibles avec calc_withdraw_one_coin pour chaque token du pool.
        
        Args:
            pool_name: Name of the pool
            lp_amount_wei: Amount of LP tokens to simulate withdrawal for (in wei)
            
        Returns:
            List of withdrawal simulations for each token
        """
        if lp_amount_wei == 0:
            return []
            
        # Get pool configuration
        pool_address = get_pool_address(self.network, pool_name)
        abi_name = get_pool_abi(self.network, pool_name)
        
        # Load pool ABI
        with open(self.abis_path / f"{abi_name}.json") as f:
            pool_abi = json.load(f)
            
        pool_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(pool_address),
            abi=pool_abi
        )
        
        # Get pool tokens info
        pool_tokens = self.get_pool_tokens(pool_name)
        
        withdrawal_simulations = []
        
        print(f"\n🧮 Simulating withdrawals for {lp_amount_wei / 1e18:.6f} LP tokens:")
        
        # Simulate withdrawal for each token
        for token in pool_tokens:
            try:
                # Call calc_withdraw_one_coin
                withdrawable_amount = pool_contract.functions.calc_withdraw_one_coin(
                    lp_amount_wei,  # _burn_amount
                    token['index']  # i (token index)
                ).call()
                
                # Convert to human readable amount
                token_amount = withdrawable_amount / (10 ** token['decimals'])
                
                simulation = {
                    "token_index": token['index'],
                    "token_address": token['address'],
                    "token_symbol": token['symbol'],
                    "token_name": token['name'],
                    "token_decimals": token['decimals'],
                    "withdrawable_amount_wei": str(withdrawable_amount),
                    "withdrawable_amount_formatted": f"{token_amount:.6f}",
                    "lp_tokens_burned": str(lp_amount_wei),
                    "lp_tokens_burned_formatted": f"{lp_amount_wei / 1e18:.6f}"
                }
                
                withdrawal_simulations.append(simulation)
                
                print(f"  💰 Option {token['index']}: Withdraw {token_amount:.6f} {token['symbol']}")
                print(f"     Token: {token['name']} ({token['address']})")
                
            except Exception as e:
                print(f"  ❌ Error simulating withdrawal for {token['symbol']}: {str(e)}")
                continue
        
        return withdrawal_simulations

    def simulate_withdrawals_with_pricing(self, pool_name: str, lp_amount_wei: int) -> List[Dict[str, Any]]:
        """
        Simule les retraits possibles avec pricing via CoWSwap pour optimiser la stratégie.
        
        Args:
            pool_name: Name of the pool
            lp_amount_wei: Amount of LP tokens to simulate withdrawal for (in wei)
            
        Returns:
            List of withdrawal simulations with pricing analysis
        """
        if lp_amount_wei == 0:
            return []
            
        # Get basic withdrawal simulations
        basic_simulations = self.simulate_withdrawals(pool_name, lp_amount_wei)
        
        # Import CoWSwap client
        try:
            from cowswap.cow_client import get_quote
        except ImportError:
            print("⚠️ CoWSwap client not available, skipping pricing analysis")
            return basic_simulations
        
        enhanced_simulations = []
        best_option = {"value_usdc": 0, "strategy": "", "details": {}}
        
        print(f"\n💰 Pricing Analysis (Bridge 1:1 + CoWSwap on Ethereum):")
        
        for sim in basic_simulations:
            token_symbol = sim['token_symbol']
            withdrawable_amount = int(sim['withdrawable_amount_wei'])
            
            enhanced_sim = sim.copy()
            
            if token_symbol == "USDC":
                # Direct USDC - no conversion needed
                usdc_value = withdrawable_amount
                enhanced_sim["final_value"] = {
                    "usdc_amount_wei": str(usdc_value),
                    "usdc_amount_formatted": f"{usdc_value / 1e6:.6f}",
                    "strategy": "Direct USDC withdrawal",
                    "conversion_needed": False
                }
                
                if usdc_value > best_option["value_usdc"]:
                    best_option = {
                        "value_usdc": usdc_value,
                        "strategy": "Direct USDC withdrawal",
                        "details": enhanced_sim
                    }
                
                print(f"  🟢 Direct USDC: {usdc_value / 1e6:.6f} USDC (no conversion)")
                
            elif token_symbol == "USDT":
                # USDT -> Bridge 1:1 -> Swap USDT→USDC on Ethereum
                try:
                    # Get Ethereum token addresses
                    eth_usdt = NETWORK_TOKENS["ethereum"]["USDT"]["address"]
                    eth_usdc = NETWORK_TOKENS["ethereum"]["USDC"]["address"]
                    
                    # Simulate CoWSwap quote on Ethereum
                    quote_result = get_quote(
                        network="ethereum",
                        sell_token=eth_usdt,
                        buy_token=eth_usdc,
                        amount=str(withdrawable_amount),  # 1:1 bridge assumption
                        token_decimals=6,
                        token_symbol="USDT"
                    )
                    
                    if quote_result["quote"] and 'quote' in quote_result["quote"]:
                        usdc_amount = int(quote_result["quote"]["quote"]["buyAmount"])
                        
                        enhanced_sim["final_value"] = {
                            "usdc_amount_wei": str(usdc_amount),
                            "usdc_amount_formatted": f"{usdc_amount / 1e6:.6f}",
                            "strategy": "USDT withdrawal + Bridge + CoWSwap",
                            "conversion_needed": True,
                            "bridge_assumption": "1:1 USDT Etherlink → Ethereum",
                            "cowswap_details": quote_result["conversion_details"]
                        }
                        
                        if usdc_amount > best_option["value_usdc"]:
                            best_option = {
                                "value_usdc": usdc_amount,
                                "strategy": "USDT withdrawal + Bridge + CoWSwap",
                                "details": enhanced_sim
                            }
                        
                        rate = float(quote_result["conversion_details"]["rate"])
                        print(f"  🔄 USDT→USDC: {usdc_amount / 1e6:.6f} USDC (rate: {rate:.6f})")
                        print(f"     Bridge: {withdrawable_amount / 1e6:.6f} USDT (1:1)")
                        print(f"     CoWSwap: {withdrawable_amount / 1e6:.6f} USDT → {usdc_amount / 1e6:.6f} USDC")
                        
                    else:
                        print(f"  ❌ Failed to get CoWSwap quote for USDT→USDC")
                        enhanced_sim["final_value"] = {
                            "error": "Failed to get conversion quote",
                            "strategy": "USDT withdrawal (no pricing available)"
                        }
                        
                except Exception as e:
                    print(f"  ❌ Error pricing USDT conversion: {str(e)}")
                    enhanced_sim["final_value"] = {
                        "error": str(e),
                        "strategy": "USDT withdrawal (pricing failed)"
                    }
            
            enhanced_simulations.append(enhanced_sim)
        
        # Add best strategy recommendation
        if best_option["strategy"]:
            print(f"\n🏆 Best Strategy: {best_option['strategy']}")
            print(f"   Final USDC: {best_option['value_usdc'] / 1e6:.6f}")
            
            for sim in enhanced_simulations:
                if sim.get("final_value", {}).get("strategy") == best_option["strategy"]:
                    sim["recommended"] = True
                else:
                    sim["recommended"] = False
        
        return enhanced_simulations

    def get_user_balances(self, pool_name: str, user_address: str) -> List[Tuple[str, str, Decimal]]:
        """
        Get user LP token balance.
        
        Args:
            pool_name: Name of the pool
            user_address: Address of the user
            
        Returns:
            List of tuples containing (address, symbol, balance)
        """
        lp_balance = self.get_lp_balance(pool_name, user_address)
        lp_token_address = get_lp_token_address(self.network, pool_name)
        
        return [
            (lp_token_address, f"{pool_name}-LP", lp_balance / Decimal(10**18))
        ]

    def get_complete_user_position(self, pool_name: str, user_address: str) -> Dict[str, Any]:
        """
        Get complete user position including LP balance and optimized withdrawal simulations.
        
        Args:
            pool_name: Name of the pool
            user_address: Address of the user
            
        Returns:
            Complete position data with withdrawal simulations and pricing analysis
        """
        # Get basic pool info
        pool_info = self.get_pool_balances(pool_name)
        
        # Get LP balance
        lp_balance_wei = self.get_lp_balance(pool_name, user_address)
        lp_balance_formatted = lp_balance_wei / Decimal(10**18)
        
        # Simulate withdrawals with pricing analysis if user has LP tokens
        withdrawal_simulations = []
        if lp_balance_wei > 0:
            withdrawal_simulations = self.simulate_withdrawals_with_pricing(pool_name, int(lp_balance_wei))
        
        return {
            "pool_info": pool_info,
            "lp_balance": {
                "amount_wei": str(lp_balance_wei),
                "amount_formatted": str(lp_balance_formatted),
                "decimals": 18
            },
            "withdrawal_simulations": withdrawal_simulations,
            "has_position": lp_balance_wei > 0
        }

def main():
    """Main function to demonstrate usage."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Check Curve LP balance')
    parser.add_argument('--address', type=str, default=DEFAULT_ADDRESS,
                      help=f'Address to check (default: {DEFAULT_ADDRESS})')
    parser.add_argument('--network', type=str, default='etherlink',
                      help='Network to use (default: etherlink)')
    parser.add_argument('--pool', type=str, default='USDCUSDT',
                      help='Pool to check (default: USDCUSDT)')
    parser.add_argument('--show-tokens', action='store_true',
                      help='Show detailed token information')
    parser.add_argument('--simulate-amount', type=float, default=None,
                      help='Simulate withdrawal for specific LP token amount')
    args = parser.parse_args()
    
    # Initialize Web3
    rpc_url = RPC_URLS.get(args.network, "https://node.ghostnet.etherlink.com")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        print(f"Failed to connect to {args.network} network")
        return
    
    # Initialize balance manager
    balance_manager = CurveBalanceManager(args.network, w3)
    
    try:
        # Check if pool exists
        available_pools = get_available_pools(args.network)
        if args.pool not in available_pools:
            print(f"Pool {args.pool} not found for network {args.network}")
            print(f"Available pools: {available_pools}")
            return
        
        # Get complete user position
        print(f"\n=== Complete Position Analysis ===")
        complete_position = balance_manager.get_complete_user_position(args.pool, args.address)
        
        # Show pool info
        pool_info = complete_position["pool_info"]
        print(f"Pool: {pool_info['pool_name']}")
        print(f"Address: {pool_info['pool_address']}")
        print(f"LP Token: {pool_info['lp_token']}")
        print(f"Network: {pool_info['network']}")
        print(f"Number of tokens: {pool_info['n_coins']}")
        
        # Show tokens if requested
        if args.show_tokens:
            print(f"\n=== Pool Tokens ===")
            for token in pool_info['tokens']:
                status = "✅ Known" if token['known_token'] else "🔍 Detected"
                print(f"  {token['index']}: {token['symbol']} ({token['name']}) {status}")
                print(f"     Address: {token['address']}")
                print(f"     Decimals: {token['decimals']}")
        
        # Show LP balance
        print(f"\n=== LP Token Balance ===")
        lp_balance = complete_position["lp_balance"]
        print(f"  {args.pool}-LP: {lp_balance['amount_formatted']}")
        print(f"  Wei: {lp_balance['amount_wei']}")
        
        # Show withdrawal simulations
        if complete_position["withdrawal_simulations"]:
            print(f"\n=== Withdrawal Simulations ===")
            for sim in complete_position["withdrawal_simulations"]:
                print(f"  Option {sim['token_index']}: {sim['withdrawable_amount_formatted']} {sim['token_symbol']}")
                print(f"    Token: {sim['token_name']}")
                print(f"    Address: {sim['token_address']}")
        
        # Manual simulation if requested
        if args.simulate_amount is not None:
            print(f"\n=== Custom Simulation ===")
            simulate_wei = int(args.simulate_amount * 1e18)
            simulations = balance_manager.simulate_withdrawals(args.pool, simulate_wei)
            print(f"Simulating withdrawal of {args.simulate_amount:.6f} LP tokens:")
            for sim in simulations:
                print(f"  {sim['token_symbol']}: {sim['withdrawable_amount_formatted']}")
        
        # Print full JSON if requested
        if args.show_tokens:
            print(f"\n=== Complete Position JSON ===")
            print(json.dumps(complete_position, indent=2, default=str))
            
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 