import os
import sys
import json
from web3 import Web3
from dotenv import load_dotenv
from decimal import Decimal
from pathlib import Path

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.networks import RPC_URLS, NETWORK_TOKENS

# Load environment variables - fix for GitHub Actions
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()  # GitHub Actions case

# ERC20 ABI pour balanceOf et autres fonctions standard
ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"}
]

# Adresse du token slUSDC sur Etherlink
SLUSDC_ADDRESS = "0xd03bfdF9B26DB1e6764724d914d7c3d18106a9Fb"

# Plus besoin de conversion - slUSDC underlying est directement USDC

# Récupérer l'adresse de production depuis .env (pour fallback seulement)
PRODUCTION_ADDRESS = os.getenv('PRODUCTION_ADDRESS', '0xA6548c1F8D3F3c97f75deE8D030B942b6c88B6ce')

def get_usdc_value(raw_balance, decimals):
    """Retourne la valeur USDC directement
    
    Pour slUSDC, 1 slUSDC = 1 USDC (underlying token)
    Pas besoin de conversion via CoWSwap
    """
    return {
        "usdc_value": raw_balance,  # Garde la valeur en wei
        "usdc_formatted": str(Decimal(raw_balance) / (10 ** decimals)),
        "conversion_rate": "1.0",
        "conversion_source": "Direct USDC underlying"
    }

def check_slusdc_balance(w3, wallet_address):
    """Vérifie la balance slUSDC pour une adresse sur Etherlink"""
    try:
        contract = w3.eth.contract(address=SLUSDC_ADDRESS, abi=ERC20_ABI)
        balance_raw = contract.functions.balanceOf(wallet_address).call()
        decimals = contract.functions.decimals().call()
        symbol = contract.functions.symbol().call()
        name = contract.functions.name().call()
        
        # Récupérer la valeur USDC si la balance > 0
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
        print(f"Erreur lors de la vérification de slUSDC: {str(e)}")
        return None

def get_superlend_balances(address=None):
    """Récupère la balance slUSDC et retourne un dictionnaire"""
    # Use provided address or fallback to PRODUCTION_ADDRESS
    target_address = address or PRODUCTION_ADDRESS
    
    # Connect to Etherlink
    rpc_url = RPC_URLS.get("etherlink")
    if not rpc_url:
        print("RPC Etherlink non configuré dans networks.py")
        return {"superlend": []}
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("Impossible de se connecter à Etherlink")
        return {"superlend": []}
    
    print(f"Connecté à Etherlink via {rpc_url}")
    print(f"Vérification de la balance slUSDC pour l'adresse: {target_address}")
    
    # Vérifier la balance slUSDC
    result = check_slusdc_balance(w3, target_address)
    
    superlend_data = []
    if result and int(result["raw_balance"]) > 0:
        superlend_data.append(result)
        print(f"Balance trouvée: {result['formatted_balance']} {result['symbol']}")
    else:
        print("Aucune balance slUSDC trouvée ou balance = 0")
    
    return {
        "superlend": superlend_data
    }

def main():
    result = get_superlend_balances()
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main() 