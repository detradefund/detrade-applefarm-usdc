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

class BalanceAggregator:
    """
    Master aggregator that combines balances from multiple protocols.
    Currently supports:
    - Superlend (Etherlink) - slUSDC monitoring
    - Spot Tokens (Etherlink) - XTZ, WXTZ, Apple XTZ & USDC monitoring
    - Curve (Etherlink) - USDC/USDT LP position monitoring with withdrawal optimization
    """
    
    def __init__(self):
        self.supply_reader = SupplyReader()
        self.spot_manager = SpotBalanceManager()
        
    def get_all_balances(self, address: str) -> Dict[str, Any]:
        """
        Fetches balances from Superlend, Spot tokens, and Curve protocol on Etherlink
        """
        # Get UTC timestamp before any on-chain requests
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        print("\n" + "="*80)
        print("FETCHING ALL BALANCES (SUPERLEND + SPOT + CURVE)")
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
        
        # Get Superlend balances
        try:
            print("\n" + "="*80)
            print("SUPERLEND BALANCE CHECKER (ETHERLINK)")
            print("="*80 + "\n")
            superlend_balances = get_superlend_balances(checksum_address)
            if superlend_balances and superlend_balances["superlend"]:
                # Organiser les positions par token
                etherlink_positions = {}
                for position in superlend_balances["superlend"]:
                    token_symbol = position["symbol"]
                    etherlink_positions[token_symbol] = {
                        "staking_contract": position["contract"],
                        "amount": position["raw_balance"],
                        "decimals": position["decimals"],
                        "formatted_balance": position["formatted_balance"],
                        "position_type": position.get("position_type", "positive"),  # Nouveau champ
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
                
                # Ajouter la position nette WXTZ si elle existe
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
                
                # Calculer les totaux pour Etherlink (valeur nette réelle)
                # On ne compte que slUSDC et la position nette WXTZ, pas les composants individuels
                etherlink_total_wei = 0
                
                for token_symbol, token_data in etherlink_positions.items():
                    if token_symbol in ["totals"]:
                        continue
                    
                    # Ne compter que slUSDC et WXTZ_NET pour le total (pas slWXTZ ni variableDebtWXTZ individuellement)
                    if token_symbol in ["slUSDC", "WXTZ_NET"]:
                        if token_data.get("value") and token_data["value"].get("USDC"):
                            etherlink_total_wei += int(token_data["value"]["USDC"]["amount"])
                
                etherlink_total_formatted = str(Decimal(etherlink_total_wei) / Decimal(10**6))
                
                # Ajouter les totaux
                if etherlink_positions:
                    etherlink_positions["totals"] = {
                        "wei": etherlink_total_wei,
                        "formatted": etherlink_total_formatted
                    }
                
                # Créer la section superlend seulement si des positions existent
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
                        # Exclure les totaux du logging des positions
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
                # Ne pas ajouter de section superlend vide
        except Exception as e:
            print(f"✗ Error fetching Superlend positions: {str(e)} - skipping Superlend section")
            # Ne pas ajouter de section superlend en cas d'erreur
        
        # Get Spot balances (XTZ, WXTZ, Apple XTZ & USDC)
        try:
            print("\n" + "="*80)
            print("SPOT BALANCE CHECKER (ETHERLINK)")
            print("="*80 + "\n")
            spot_balances = self.spot_manager.get_balances(checksum_address)
            
            if spot_balances and "etherlink" in spot_balances:
                etherlink_spot = spot_balances["etherlink"]
                # Convertir les balances spot pour correspondre au format attendu
                spot_positions = {}
                
                for token_symbol, token_data in etherlink_spot.items():
                    if token_symbol == "totals":
                        continue
                    
                    # Le spot balance manager fournit déjà les valeurs en USDC
                    if token_data.get("value") and token_data["value"].get("USDC"):
                        usdc_data = token_data["value"]["USDC"]
                        
                        spot_positions[token_symbol] = {
                            "amount": token_data["amount"],
                            "decimals": token_data["decimals"],
                            "formatted_balance": f"{Decimal(token_data['amount']) / Decimal(10**token_data['decimals']):.6f}",
                            "value": {
                                "WXTZ": token_data["value"]["WXTZ"],
                                "USDC": usdc_data
                            }
                        }
                
                # Calculer les totaux spot
                spot_total_wei = sum(
                    int(token_data["value"]["USDC"]["amount"]) 
                    for token_data in spot_positions.values() 
                    if token_data.get("value") and token_data["value"].get("USDC")
                )
                spot_total_formatted = str(Decimal(spot_total_wei) / Decimal(10**6))
                
                # Ajouter les totaux
                if spot_positions:
                    spot_positions["totals"] = {
                        "wei": spot_total_wei,
                        "formatted": spot_total_formatted
                    }
                
                result["protocols"]["spot"]["etherlink"] = spot_positions
                result["protocols"]["spot"]["totals"] = {
                    "wei": spot_total_wei,
                    "formatted": spot_total_formatted
                }
                
                print("✓ Spot positions fetched successfully")
                
                # Add detailed logging for Spot
                if spot_positions:
                    print("\nSpot Etherlink positions:")
                    for token_symbol, token_data in spot_positions.items():
                        if token_symbol == "totals":
                            print(f"\nSpot totals:")
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
            else:
                print("No spot balances found")
                result["protocols"]["spot"]["etherlink"] = {}
                result["protocols"]["spot"]["totals"] = {
                    "wei": 0,
                    "formatted": "0.0"
                }
                
        except Exception as e:
            print(f"✗ Error fetching Spot positions: {str(e)}")
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
                    # Get the best withdrawal simulation (recommended strategy)
                    best_withdrawal = None
                    for sim in pool_data.get("withdrawal_simulations", []):
                        if sim.get("recommended", False):
                            best_withdrawal = sim
                            break
                    
                    # If no recommended, take the first one or default to basic data
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
                        # Fallback: use raw LP balance as USDC (rough estimate)
                        lp_balance = float(pool_data["lp_balance"]["amount_formatted"])
                        usdc_value_wei = int(lp_balance * 1e6)  # Rough 1:1 estimation
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
            print(f"✗ Error fetching Curve positions: {str(e)}")
            # Don't add empty curve section on error
        
        return result


def build_overview(all_balances: Dict[str, Any], address: str) -> Dict[str, Any]:
    """Build overview section with Superlend, Spot, and Curve positions"""
    
    # Initialize positions dictionary
    positions = {}
    
    # Process Superlend positions
    if "protocols" in all_balances and "superlend" in all_balances["protocols"] and "etherlink" in all_balances["protocols"]["superlend"]:
        etherlink_positions = all_balances["protocols"]["superlend"]["etherlink"]
        superlend_total_usdc = 0
        
        for token_symbol, token_data in etherlink_positions.items():
            # Exclure les totaux des positions
            if token_symbol == "totals":
                continue
            
            # Calculer le total net Superlend (slUSDC + WXTZ_NET)
            if token_symbol in ["slUSDC", "WXTZ_NET"]:
                if token_data.get("value") and token_data["value"].get("USDC"):
                    superlend_total_usdc += int(token_data["value"]["USDC"]["amount"])
        
        # Ajouter une seule position pour tout Superlend
        if superlend_total_usdc != 0:
            # Formater en USDC décimal
            superlend_formatted = f"{Decimal(superlend_total_usdc) / Decimal(10**6):.6f}"
            positions["superlend.etherlink.total"] = superlend_formatted
    
    # Process Spot positions
    if "protocols" in all_balances and "spot" in all_balances["protocols"] and "etherlink" in all_balances["protocols"]["spot"]:
        etherlink_spot_positions = all_balances["protocols"]["spot"]["etherlink"]
        for token_symbol, token_data in etherlink_spot_positions.items():
            # Exclure les totaux des positions
            if token_symbol == "totals":
                continue
            if token_data.get("value") and token_data["value"].get("USDC"):
                # Formater en USDC décimal
                usdc_wei = token_data["value"]["USDC"]["amount"]
                usdc_formatted = f"{Decimal(usdc_wei) / Decimal(10**6):.6f}"
                positions[f"spot.etherlink.{token_symbol}"] = usdc_formatted
    
    # Process Curve positions
    if "protocols" in all_balances and "curve" in all_balances["protocols"] and "etherlink" in all_balances["protocols"]["curve"]:
        etherlink_curve_positions = all_balances["protocols"]["curve"]["etherlink"]
        for pool_name, pool_data in etherlink_curve_positions.items():
            # Exclure les totaux des positions
            if pool_name == "totals":
                continue
            if pool_data.get("value") and pool_data["value"].get("USDC"):
                # Formater en USDC décimal
                usdc_wei = pool_data["value"]["USDC"]["amount"]
                usdc_formatted = f"{Decimal(usdc_wei) / Decimal(10**6):.6f}"
                positions[f"curve.etherlink.{pool_name}"] = usdc_formatted
    
    # Sort positions by value in descending order
    sorted_positions = dict(sorted(
        positions.items(),
        key=lambda x: float(x[1]),  # Convertir string en float pour le tri
        reverse=True
    ))
    
    # Calculate total value from positions (convert formatted values back to wei for calculation)
    total_value_usdc_wei = sum(Decimal(value) * Decimal(10**6) for value in sorted_positions.values())
    
    # Convert to USDC with 6 decimals for display
    total_value_usdc = total_value_usdc_wei / Decimal(10**6)
    
    return {
        "nav": {
            "total_assets_wei": str(int(total_value_usdc_wei)),  # S'assurer que c'est un entier
            "total_assets": f"{total_value_usdc:.6f}"
        },
        "positions": sorted_positions
    }

def main():
    """
    Main function to aggregate Superlend and Spot balance data.
    Uses command line argument if provided, otherwise uses production address from .env.
    """
    # Get production address from environment
    from dotenv import load_dotenv
    load_dotenv()
    DEFAULT_ADDRESS = os.getenv('PRODUCTION_ADDRESS', '0xA6548c1F8D3F3c97f75deE8D030B942b6c88B6ce')
    
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
    
    # Build the final result with overview and protocols sections
    overview = build_overview(all_balances, address)
    
    # Get total supply and calculate share price
    try:
        print("\n" + "="*80)
        print("CALCULATING SHARE PRICE")
        print("="*80 + "\n")
        
        total_supply_wei = aggregator.supply_reader.get_total_supply()
        total_supply_formatted = aggregator.supply_reader.format_total_supply()
        
        # Calculate share price: NAV / Total Supply
        nav_usdc_wei = Decimal(overview["nav"]["total_assets_wei"])
        supply_wei = Decimal(total_supply_wei)
        
        if supply_wei > 0:
            # Share price in USDC (with 18 decimals precision)
            share_price_wei = nav_usdc_wei * Decimal(10**18) / supply_wei
            share_price_formatted = share_price_wei / Decimal(10**6)  # Convert back to USDC (6 decimals)
        else:
            share_price_wei = Decimal(0)
            share_price_formatted = Decimal(0)
        
        print(f"Total Supply: {total_supply_formatted} dtUSDC")
        print(f"Total Assets: {overview['nav']['total_assets']} USDC")
        print(f"Price per Share: {share_price_formatted:.6f} USDC per dtUSDC")
        
    except Exception as e:
        print(f"✗ Error calculating share price: {str(e)}")
        total_supply_wei = "0"
        total_supply_formatted = "0.0"
        share_price_formatted = Decimal(0)
    
    # Format created_at to match timestamp format
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Update nav with share price information
    enhanced_nav = {
        "total_assets": overview["nav"]["total_assets"],
        "price_per_share": f"{share_price_formatted:.6f}",
        "total_supply": f"{Decimal(total_supply_wei) / Decimal(10**18):.6f}",
        "total_assets_wei": overview["nav"]["total_assets_wei"]
    }
    
    # Extract spot data from protocols
    spot_data = all_balances["protocols"].get("spot", {})
    # Remove spot from protocols
    protocols_without_spot = {k: v for k, v in all_balances["protocols"].items() if k != "spot"}
    
    final_result = {
        "timestamp": timestamp,
        "created_at": created_at,
        "address": address,
        "nav": enhanced_nav,
        "spot": spot_data,
        "positions": overview["positions"],
        "protocols": protocols_without_spot
    }
    
    # Display final result
    print("\n" + "="*80)
    print("FINAL AGGREGATED RESULT (SUPERLEND + SPOT + CURVE)")
    print("="*80 + "\n")
    print(json.dumps(final_result, indent=2))
    
    return final_result

if __name__ == "__main__":
    main()
