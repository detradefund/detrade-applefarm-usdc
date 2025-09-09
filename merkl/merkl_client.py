import requests
from typing import Dict, Any, Optional, List
from decimal import Decimal

class MerklClient:
    """Client for interacting with the Merkl API."""
    
    BASE_URL = "https://api.merkl.xyz/v4"
    
    def __init__(self):
        self.session = requests.Session()
    
    def get_user_rewards(self, user_address: str, chain_id: int) -> Dict[str, Any]:
        """Fetch rewards for a specific user on a specific chain."""
        url = f"{self.BASE_URL}/users/{user_address}/rewards"
        params = {"chainId": chain_id}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()

    @staticmethod
    def format_amount(amount: str, decimals: int = 18) -> str:
        """Format a token amount from wei to human readable format."""
        if not amount:
            return "0"
        amount_decimal = Decimal(amount) / Decimal(10 ** decimals)
        return f"{amount_decimal:.6f}"

    @staticmethod
    def calculate_claimable_now(amount: str, claimed: str) -> str:
        """Calculate amount claimable now (amount - claimed)."""
        amount_dec = Decimal(amount if amount else "0")
        claimed_dec = Decimal(claimed if claimed else "0")
        return str(max(amount_dec - claimed_dec, 0))

    def get_claimable_rewards(self, user_address: str, chain_id: int) -> Dict[str, Any]:
        """Get a structured dictionary of all claimable rewards."""
        rewards_data = self.get_user_rewards(user_address, chain_id)
        result = {"etherlink": [], "totals": {"wei": 0, "formatted": "0"}}
        
        total_wei = 0
        
        for chain_data in rewards_data:
            for reward in chain_data['rewards']:
                token = reward['token']
                token_price = float(token['price'])
                
                # Calculate total claimable
                total_claimable_wei = self.calculate_claimable_now(
                    reward['amount'],
                    reward['claimed']
                )
                total_claimable = self.format_amount(total_claimable_wei)
                
                reward_data = {
                    "token": token['symbol'],
                    "token_address": token['address'],
                    "token_price": token_price,
                    "total_claimable": {
                        "amount": total_claimable,
                        "amount_wei": total_claimable_wei,
                        "usd_value": float(Decimal(total_claimable) * Decimal(str(token_price)))
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
                        campaign_claimable = self.format_amount(campaign_claimable_wei)
                        campaign_total_wei += int(campaign_claimable_wei)
                        
                        reward_data["campaigns"].append({
                            "id": breakdown['campaignId'][:10],
                            "type": breakdown['reason'],
                            "claimable": {
                                "amount": campaign_claimable,
                                "amount_wei": campaign_claimable_wei,
                                "usd_value": float(Decimal(campaign_claimable) * Decimal(str(token_price)))
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
            claimable_now_fmt = MerklClient.format_amount(claimable_now)
            pending_fmt = MerklClient.format_amount(reward['pending'])
            claimed_fmt = MerklClient.format_amount(reward['claimed'])
            
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
                        claimable_fmt = MerklClient.format_amount(campaign_claimable)
                        print(f"Claimable Now:   {claimable_fmt:>12} {token['symbol']} "
                              f"(${float(Decimal(claimable_fmt) * Decimal(str(token_price))):.2f})")
                    
                    if Decimal(breakdown['pending']) > 0:
                        pending_fmt = MerklClient.format_amount(breakdown['pending'])
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