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
from spot.balance_manager import SpotBalanceManager
from curve.curve_manager import CurveManager
from merkl.merkl_client import MerklClient

class BalanceAggregator:
    """
    Master aggregator that combines balances from multiple protocols.
    Currently supports:
    - Superlend (Etherlink) - slUSDC monitoring
    - Spot Tokens (Etherlink) - XTZ, WXTZ, Apple XTZ & USDC monitoring
    - Curve (Etherlink) - USDC/USDT LP position monitoring with withdrawal optimization
    - Merkl (Etherlink) - Claimable rewards monitoring
    """
    
    def __init__(self):
        self.supply_reader = SupplyReader()
        self.spot_manager = SpotBalanceManager()
        self.merkl_client = MerklClient()
        
    def get_all_balances(self, address: str) -> Dict[str, Any]:
        """
        Fetches balances from all protocols
        """
        # Get UTC timestamp before any on-chain requests
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        print("\n" + "="*80)
        print("FETCHING ALL BALANCES (SUPERLEND + SPOT + CURVE + MERKL)")
        print("="*80)
        
        # Convert address to checksum format
        checksum_address = Web3.to_checksum_address(address)
        
        # Initialize result structure
        result = {
            "protocols": {
                "spot": {
                    "etherlink": {}
                }
            }
        }
        
        # Get Merkl rewards
        try:
            print("\n" + "="*80)
            print("MERKL REWARDS CHECKER (ETHERLINK)")
            print("="*80 + "\n")
            
            merkl_rewards = self.merkl_client.get_claimable_rewards(checksum_address, 42793)
            if merkl_rewards and merkl_rewards.get("etherlink"):
                result["protocols"]["merkl"] = merkl_rewards
                print("✓ Merkl rewards fetched successfully")
                
                # Add detailed logging for Merkl
                print("\nMerkl Etherlink rewards:")
                for reward in merkl_rewards["etherlink"]:
                    print(f"\nToken: {reward['token']}")
                    print(f"Total claimable: {reward['total_claimable']['amount']} "
                          f"(${reward['total_claimable']['usd_value']:.2f})")
                    
                    print("\nActive campaigns:")
                    for campaign in reward["campaigns"]:
                        print(f"\n  Campaign {campaign['id']}...")
                        print(f"  Type: {campaign['type']}")
                        print(f"  Claimable: {campaign['claimable']['amount']} "
                              f"(${campaign['claimable']['usd_value']:.2f})")
            else:
                print("No Merkl rewards found")
        except Exception as e:
            print(f"Error fetching Merkl rewards: {str(e)}")
        
        # Get Superlend balances
        try:
            print("\n" + "="*80)
            print("SUPERLEND BALANCE CHECKER (ETHERLINK)")
            print("="*80 + "\n")
            superlend_balances = get_superlend_balances(checksum_address)
            if superlend_balances and superlend_balances["superlend"]:
                # Organize positions by token
                etherlink_positions = {}
                for position in superlend_balances["superlend"]:
                    token_symbol = position["symbol"]
                    etherlink_positions[token_symbol] = {
                        "staking_contract": position["contract"],
                        "amount": position["raw_balance"],
                        "decimals": position["decimals"],
                        "formatted_balance": position["formatted_balance"],
                        "position_type": position.get("position_type", "positive"),
                        "value": {
                            "USDC": {
                                "amount": position["usdc_value"]["usdc_value"],
                                "decimals": position["decimals"],
                                "formatted": position["usdc_value"]["usdc_formatted"],
                                "conversion_details": {
                                    "source": position["usdc_value"]["conversion_source"],
                                    "rate": position["usdc_value"]["conversion_rate"],
                                    "note": f"1 {token_symbol} conversion to USDC"
                                }
                            }
                        }
                    }
                
                # Add WXTZ net position if it exists
                if superlend_balances.get("wxtz_net_position") and superlend_balances["wxtz_net_position"]["usdc_value"]:
                    wxtz_net = superlend_balances["wxtz_net_position"]
                    etherlink_positions["WXTZ_NET"] = {
                        "staking_contract": "Net position calculation",
                        "amount": wxtz_net["wxtz_net_wei"],
                        "decimals": 18,
                        "formatted_balance": wxtz_net["wxtz_net_formatted"],
                        "position_type": "net",
                        "value": {
                            "USDC": {
                                "amount": str(wxtz_net["usdc_value"]["usdc_value"]),
                                "decimals": 6,
                                "formatted": wxtz_net["usdc_value"]["usdc_formatted"],
                                "conversion_details": {
                                    "source": wxtz_net["usdc_value"]["conversion_source"],
                                    "rate": wxtz_net["usdc_value"]["conversion_rate"],
                                    "note": f"Net WXTZ position: {wxtz_net['positions']['slWXTZ']} - {wxtz_net['positions']['variableDebtWXTZ']} wei"
                                }
                            }
                        }
                    }
                
                # Calculate totals for Etherlink (real net value)
                etherlink_total_wei = 0
                
                for token_symbol, token_data in etherlink_positions.items():
                    if token_symbol in ["totals"]:
                        continue
                    
                    # Ne compter que slUSDC et WXTZ_NET pour le total
                    if token_symbol in ["slUSDC", "WXTZ_NET"]:
                        if token_data.get("value") and token_data["value"].get("USDC"):
                            etherlink_total_wei += int(token_data["value"]["USDC"]["amount"])
                
                etherlink_total_formatted = str(Decimal(etherlink_total_wei) / Decimal(10**6))
                
                # Add totals
                if etherlink_positions:
                    etherlink_positions["totals"] = {
                        "wei": etherlink_total_wei,
                        "formatted": etherlink_total_formatted
                    }
                
                # Create superlend section only if positions exist
                if etherlink_positions:
                    result["protocols"]["superlend"] = {
                        "etherlink": etherlink_positions,
                        "totals": {
                            "wei": etherlink_total_wei,
                            "formatted": etherlink_total_formatted
                        }
                    }
                    
                    print("✓ Superlend positions fetched successfully")
                    
                    # Add detailed logging for Superlend
                    print("\nSuperlend Etherlink positions:")
                    for token_symbol, token_data in etherlink_positions.items():
                        if token_symbol == "totals":
                            print(f"\nEtherlink totals:")
                            print(f"  Total USDC value: {token_data['formatted']}")
                            print(f"  Total USDC value (wei): {token_data['wei']}")
                            continue
                        print(f"\n{token_symbol}:")
                        print(f"  Contract: {token_data['staking_contract']}")
                        print(f"  Raw balance: {token_data['amount']}")
                        print(f"  Formatted balance: {token_data['formatted_balance']}")
                        print(f"  Position type: {token_data.get('position_type', 'positive')}")
                        if token_data.get('value') and token_data['value'].get('USDC'):
                            usdc_data = token_data['value']['USDC']
                            print(f"  USDC value: {usdc_data['formatted']}")
                            print(f"  USDC value (wei): {usdc_data['amount']}")
                            print(f"  Conversion rate: {usdc_data['conversion_details']['rate']}")
                            print(f"  Source: {usdc_data['conversion_details']['source']}")
            else:
                print("No Superlend balances found - skipping Superlend section")
        except Exception as e:
            print(f"Error fetching Superlend positions: {str(e)}")
        
        # Get Spot balances (XTZ, WXTZ, Apple XTZ & USDC)
        try:
            print("\n" + "="*80)
            print("SPOT BALANCE CHECKER (ETHERLINK)")
            print("="*80 + "\n")
            spot_balances = self.spot_manager.get_balances(checksum_address)
            
            # Initialize spot data structure
            result["protocols"]["spot"] = {
                "etherlink": {},
                "base": {},
                "totals": {
                    "wei": 0,
                    "formatted": "0.0"
                }
            }
            
            total_spot_wei = 0
            
            # Process each network
            for network in ["etherlink", "base"]:
                if spot_balances and network in spot_balances:
                    network_spot = spot_balances[network]
                    spot_positions = {}
                    network_total_wei = 0
                    
                    for token_symbol, token_data in network_spot.items():
                        if token_symbol == "totals":
                            continue
                        
                        if token_data.get("value") and token_data["value"].get("USDC"):
                            usdc_data = token_data["value"]["USDC"]
                            position_data = {
                                "amount": token_data["amount"],
                                "decimals": token_data["decimals"],
                                "formatted_balance": f"{Decimal(token_data['amount']) / Decimal(10**token_data['decimals']):.6f}",
                                "value": {
                                    "USDC": usdc_data
                                }
                            }
                            
                            # Add WXTZ value only for Etherlink tokens
                            if network == "etherlink" and "WXTZ" in token_data["value"]:
                                position_data["value"]["WXTZ"] = token_data["value"]["WXTZ"]
                            
                            spot_positions[token_symbol] = position_data
                            network_total_wei += int(usdc_data["amount"])
                    
                    # Add network totals
                    if spot_positions:
                        network_total_formatted = str(Decimal(network_total_wei) / Decimal(10**6))
                        spot_positions["totals"] = {
                            "wei": network_total_wei,
                            "formatted": network_total_formatted
                        }
                        total_spot_wei += network_total_wei
                    
                    result["protocols"]["spot"][network] = spot_positions
                    
                    print(f"✓ Spot {network} positions fetched successfully")
                    
                    # Add detailed logging for network
                    if spot_positions:
                        print(f"\nSpot {network} positions:")
                        for token_symbol, token_data in spot_positions.items():
                            if token_symbol == "totals":
                                print(f"\n{network} totals:")
                                print(f"  Total USDC value: {token_data['formatted']}")
                                print(f"  Total USDC value (wei): {token_data['wei']}")
                                continue
                            print(f"\n{token_symbol}:")
                            print(f"  Raw balance: {token_data['amount']}")
                            print(f"  Formatted balance: {token_data['formatted_balance']}")
                            if token_data.get('value') and token_data['value'].get('USDC'):
                                usdc_data = token_data['value']['USDC']
                                print(f"  USDC value: {usdc_data['formatted']}")
                                print(f"  USDC value (wei): {usdc_data['amount']}")
                                print(f"  Conversion rate: {usdc_data['conversion_details']['rate']}")
                                print(f"  Source: {usdc_data['conversion_details']['source']}")
            
            # Update global spot totals
            if total_spot_wei > 0:
                result["protocols"]["spot"]["totals"] = {
                    "wei": total_spot_wei,
                    "formatted": str(Decimal(total_spot_wei) / Decimal(10**6))
                }
                
        except Exception as e:
            print(f"Error fetching Spot positions: {str(e)}")
            result["protocols"]["spot"]["etherlink"] = {}
            result["protocols"]["spot"]["totals"] = {
                "wei": 0,
                "formatted": "0.0"
            }
        
        # Get Curve balances (USDC/USDT LP position)
        try:
            print("\n" + "="*80)
            print("CURVE BALANCE CHECKER (ETHERLINK)")
            print("="*80 + "\n")
            
            # Initialize Curve manager
            curve_manager = CurveManager(checksum_address, network="etherlink", pool_name="USDCUSDT")
            curve_results = curve_manager.run()
            
            if curve_results and curve_results.get("positions"):
                # Process Curve positions
                curve_positions = {}
                curve_total_wei = 0
                
                for pool_name, pool_data in curve_results["positions"].items():
                    # Get the best withdrawal simulation
                    best_withdrawal = None
                    for sim in pool_data.get("withdrawal_simulations", []):
                        if sim.get("recommended", False):
                            best_withdrawal = sim
                            break
                    
                    if not best_withdrawal and pool_data.get("withdrawal_simulations"):
                        best_withdrawal = pool_data["withdrawal_simulations"][0]
                    
                    # Calculate USDC value
                    usdc_value_wei = 0
                    conversion_details = {}
                    
                    if best_withdrawal and best_withdrawal.get("final_value"):
                        final_value = best_withdrawal["final_value"]
                        if "usdc_amount_wei" in final_value:
                            usdc_value_wei = int(final_value["usdc_amount_wei"])
                            conversion_details = {
                                "source": final_value.get("strategy", "Unknown"),
                                "rate": "optimized",
                                "note": f"Best strategy: {final_value.get('strategy', 'Unknown')}"
                            }
                    else:
                        # Fallback: use raw LP balance as USDC
                        lp_balance = float(pool_data["lp_balance"]["amount_formatted"])
                        usdc_value_wei = int(lp_balance * 1e6)
                        conversion_details = {
                            "source": "Estimated",
                            "rate": "1.0",
                            "note": "Rough LP to USDC estimation (1:1)"
                        }
                    
                    curve_positions[pool_name] = {
                        "staking_contract": pool_data["pool_address"],
                        "amount": pool_data["lp_balance"]["amount_wei"],
                        "decimals": pool_data["lp_balance"]["decimals"],
                        "formatted_balance": pool_data["lp_balance"]["amount_formatted"],
                        "pool_tokens": pool_data["pool_tokens"],
                        "n_coins": pool_data["n_coins"],
                        "withdrawal_simulations": pool_data.get("withdrawal_simulations", []),
                        "value": {
                            "USDC": {
                                "amount": str(usdc_value_wei),
                                "decimals": 6,
                                "formatted": f"{usdc_value_wei / 1e6:.6f}",
                                "conversion_details": conversion_details
                            }
                        }
                    }
                    
                    curve_total_wei += usdc_value_wei
                
                # Add totals
                if curve_positions:
                    curve_total_formatted = str(Decimal(curve_total_wei) / Decimal(10**6))
                    curve_positions["totals"] = {
                        "wei": curve_total_wei,
                        "formatted": curve_total_formatted
                    }
                    
                    result["protocols"]["curve"] = {
                        "etherlink": curve_positions,
                        "totals": {
                            "wei": curve_total_wei,
                            "formatted": curve_total_formatted
                        }
                    }
                    
                    print("✓ Curve positions fetched successfully")
                    
                    # Add detailed logging for Curve
                    print("\nCurve Etherlink positions:")
                    for pool_name, pool_data in curve_positions.items():
                        if pool_name == "totals":
                            print(f"\nCurve totals:")
                            print(f"  Total USDC value: {pool_data['formatted']}")
                            print(f"  Total USDC value (wei): {pool_data['wei']}")
                            continue
                        print(f"\n{pool_name}:")
                        print(f"  Pool address: {pool_data['staking_contract']}")
                        print(f"  LP balance: {pool_data['formatted_balance']}")
                        print(f"  Tokens in pool: {[token['symbol'] for token in pool_data['pool_tokens']]}")
                        if pool_data.get('value') and pool_data['value'].get('USDC'):
                            usdc_data = pool_data['value']['USDC']
                            print(f"  USDC value: {usdc_data['formatted']}")
                            print(f"  USDC value (wei): {usdc_data['amount']}")
                            print(f"  Strategy: {usdc_data['conversion_details']['source']}")
                        if pool_data.get('withdrawal_simulations'):
                            print(f"  Withdrawal options:")
                            for i, sim in enumerate(pool_data['withdrawal_simulations']):
                                recommended = " (RECOMMENDED)" if sim.get('recommended', False) else ""
                                print(f"    Option {i+1}: {sim['withdrawable_amount_formatted']} {sim['token_symbol']}{recommended}")
            else:
                print("No Curve positions found")
                
        except Exception as e:
            print(f"Error fetching Curve positions: {str(e)}")
        
        return result

def build_overview(all_balances: Dict[str, Any], address: str) -> Dict[str, Any]:
    """Build overview section with all protocol positions"""
    
    # Initialize positions dictionary
    positions = {}
    
    # Process Superlend positions
    if "protocols" in all_balances and "superlend" in all_balances["protocols"] and "etherlink" in all_balances["protocols"]["superlend"]:
        etherlink_positions = all_balances["protocols"]["superlend"]["etherlink"]
        superlend_total_usdc = 0
        
        for token_symbol, token_data in etherlink_positions.items():
            if token_symbol == "totals":
                continue
            
            if token_symbol in ["slUSDC", "WXTZ_NET"]:
                if token_data.get("value") and token_data["value"].get("USDC"):
                    superlend_total_usdc += int(token_data["value"]["USDC"]["amount"])
        
        if superlend_total_usdc != 0:
            superlend_formatted = f"{Decimal(superlend_total_usdc) / Decimal(10**6):.6f}"
            positions["superlend.etherlink.total"] = superlend_formatted
    
    # Process Spot positions
    if "protocols" in all_balances and "spot" in all_balances["protocols"]:
        spot_data = all_balances["protocols"]["spot"]
        # Process each network
        for network in ["etherlink", "base"]:
            if network in spot_data:
                network_positions = spot_data[network]
                for token_symbol, token_data in network_positions.items():
                    if token_symbol == "totals":
                        continue
                    if token_data.get("value") and token_data["value"].get("USDC"):
                        usdc_wei = token_data["value"]["USDC"]["amount"]
                        usdc_formatted = f"{Decimal(usdc_wei) / Decimal(10**6):.6f}"
                        positions[f"spot.{network}.{token_symbol}"] = usdc_formatted
    
    # Process Curve positions
    if "protocols" in all_balances and "curve" in all_balances["protocols"] and "etherlink" in all_balances["protocols"]["curve"]:
        etherlink_curve_positions = all_balances["protocols"]["curve"]["etherlink"]
        for pool_name, pool_data in etherlink_curve_positions.items():
            if pool_name == "totals":
                continue
            if pool_data.get("value") and pool_data["value"].get("USDC"):
                usdc_wei = pool_data["value"]["USDC"]["amount"]
                usdc_formatted = f"{Decimal(usdc_wei) / Decimal(10**6):.6f}"
                positions[f"curve.etherlink.{pool_name}"] = usdc_formatted
    
    # Process Merkl rewards
    if "protocols" in all_balances and "merkl" in all_balances["protocols"] and "etherlink" in all_balances["protocols"]["merkl"]:
        # Get WXTZ/USDC rate from spot data for consistent pricing
        wxtz_usdc_rate = None
        if "spot" in all_balances["protocols"] and "etherlink" in all_balances["protocols"]["spot"]:
            etherlink_spot = all_balances["protocols"]["spot"]["etherlink"]
            for token_data in etherlink_spot.values():
                if token_data.get("value") and token_data["value"].get("USDC"):
                    usdc_data = token_data["value"]["USDC"]
                    if usdc_data.get("conversion_details") and usdc_data["conversion_details"].get("rate"):
                        wxtz_usdc_rate = Decimal(usdc_data["conversion_details"]["rate"])
                        break

        for reward in all_balances["protocols"]["merkl"]["etherlink"]:
            if reward.get("total_claimable"):
                reward_amount = Decimal(reward["total_claimable"]["amount_wei"]) / Decimal(10**18)  # Convert from wei to applXTZ
                if wxtz_usdc_rate and reward["token"] == "applXTZ":
                    # Convert applXTZ to USDC using the same rate as spot
                    usdc_amount = reward_amount * wxtz_usdc_rate
                    positions[f"merkl.etherlink.{reward['token']}"] = f"{usdc_amount:.6f}"
                else:
                    # Fallback to original amount if token is not applXTZ or rate not found
                    positions[f"merkl.etherlink.{reward['token']}"] = reward["total_claimable"]["amount"]
    
    # Sort positions by value in descending order
    sorted_positions = dict(sorted(
        positions.items(),
        key=lambda x: float(x[1]),
        reverse=True
    ))
    
    # Calculate total value from positions
    total_value_usdc_wei = sum(Decimal(value) * Decimal(10**6) for value in sorted_positions.values())
    total_value_usdc = total_value_usdc_wei / Decimal(10**6)
    
    return {
        "nav": {
            "total_assets_wei": str(int(total_value_usdc_wei)),
            "total_assets": f"{total_value_usdc:.6f}"
        },
        "positions": sorted_positions
    }

def main():
    """Main function to aggregate all protocol data."""
    from dotenv import load_dotenv
    load_dotenv()
    DEFAULT_ADDRESS = os.getenv('PRODUCTION_ADDRESS', '0xA6548c1F8D3F3c97f75deE8D030B942b6c88B6ce')
    
    address = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADDRESS
    
    if not Web3.is_address(address):
        print(f"Error: Invalid address format: {address}")
        return None
        
    aggregator = BalanceAggregator()
    
    max_retries = 3
    retry_delay = 2
    
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
    
    overview = build_overview(all_balances, address)
    
    try:
        print("\n" + "="*80)
        print("CALCULATING SHARE PRICE")
        print("="*80 + "\n")
        
        total_supply_wei = aggregator.supply_reader.get_total_supply()
        total_supply_formatted = aggregator.supply_reader.format_total_supply()
        
        nav_usdc = Decimal(overview["nav"]["total_assets"])
        supply_formatted = Decimal(total_supply_wei) / Decimal(10**18)
        
        if supply_formatted > 0:
            share_price_formatted = nav_usdc / supply_formatted
        else:
            share_price_formatted = Decimal(0)
        
        print(f"Total Supply: {total_supply_formatted} dtUSDC")
        print(f"Total Assets: {overview['nav']['total_assets']} USDC")
        print(f"Price per Share: {share_price_formatted:.6f} USDC per dtUSDC")
        
    except Exception as e:
        print(f"Error calculating share price: {str(e)}")
        total_supply_wei = "0"
        total_supply_formatted = "0.0"
        share_price_formatted = Decimal(0)
    
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    enhanced_nav = {
        "total_assets": overview["nav"]["total_assets"],
        "price_per_share": f"{share_price_formatted:.6f}",
        "total_supply": f"{Decimal(total_supply_wei) / Decimal(10**18):.6f}",
        "total_assets_wei": overview["nav"]["total_assets_wei"]
    }
    
    spot_data = all_balances["protocols"].get("spot", {})
    protocols_without_spot = {k: v for k, v in all_balances["protocols"].items() if k != "spot"}
    
    # Calculate total spot balance across all networks
    total_spot_wei = 0
    for network in ["etherlink", "base"]:
        if network in spot_data and "totals" in spot_data[network]:
            total_spot_wei += spot_data[network]["totals"]["wei"]
    
    # Update spot totals
    if total_spot_wei > 0:
        spot_data["totals"] = {
            "wei": total_spot_wei,
            "formatted": f"{total_spot_wei/1e6:.6f}"
        }
    
    final_result = {
        "timestamp": timestamp,
        "created_at": created_at,
        "address": address,
        "nav": enhanced_nav,
        "positions": overview["positions"],  # Moved positions right after nav
        "spot": spot_data,
        "protocols": protocols_without_spot
    }
    
    print("\n" + "="*80)
    print("FINAL AGGREGATED RESULT (SUPERLEND + SPOT + CURVE + MERKL)")
    print("="*80 + "\n")
    print(json.dumps(final_result, indent=2))
    
    return final_result

if __name__ == "__main__":
    main()