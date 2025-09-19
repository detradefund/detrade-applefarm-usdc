import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env - use consistent path resolution
# In GitHub Actions, .env doesn't exist but environment variables are set directly
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
else:
    # In GitHub Actions or when .env doesn't exist, variables come from environment
    load_dotenv()  # This will load from existing environment variables

# RPC endpoints for supported networks
RPC_URLS = {
    "base": os.getenv('BASE_RPC'),
    "etherlink": os.getenv('ETHERLINK_RPC'),
    "ethereum": os.getenv('ETHEREUM_RPC'),
}

# Chain IDs for network identification
CHAIN_IDS = {
    "base": "8453",
    "etherlink": "42793",
    "ethereum": "1"
}

# Complete network token configuration
# Tokens are organized in categories:
# 1. Yield-bearing tokens (with underlying assets and protocol info)
# 2. Base stablecoins
# 3. Other tokens (governance, rewards, etc.)
NETWORK_TOKENS = {
    "ethereum": {
        "USDC": {
            "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "decimals": 6,
            "name": "USD Coin",
            "symbol": "USDC"
        },
        "USDT": {
            "address": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
            "decimals": 6,
            "name": "Tether USD",
            "symbol": "USDT"
        }
    },
    "base": {
        "USDC": {
            "address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "decimals": 6,
            "name": "USD Coin",
            "symbol": "USDC"
        }
    },
    "etherlink": {
        "applXTZ": {
            "address": "0xcFD2f5FAF6D92D963238E74321325A90BA67fCA3",
            "decimals": 18,
            "name": "Apple XTZ",
            "symbol": "applXTZ"
        },
        "WXTZ": {
            "address": "0xc9B53AB2679f573e480d01e0f49e2B5CFB7a3EAb",
            "decimals": 18,
            "name": "Wrapped XTZ",
            "symbol": "WXTZ"
        },
        "USDC": {
            "address": "0x796Ea11Fa2dD751eD01b53C372fFDB4AAa8f00F9",
            "decimals": 6,
            "name": "USD Coin",
            "symbol": "USDC"
        },
        "USDT": {
            "address": "0x2C03058C8AFC06713be23e58D2febC8337dbfE6A",
            "decimals": 6,
            "name": "Tether USD",
            "symbol": "USDT"
        }
    }
}