import requests
from typing import Dict, Any, Optional, List
from decimal import Decimal

import sys
from pathlib import Path

# Add parent directory to PYTHONPATH for importing from spot
root_path = str(Path(__file__).parent.parent)
sys.path.append(root_path)

from spot.balance_manager import SpotBalanceManager

class MerklClient:
    """Client for interacting with the Merkl API."""
    
    BASE_URL = "https://api.merkl.xyz/v4"
    
    # Token decimals mapping
    TOKEN_DECIMALS = {
        "WXTZ": 18,
        "applXTZ": 18,
        "applstXTZ": 6,
        "stXTZ": 6,
        "USDC": 6,
        "USDT": 6
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.spot_manager = SpotBalanceManager()  # Pour obtenir les taux de conversion
    
    def get_user_rewards(self, user_address: str, chain_id: int) -> Dict[str, Any]:
        """Fetch rewards for a specific user on a specific chain."""
        url = f"{self.BASE_URL}/users/{user_address}/rewards"
        params = {"chainId": chain_id}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()

    def format_amount(self, amount: str, token_symbol: str = None) -> str:
        """Format a token amount from wei to human readable format."""
        if not amount:
            return "0"
        
        # Get token decimals, default to 18 if token not in mapping
        decimals = self.TOKEN_DECIMALS.get(token_symbol, 18) if token_symbol else 18
        amount_decimal = Decimal(amount) / Decimal(10 ** decimals)
        return f"{amount_decimal:.6f}"

    @staticmethod
    def calculate_claimable_now(amount: str, claimed: str) -> str:
        """Calculate amount claimable now (amount - claimed)."""
        amount_dec = Decimal(amount if amount else "0")
        claimed_dec = Decimal(claimed if claimed else "0")
        return str(max(amount_dec - claimed_dec, 0))

    def convert_to_usdc(self, amount: str, token_symbol: str) -> tuple[str, dict]:
        """
        Convert a token amount to USDC using the same logic as SpotBalanceManager
        Returns (usdc_amount, conversion_details)
        """
        if token_symbol == "USDC":
            return amount, {
                "source": "Direct",
                "price_impact": "0.0000%",
                "rate": "1.000000",
                "fee_percentage": "0.0000%",
                "fallback": False,
                "note": "1 USDC = 1 USDC (no conversion needed)"
            }
        
        # Get conversion rates
        wxtz_usdc_rate, price_details = self.spot_manager._get_wxtz_usdc_price()
        
        if token_symbol == "applstXTZ":
            # Pour applstXTZ, on doit d'abord convertir en WXTZ via stXTZ
            stxtz_wxtz_rate, stxtz_details = self.spot_manager._get_stxtz_wxtz_price()
            
            # Convert applstXTZ to WXTZ (via stXTZ)
            wxtz_amount = str(int(Decimal(amount) * Decimal(stxtz_wxtz_rate) * Decimal(10**12)))  # 6 to 18 decimals
            
            # Convert WXTZ to USDC
            usdc_amount = str(int(Decimal(wxtz_amount) * Decimal(wxtz_usdc_rate) * Decimal(10**6) / Decimal(10**18)))
            
            return usdc_amount, {
                "source": "Via stXTZ/WXTZ pool",
                "price_impact": "Two-step conversion",
                "rate": f"{float(Decimal(stxtz_wxtz_rate) * Decimal(wxtz_usdc_rate)):.6f}",
                "fee_percentage": "N/A",
                "fallback": False,
                "note": f"1 applstXTZ = {stxtz_wxtz_rate} WXTZ = {wxtz_usdc_rate} USDC"
            }
        else:
            # Pour les autres tokens (WXTZ, applXTZ), conversion directe en USDC
            wxtz_amount = amount  # Déjà en WXTZ ou conversion 1:1
            usdc_amount = str(int(Decimal(wxtz_amount) * Decimal(wxtz_usdc_rate) * Decimal(10**6) / Decimal(10**18)))
            
            return usdc_amount, price_details

    def get_claimable_rewards(self, user_address: str, chain_id: int) -> Dict[str, Any]:
        """Get a structured dictionary of all claimable rewards."""
        rewards_data = self.get_user_rewards(user_address, chain_id)
        result = {"etherlink": [], "totals": {"wei": 0, "formatted": "0"}}
        
        total_wei = 0
        
        for chain_data in rewards_data:
            for reward in chain_data['rewards']:
                token = reward['token']
                token_symbol = token['symbol']
                
                # Calculate total claimable
                total_claimable_wei = self.calculate_claimable_now(
                    reward['amount'],
                    reward['claimed']
                )
                token_symbol = token['symbol']
                total_claimable = self.format_amount(total_claimable_wei, token_symbol)
                
                # Convert to USDC using spot manager logic
                usdc_amount, conversion_details = self.convert_to_usdc(total_claimable_wei, token_symbol)
                usdc_formatted = self.format_amount(usdc_amount, "USDC")
                
                # Skip if USDC value is 0
                if usdc_formatted == "0.000000":
                    continue
                
                reward_data = {
                    "token": token_symbol,
                    "token_address": token['address'],
                    "total_claimable": {
                        "amount": total_claimable,
                        "amount_wei": total_claimable_wei,
                        "usdc_value": {
                            "amount": usdc_amount,
                            "formatted": usdc_formatted,
                            "conversion_details": conversion_details
                        }
                    },
                    "campaigns": []
                }
                
                campaign_total_wei = 0
                
                # Get campaign details
                for breakdown in reward['breakdowns']:
                    campaign_claimable_wei = self.calculate_claimable_now(
                        breakdown.get('amount', '0'),
                        breakdown.get('claimed', '0')
                    )
                    
                    if Decimal(campaign_claimable_wei) > 0:
                        campaign_claimable = self.format_amount(campaign_claimable_wei, token_symbol)
                        
                        # Convert campaign amount to USDC
                        campaign_usdc_amount, campaign_conversion_details = self.convert_to_usdc(campaign_claimable_wei, token_symbol)
                        campaign_usdc_formatted = self.format_amount(campaign_usdc_amount, "USDC")
                        campaign_total_wei += int(campaign_usdc_amount)  # Add USDC amount to total
                        
                        reward_data["campaigns"].append({
                            "id": breakdown['campaignId'][:10],
                            "type": breakdown['reason'],
                            "claimable": {
                                "amount": campaign_claimable,
                                "amount_wei": campaign_claimable_wei,
                                "usdc_value": {
                                    "amount": campaign_usdc_amount,
                                    "formatted": campaign_usdc_formatted,
                                    "conversion_details": campaign_conversion_details
                                }
                            }
                        })
                
                total_wei += campaign_total_wei
                result["etherlink"].append(reward_data)
        
        # Update totals
        result["totals"] = {
            "wei": total_wei,
            "formatted": self.format_amount(str(total_wei))
        }
        
        return result

def print_rewards_summary(rewards_data: list):
    """Print a formatted summary of the rewards data."""
    for chain_data in rewards_data:
        for reward in chain_data['rewards']:
            token = reward['token']
            token_price = float(token['price'])
            
            # Calculate claimable now
            claimable_now = MerklClient.calculate_claimable_now(
                reward['amount'],
                reward['claimed']
            )
            
            # Format amounts
            token_symbol = token['symbol']
            claimable_now_fmt = client.format_amount(claimable_now, token_symbol)
            pending_fmt = client.format_amount(reward['pending'], token_symbol)
            claimed_fmt = client.format_amount(reward['claimed'], token_symbol)
            
            print(f"\nRewards Summary ({token['symbol']})")
            print("-" * 50)
            
            print(f"Token Price: ${token_price:.6f}")
            print("\nStatus:")
            print(f"Claimable Now:   {claimable_now_fmt:>12} {token['symbol']} "
                  f"(${float(Decimal(claimable_now_fmt) * Decimal(str(token_price))):.2f})")
            print(f"Claimable Soon:  {pending_fmt:>12} {token['symbol']} "
                  f"(${float(Decimal(pending_fmt) * Decimal(str(token_price))):.2f})")
            print(f"Already Claimed: {claimed_fmt:>12} {token['symbol']} "
                  f"(${float(Decimal(claimed_fmt) * Decimal(str(token_price))):.2f})")
            
            print("\nActive Campaigns:")
            for breakdown in reward['breakdowns']:
                campaign_claimable = MerklClient.calculate_claimable_now(
                    breakdown.get('amount', '0'),
                    breakdown.get('claimed', '0')
                )
                
                if Decimal(campaign_claimable) > 0 or Decimal(breakdown['pending']) > 0:
                    print(f"\nCampaign {breakdown['campaignId'][:10]}...")
                    print(f"Type: {breakdown['reason']}")
                    
                    if Decimal(campaign_claimable) > 0:
                        claimable_fmt = client.format_amount(campaign_claimable, token_symbol)
                        print(f"Claimable Now:   {claimable_fmt:>12} {token['symbol']} "
                              f"(${float(Decimal(claimable_fmt) * Decimal(str(token_price))):.2f})")
                    
                    if Decimal(breakdown['pending']) > 0:
                        pending_fmt = client.format_amount(breakdown['pending'], token_symbol)
                        print(f"Claimable Soon:  {pending_fmt:>12} {token['symbol']} "
                              f"(${float(Decimal(pending_fmt) * Decimal(str(token_price))):.2f})")

# Example usage:
if __name__ == "__main__":
    # Example address and chain ID (Etherlink)
    TEST_ADDRESS = "0xA6548c1F8D3F3c97f75deE8D030B942b6c88B6ce"
    ETHERLINK_CHAIN_ID = 42793
    
    client = MerklClient()
    try:
        # Get and print formatted summary
        rewards = client.get_user_rewards(TEST_ADDRESS, ETHERLINK_CHAIN_ID)
        print_rewards_summary(rewards)
        
        # Get structured claimable rewards
        print("\nStructured Claimable Rewards Data:")
        print("-" * 50)
        claimable_rewards = client.get_claimable_rewards(TEST_ADDRESS, ETHERLINK_CHAIN_ID)
        import json
        print(json.dumps(claimable_rewards, indent=2))
    except requests.exceptions.RequestException as e:
        print(f"Error fetching rewards: {e}")