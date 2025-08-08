"""
Master script to manage Curve positions - Version simplifiée.
Gère uniquement les balances LP token sans rewards ni conversions.
Détecte automatiquement les tokens du pool.
"""
from typing import Dict, List, Optional, Any
from web3 import Web3
from decimal import Decimal
import json
import os
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
import sys

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from curve.balance.balance_manager import CurveBalanceManager
from curve.markets.pools import get_available_pools, get_supported_networks
from config.networks import RPC_URLS

# Load environment variables
load_dotenv()

class CurveManager:
    def __init__(self, wallet_address: str, network: str = "etherlink", pool_name: str = "USDCUSDT"):
        """
        Initialize the CurveManager - Version simplifiée avec détection automatique des tokens.
        
        Args:
            wallet_address: The wallet address to manage positions for
            network: Network to use (default: etherlink)
            pool_name: Pool to check (default: USDCUSDT)
        """
        self.wallet_address = wallet_address
        self.network = network
        self.pool_name = pool_name
        self.positions = {}
        self.pool_info = {}
        
        # Validate network and pool
        if network not in get_supported_networks():
            raise ValueError(f"Network {network} not supported. Available: {get_supported_networks()}")
            
        available_pools = get_available_pools(network)
        if pool_name not in available_pools:
            raise ValueError(f"Pool {pool_name} not found for network {network}. Available: {available_pools}")
        
        # Initialize Web3 connection
        rpc_url = RPC_URLS.get(self.network, "https://node.ghostnet.etherlink.com")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {self.network} network")
            
        self.balance_manager = CurveBalanceManager(self.network, self.w3)
        
    def analyze_pool(self):
        """Analyser le pool et détecter automatiquement les tokens."""
        print(f"\n=== Analyzing Pool {self.pool_name} ===")
        
        try:
            # Get complete pool information including token detection
            self.pool_info = self.balance_manager.get_pool_balances(self.pool_name)
            
            print(f"Pool: {self.pool_info['pool_name']}")
            print(f"Address: {self.pool_info['pool_address']}")
            print(f"Network: {self.pool_info['network']}")
            print(f"Number of tokens: {self.pool_info['n_coins']}")
            
            print(f"\n📋 Pool composition:")
            for token in self.pool_info['tokens']:
                status = "✅" if token['known_token'] else "🔍"
                print(f"  {token['index']}: {token['symbol']} ({token['name']}) {status}")
                print(f"     Address: {token['address']}")
                print(f"     Decimals: {token['decimals']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error analyzing pool: {str(e)}")
            return False
        
    def check_balances(self):
        """Check LP token balances et simule les retraits possibles."""
        print(f"\n=== Checking LP Token Balances ===")
        self.positions = {}
        
        try:
            # Get complete user position with withdrawal simulations
            complete_position = self.balance_manager.get_complete_user_position(self.pool_name, self.wallet_address)
            
            if complete_position["has_position"]:
                self.positions[self.pool_name] = {
                    "pool_address": complete_position["pool_info"]["pool_address"],
                    "lp_token_address": complete_position["pool_info"]["lp_token"],
                    "network": complete_position["pool_info"]["network"],
                    "pool_tokens": complete_position["pool_info"]["tokens"],
                    "n_coins": complete_position["pool_info"]["n_coins"],
                    "lp_balance": complete_position["lp_balance"],
                    "withdrawal_simulations": complete_position["withdrawal_simulations"]
                }
                
                lp_amount = float(complete_position["lp_balance"]["amount_formatted"])
                print(f"✅ Found LP tokens for {self.pool_name}")
                print(f"   Balance: {lp_amount:.6f} {self.pool_name}-LP")
                print(f"   Wei: {complete_position['lp_balance']['amount_wei']}")
                
                # Show withdrawal options
                if complete_position["withdrawal_simulations"]:
                    print(f"\n🔄 Withdrawal Options:")
                    for sim in complete_position["withdrawal_simulations"]:
                        print(f"   Option {sim['token_index']}: {sim['withdrawable_amount_formatted']} {sim['token_symbol']}")
                        print(f"     → Burn {sim['lp_tokens_burned_formatted']} LP tokens")
                
                # Show which tokens this LP balance represents
                print(f"\n💎 Represents liquidity in:")
                for token in complete_position["pool_info"]["tokens"]:
                    print(f"     - {token['symbol']} ({token['address']})")
                    
            else:
                print(f"❌ No LP tokens found for {self.pool_name}")
            
        except Exception as e:
            print(f"Error checking balances for pool {self.pool_name}: {str(e)}")
        
        return self.positions
    
    def get_raw_data(self):
        """
        Get raw position data without any processing.
        
        Returns:
            dict: Raw position data
        """
        if not self.positions:
            print("\n⚠️ No positions found")
            return None
            
        print("\n=== Raw Position Data ===")
        
        results = {
            "wallet_address": self.wallet_address,
            "network": self.network,
            "pool_name": self.pool_name,
            "timestamp": datetime.now().isoformat(),
            "pool_analysis": {
                "pool_address": self.pool_info.get("pool_address"),
                "lp_token_address": self.pool_info.get("lp_token"),
                "n_coins": self.pool_info.get("n_coins"),
                "tokens": self.pool_info.get("tokens", [])
            },
            "positions": self.positions
        }
        
        return results
    
    def run(self):
        """
        Run the complete process - Version simplifiée avec analyse des tokens.
        
        Returns:
            dict: Complete raw data
        """
        print("\n=== Curve Position Manager - Simplified with Token Detection ===")
        print(f"Wallet: {self.wallet_address}")
        print(f"Network: {self.network}")
        print(f"Pool: {self.pool_name}")
        print(f"Time: {datetime.now().isoformat()}")
        
        # First analyze the pool
        if not self.analyze_pool():
            print("❌ Pool analysis failed")
            return None
        
        # Then check balances
        self.check_balances()
        results = self.get_raw_data()
        
        print("\n=== Process Complete ===")
        return results

def main():
    """Example usage of the simplified CurveManager."""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Curve Position Manager - Simplified with Token Detection')
    parser.add_argument('--address', type=str, default=os.getenv('PRODUCTION_ADDRESS'),
                      help='Wallet address to check')
    parser.add_argument('--network', type=str, default='etherlink',
                      help='Network to use (default: etherlink)')
    parser.add_argument('--pool', type=str, default='USDCUSDT',
                      help='Pool to check (default: USDCUSDT)')
    parser.add_argument('--list-networks', action='store_true',
                      help='List available networks')
    parser.add_argument('--list-pools', type=str, metavar='NETWORK',
                      help='List available pools for a network')
    parser.add_argument('--analyze-only', action='store_true',
                      help='Only analyze pool composition without checking balances')
    
    args = parser.parse_args()
    
    # Handle list commands
    if args.list_networks:
        print("Available networks:")
        for network in get_supported_networks():
            pools = get_available_pools(network)
            print(f"  {network}: {pools}")
        return
        
    if args.list_pools:
        try:
            pools = get_available_pools(args.list_pools)
            print(f"Available pools for {args.list_pools}: {pools}")
        except ValueError as e:
            print(f"Error: {e}")
        return
    
    # Analyze only mode
    if args.analyze_only:
        try:
            print(f"\n=== Pool Analysis Only ===")
            manager = CurveManager("0x0000000000000000000000000000000000000000", args.network, args.pool)  # Dummy address
            manager.analyze_pool()
            
            print(f"\n=== Pool Composition JSON ===")
            print(json.dumps(manager.pool_info, indent=2, default=str))
            
        except Exception as e:
            print(f"\n✗ Error: {str(e)}")
        return
    
    # Validate address for balance checking
    if not args.address:
        print("Error: No wallet address provided. Set PRODUCTION_ADDRESS env var or use --address")
        return
    
    try:
        print(f"\n=== Testing Curve Manager ===")
        print(f"Address: {args.address}")
        print(f"Network: {args.network}")
        print(f"Pool: {args.pool}")
        
        manager = CurveManager(args.address, args.network, args.pool)
        results = manager.run()

        # Display results
        if results:
            print("\n=== Complete Results JSON ===")
            print(json.dumps(results, indent=2, default=str))
        else:
            print("\n=== No LP tokens found ===")
        
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        print("\nFull error traceback:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 