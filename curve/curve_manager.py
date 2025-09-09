import sys
from pathlib import Path
from typing import Dict, Any
import json
from decimal import Decimal
from web3 import Web3
import time

# Add parent directory to PYTHONPATH
root_path = str(Path(__file__).parent.parent)
sys.path.append(root_path)

from curve.markets.pools import CURVE_POOLS
from curve.balance.balance_manager import CurveBalanceManager
from config.networks import RPC_URLS

class CurveManager:
    """Manager for Curve pool interactions and balance checking."""
    
    def __init__(self, address: str, network: str = "etherlink", pool_name: str = "USDCUSDT"):
        self.address = Web3.to_checksum_address(address)
        self.network = network
        self.pool_name = pool_name
        
        # Initialize Web3 and balance manager
        rpc_url = RPC_URLS.get(network, "https://node.ghostnet.etherlink.com")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise Exception(f"Failed to connect to {network} network")
            
        self.balance_manager = CurveBalanceManager(network, self.w3)
        
    def run(self) -> Dict[str, Any]:
        """Run the Curve position analysis."""
        print("\n=== Curve Position Manager ===")
        print(f"Wallet: {self.address}")
        print(f"Network: {self.network}")
        print(f"Pool: {self.pool_name}")
        print(f"Time: {time.strftime('%Y-%m-%dT%H:%M:%S.%f')}")
        
        try:
            # Get complete user position
            position = self.balance_manager.get_complete_user_position(self.pool_name, self.address)
            
            # Format response
            pool_info = position["pool_info"]
            result = {
                "positions": {
                    self.pool_name: {
                        "pool_address": pool_info["pool_address"],
                        "lp_balance": position["lp_balance"],
                        "pool_tokens": pool_info.get("tokens", []),
                        "n_coins": pool_info.get("n_coins", 0),
                        "withdrawal_simulations": position.get("withdrawal_simulations", [])
                    }
                }
            }
            
            print("✓ Position data retrieved successfully")
            return result
            
        except Exception as e:
            print(f"Error getting Curve position: {str(e)}")
            return {}