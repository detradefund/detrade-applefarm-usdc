"""
Curve Protocol reward manager.
Handles interactions with Curve gauges and manages reward tokens.
"""

from typing import Dict, Optional, List, Tuple, Any
from decimal import Decimal
import json
from pathlib import Path
from web3 import Web3

from cowswap.cow_client import get_quote
from config.networks import NETWORK_TOKENS

class CurveRewardManager:
    """
    Manages Curve Protocol reward interactions and tracking.
    """
    
    def __init__(self, network: str, w3: Web3):
        """
        Initialize the Curve reward manager.
        
        Args:
            network: Network identifier ('ethereum' or 'base')
            w3: Web3 instance for blockchain interaction
        """
        self.network = network
        self.w3 = w3
        self.network_tokens = NETWORK_TOKENS
        self.abis_path = Path(__file__).parent.parent / "abis"

    def get_reward_tokens(self, pool_name: str) -> List[Tuple[str, str, int]]:
        """
        Get all reward tokens from the gauge by querying reward_tokens(index) until we get the zero address.
        Maps the token addresses to their symbols and decimals using NETWORK_TOKENS.
        
        Args:
            pool_name: Name of the pool
            
        Returns:
            List of tuples containing (token_address, token_symbol, decimals)
        """
        gauge_address = self._get_gauge_address(pool_name)
        
        # Load Child Liquidity Gauge ABI
        with open(self.abis_path / "Child Liquidity Gauge.json") as f:
            gauge_abi = json.load(f)
            
        gauge_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(gauge_address),
            abi=gauge_abi
        )
        
        reward_tokens = []
        index = 0
        
        while True:
            try:
                token_address = gauge_contract.functions.reward_tokens(index).call()
                
                # Check if we've reached the end (zero address)
                if token_address == "0x0000000000000000000000000000000000000000":
                    break
                    
                # Map token address to symbol and decimals
                token_info = self._get_token_info(token_address)
                if token_info:
                    reward_tokens.append(token_info)
                    
                index += 1
            except Exception:
                # If we get an error, we've probably reached the end
                break
                
        return reward_tokens

    def get_claimable_rewards(self, pool_name: str, user_address: str) -> Dict[str, Any]:
        """
        Get claimable rewards for a user from the gauge.
        
        Args:
            pool_name: Name of the pool
            user_address: Address of the user
            
        Returns:
            Dictionary containing structured reward information
        """
        gauge_address = self._get_gauge_address(pool_name)
        
        result = {
            "curve": {
                "base": {
                    pool_name: {
                        "rewards": {},
                        "totals": {
                            "wei": 0,
                            "formatted": "0.000000"
                        }
                    }
                }
            }
        }
        
        try:
            # Load Child Liquidity Gauge ABI
            with open(self.abis_path / "Child Liquidity Gauge.json") as f:
                gauge_abi = json.load(f)
                
            gauge_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(gauge_address),
                abi=gauge_abi
            )
            
            rewards_total = 0
            
            # First check CRV rewards
            try:
                claimable = gauge_contract.functions.claimable_tokens(
                    self.w3.to_checksum_address(user_address)
                ).call()
                
                crv_decimal = Decimal(claimable) / Decimal(10**18)
                if crv_decimal > 0:
                    crv_address = "0x8Ee73c484A26e0A5df2Ee2a4960B789967dd0415"  # CRV address on Base
                    
                    # Get CRV price in ETH using CoWSwap
                    quote_result = self._get_quote_with_fallback(
                        crv_address, claimable, 18, "CRV"
                    )
                    
                    if quote_result:
                        eth_value = quote_result["amount"]
                        result["curve"]["base"][pool_name]["rewards"]["CRV"] = {
                            "amount": claimable,
                            "decimals": 18,
                            "value": {
                                "WETH": quote_result
                            },
                            "totals": {
                                "wei": eth_value,
                                "formatted": f"{eth_value/1e18:.6f}"
                            }
                        }
                        rewards_total += eth_value
                    
            except Exception as e:
                print(f"Error checking CRV rewards: {str(e)}")
            
            # Then check other rewards
            try:
                reward_count = gauge_contract.functions.reward_count().call()
                
                for i in range(reward_count):
                    try:
                        token_address = gauge_contract.functions.reward_tokens(i).call()
                        
                        # Skip CRV token as we already checked it
                        if token_address.lower() == "0x8Ee73c484A26e0A5df2Ee2a4960B789967dd0415".lower():
                            continue
                        
                        # Get reward data
                        reward_data = gauge_contract.functions.reward_data(
                            self.w3.to_checksum_address(token_address)
                        ).call()
                        
                        # Get claimable amount
                        claimable = gauge_contract.functions.claimable_reward(
                            self.w3.to_checksum_address(user_address),
                            self.w3.to_checksum_address(token_address)
                        ).call()
                        
                        # Get token info
                        token_info = self._get_token_info(token_address)
                        if token_info and claimable > 0:
                            addr, symbol, decimals = token_info
                            
                            # Get token price in ETH using CoWSwap
                            quote_result = self._get_quote_with_fallback(
                                addr, claimable, decimals, symbol
                            )
                            
                            if quote_result:
                                eth_value = quote_result["amount"]
                                result["curve"]["base"][pool_name]["rewards"][symbol] = {
                                    "amount": claimable,
                                    "decimals": decimals,
                                    "value": {
                                        "WETH": quote_result
                                    },
                                    "totals": {
                                        "wei": eth_value,
                                        "formatted": f"{eth_value/1e18:.6f}"
                                    }
                                }
                                rewards_total += eth_value
                                
                    except Exception as e:
                        print(f"Error checking reward token {i}: {str(e)}")
                        continue
                        
            except Exception as e:
                print(f"Error checking other rewards: {str(e)}")
                
            # Update totals
            result["curve"]["base"][pool_name]["totals"] = {
                "wei": rewards_total,
                "formatted": f"{rewards_total/1e18:.6f}"
            }
            
            # Add protocol total
            if rewards_total > 0:
                result["curve"]["totals"] = {
                    "wei": rewards_total,
                    "formatted": f"{rewards_total/1e18:.6f}"
                }
                
        except Exception as e:
            print(f"Error loading gauge: {str(e)}")
            
        return result

    def _get_token_info(self, token_address: str) -> Optional[Tuple[str, str, int]]:
        """
        Helper method to get token information from NETWORK_TOKENS.
        
        Args:
            token_address: Address of the token
            
        Returns:
            Tuple of (token_address, token_symbol, decimals) or None if not found
        """
        addr_lower = token_address.lower()
        
        # Search for token in NETWORK_TOKENS
        for token_name, token_data in NETWORK_TOKENS[self.network].items():
            if token_data["address"].lower() == addr_lower:
                return (
                    token_address,
                    token_data["symbol"],
                    token_data["decimals"]
                )
                
        return None

    def _get_quote_with_fallback(self, token_address: str, amount: int, decimals: int, symbol: str) -> Dict[str, Any]:
        """
        Gets ETH conversion quote for tokens.
        Uses the centralized quote logic from cow_client.py
        """
        result = get_quote(
            network="base",
            sell_token=token_address,
            buy_token=self.network_tokens["base"]["WETH"]["address"],
            amount=str(int(amount)),
            token_decimals=decimals,
            token_symbol=symbol,
            context="spot"
        )

        if result["quote"]:
            return {
                "amount": int(result["quote"]["quote"]["buyAmount"]),
                "decimals": 18,
                "conversion_details": result["conversion_details"]
            }
        
        return {
            "amount": 0,
            "decimals": 18,
            "conversion_details": result["conversion_details"]
        }

    def _get_gauge_address(self, pool_name: str) -> str:
        """Get gauge address from markets.json"""
        markets_path = Path(__file__).parent.parent / "markets" / "markets.json"
        with open(markets_path) as f:
            markets_config = json.load(f)
        return markets_config["gauge"] 