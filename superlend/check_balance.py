import os
import sys
import json
from web3 import Web3
from dotenv import load_dotenv
from decimal import Decimal
from pathlib import Path
import requests

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.networks import RPC_URLS, NETWORK_TOKENS

# Load environment variables - fix for GitHub Actions
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()  # GitHub Actions case

# ERC20 ABI for balanceOf and other standard functions
ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"}
]

# Token address on Etherlink
SLUSDC_ADDRESS = "0xd03bfdF9B26DB1e6764724d914d7c3d18106a9Fb"
SLWXTZ_ADDRESS = "0x008ae222661B6A42e3A097bd7AAC15412829106b"  # slWXTZ (positive position)
VARIABLE_DEBT_WXTZ_ADDRESS = "0x1504D006b80b1616d2651E8d15D5d25A88efef58"  # variableDebtWXTZ (debt)

# Get production address from .env (for fallback only)
PRODUCTION_ADDRESS = os.getenv('PRODUCTION_ADDRESS', '0xA6548c1F8D3F3c97f75deE8D030B942b6c88B6ce')

def get_usdc_value(raw_balance, decimals):
    """Returns USDC value directly
    
    For slUSDC, 1 slUSDC = 1 USDC (underlying token)
    No need for CoWSwap conversion
    """
    return {
        "usdc_value": raw_balance,  # Keep value in wei
        "usdc_formatted": str(Decimal(raw_balance) / (10 ** decimals)),
        "conversion_rate": "1.0",
        "conversion_source": "Direct USDC underlying"
    }

def get_wxtz_usdc_price():
    """Get WXTZ/USDC price from GeckoTerminal API"""
    try:
        url = "https://api.geckoterminal.com/api/v2/search/pools?query=0x508060a01f11d6a2eb774b55aeba95931265e0cc&network=etherlink&page=1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data.get("data") and len(data["data"]) > 0:
            pool_data = data["data"][0]
            attributes = pool_data.get("attributes", {})
            wxtz_usdc_price = attributes.get("quote_token_price_base_token")
            
            if wxtz_usdc_price:
                return float(wxtz_usdc_price)
        
        return 0.8  # Fallback price
    except Exception as e:
        print(f"Warning: Failed to fetch WXTZ price: {str(e)}")
        return 0.8  # Fallback price

def get_wxtz_value(raw_balance, decimals):
    """Returns USDC value for a WXTZ amount"""
    wxtz_price = get_wxtz_usdc_price()
    
    # Convert raw_balance (18 decimals) to USDC value (6 decimals)
    wxtz_amount = Decimal(raw_balance) / Decimal(10 ** 18)  # WXTZ always 18 decimals
    usdc_amount = wxtz_amount * Decimal(str(wxtz_price))
    usdc_wei = int(usdc_amount * Decimal(10 ** 6))  # USDC 6 decimals
    
    return {
        "usdc_value": usdc_wei,
        "usdc_formatted": str(usdc_amount),
        "conversion_rate": str(wxtz_price),
        "conversion_source": "GeckoTerminal API"
    }

def check_slusdc_balance(w3, wallet_address):
    """Check slUSDC balance for an address on Etherlink"""
    try:
        contract = w3.eth.contract(address=SLUSDC_ADDRESS, abi=ERC20_ABI)
        balance_raw = contract.functions.balanceOf(wallet_address).call()
        decimals = contract.functions.decimals().call()
        symbol = contract.functions.symbol().call()
        name = contract.functions.name().call()
        
        # Get USDC value if balance > 0
        usdc_value = None
        if balance_raw > 0:
            usdc_value = get_usdc_value(str(balance_raw), decimals)
        
        return {
            "contract": SLUSDC_ADDRESS,
            "symbol": symbol,
            "name": name,
            "decimals": decimals,
            "raw_balance": str(balance_raw),
            "formatted_balance": str(Decimal(balance_raw) / (10 ** decimals)),
            "usdc_value": usdc_value
        }
    except Exception as e:
        print(f"Error checking slUSDC: {e}")
        return None

def check_slwxtz_balance(w3, wallet_address):
    """Check slWXTZ balance for an address on Etherlink"""
    try:
        contract = w3.eth.contract(address=SLWXTZ_ADDRESS, abi=ERC20_ABI)
        balance_raw = contract.functions.balanceOf(wallet_address).call()
        decimals = contract.functions.decimals().call()
        symbol = contract.functions.symbol().call()
        name = contract.functions.name().call()
        
        # Get USDC value if balance > 0
        usdc_value = None
        if balance_raw > 0:
            usdc_value = get_wxtz_value(str(balance_raw), decimals)
        
        return {
            "contract": SLWXTZ_ADDRESS,
            "symbol": symbol,
            "name": name,
            "decimals": decimals,
            "raw_balance": str(balance_raw),
            "formatted_balance": str(Decimal(balance_raw) / (10 ** decimals)),
            "usdc_value": usdc_value,
            "position_type": "positive"  # Long position
        }
    except Exception as e:
        print(f"Error checking slWXTZ: {e}")
        return None

def check_variable_debt_wxtz_balance(w3, wallet_address):
    """Check variableDebtWXTZ balance for an address on Etherlink"""
    try:
        contract = w3.eth.contract(address=VARIABLE_DEBT_WXTZ_ADDRESS, abi=ERC20_ABI)
        balance_raw = contract.functions.balanceOf(wallet_address).call()
        decimals = contract.functions.decimals().call()
        symbol = contract.functions.symbol().call()
        name = contract.functions.name().call()
        
        # Get USDC value if balance > 0 (debt)
        usdc_value = None
        if balance_raw > 0:
            usdc_value = get_wxtz_value(str(balance_raw), decimals)
        
        return {
            "contract": VARIABLE_DEBT_WXTZ_ADDRESS,
            "symbol": symbol,
            "name": name,
            "decimals": decimals,
            "raw_balance": str(balance_raw),
            "formatted_balance": str(Decimal(balance_raw) / (10 ** decimals)),
            "usdc_value": usdc_value,
            "position_type": "negative"  # Short position (debt)
        }
    except Exception as e:
        print(f"Error checking variableDebtWXTZ: {e}")
        return None

def get_superlend_balances(address=None):
    """Get Superlend balances (slUSDC, slWXTZ, variableDebtWXTZ) and calculate net WXTZ position"""
    # Use provided address or fallback to PRODUCTION_ADDRESS
    target_address = address or PRODUCTION_ADDRESS
    
    # Connect to Etherlink
    rpc_url = RPC_URLS.get("etherlink")
    if not rpc_url:
        print("Etherlink RPC not configured in networks.py")
        return {"superlend": [], "wxtz_net_position": None}
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("Unable to connect to Etherlink")
        return {"superlend": [], "wxtz_net_position": None}
    
    print(f"Connected to Etherlink via {rpc_url}")
    print(f"Checking Superlend balances for address: {target_address}")
    
    superlend_data = []
    wxtz_positions = {"positive": 0, "negative": 0}  # For calculating net position
    
    # Check slUSDC balance
    print("\n--- Checking slUSDC ---")
    slusdc_result = check_slusdc_balance(w3, target_address)
    if slusdc_result and int(slusdc_result["raw_balance"]) > 0:
        superlend_data.append(slusdc_result)
        print(f"Balance found: {slusdc_result['formatted_balance']} {slusdc_result['symbol']}")
    else:
        print("No slUSDC balance found")
    
    # Check slWXTZ balance (positive position)
    print("\n--- Checking slWXTZ ---")
    slwxtz_result = check_slwxtz_balance(w3, target_address)
    if slwxtz_result and int(slwxtz_result["raw_balance"]) > 0:
        superlend_data.append(slwxtz_result)
        wxtz_positions["positive"] = Decimal(slwxtz_result["raw_balance"])
        print(f"Balance found: {slwxtz_result['formatted_balance']} {slwxtz_result['symbol']}")
    else:
        print("No slWXTZ balance found")
    
    # Check variableDebtWXTZ balance (negative position)
    print("\n--- Checking variableDebtWXTZ ---")
    debt_result = check_variable_debt_wxtz_balance(w3, target_address)
    if debt_result and int(debt_result["raw_balance"]) > 0:
        superlend_data.append(debt_result)
        wxtz_positions["negative"] = Decimal(debt_result["raw_balance"])
        print(f"Debt found: {debt_result['formatted_balance']} {debt_result['symbol']}")
    else:
        print("No variableDebtWXTZ debt found")
    
    # Calculate net WXTZ position
    net_position_wei = wxtz_positions["positive"] - wxtz_positions["negative"]
    net_position_formatted = str(net_position_wei / Decimal(10**18))
    
    # Calculate USDC value of net position
    net_position_usdc = None
    if net_position_wei != 0:
        if net_position_wei > 0:
            net_position_usdc = get_wxtz_value(str(int(net_position_wei)), 18)
        else:
            # Negative position
            usdc_value_data = get_wxtz_value(str(int(abs(net_position_wei))), 18)
            net_position_usdc = {
                "usdc_value": -int(usdc_value_data["usdc_value"]),  # Negative
                "usdc_formatted": f"-{usdc_value_data['usdc_formatted']}",
                "conversion_rate": usdc_value_data["conversion_rate"],
                "conversion_source": usdc_value_data["conversion_source"]
            }
    
    wxtz_net_position = {
        "wxtz_net_wei": str(int(net_position_wei)),
        "wxtz_net_formatted": net_position_formatted,
        "positions": {
            "slWXTZ": str(int(wxtz_positions["positive"])),
            "variableDebtWXTZ": str(int(wxtz_positions["negative"]))
        },
        "usdc_value": net_position_usdc
    }
    
    print(f"\n--- Net WXTZ Position ---")
    print(f"slWXTZ: +{wxtz_positions['positive'] / Decimal(10**18):.6f} WXTZ")
    print(f"variableDebtWXTZ: -{wxtz_positions['negative'] / Decimal(10**18):.6f} WXTZ")
    print(f"Net position: {net_position_formatted} WXTZ")
    if net_position_usdc:
        print(f"Net USDC value: {net_position_usdc['usdc_formatted']} USDC")
    
    return {"superlend": superlend_data, "wxtz_net_position": wxtz_net_position}

def main():
    result = get_superlend_balances()
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()