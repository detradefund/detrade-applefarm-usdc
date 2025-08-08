"""
Curve Protocol pools configuration and utilities.
Contains pool addresses and related constants for different networks.
"""

from typing import Dict, Optional, List
import os
import json

class CurvePool:
    def __init__(self, name: str, network: str):
        """
        Initialize a Curve pool.
        
        Args:
            name: Name of the pool (e.g., 'USDCUSDT')
            network: Network identifier ('etherlink')
        """
        self.name = name
        self.network = network
        self.info = CURVE_POOLS[network][name]

    @property
    def address(self) -> str:
        """Get the pool address."""
        return self.info["pool"]

    @property
    def lp_token_address(self) -> str:
        """Get the LP token address."""
        return self.info["lp_token"]

    @property
    def abi_name(self) -> str:
        """Get the ABI name."""
        return self.info["abi"]

# Pool addresses pour Etherlink - Un seul contrat qui fait pool ET LP token
CURVE_POOLS: Dict[str, Dict[str, Dict[str, str]]] = {
    "etherlink": {
        "USDCUSDT": {
            "pool": "0x2D84D79C852f6842AbE0304b70bBaA1506AdD457",
            "lp_token": "0x2D84D79C852f6842AbE0304b70bBaA1506AdD457",  # Même contrat
            "abi": "CurveStableSwap"
        }
    }
}

def get_pool_address(network: str, pool_name: str) -> str:
    """
    Get the address of a Curve pool for a specific network.
    
    Args:
        network: Network identifier ('etherlink')
        pool_name: Name of the pool
        
    Returns:
        Pool address as string
    """
    if network not in CURVE_POOLS:
        raise ValueError(f"Network {network} not supported")
    
    if pool_name not in CURVE_POOLS[network]:
        raise ValueError(f"Pool {pool_name} not found for network {network}")
        
    return CURVE_POOLS[network][pool_name]["pool"]

def get_lp_token_address(network: str, pool_name: str) -> str:
    """
    Get the address of a Curve LP token for a specific network.
    
    Args:
        network: Network identifier ('etherlink')
        pool_name: Name of the pool
        
    Returns:
        LP token address as string
    """
    if network not in CURVE_POOLS:
        raise ValueError(f"Network {network} not supported")
    
    if pool_name not in CURVE_POOLS[network]:
        raise ValueError(f"Pool {pool_name} not found for network {network}")
        
    return CURVE_POOLS[network][pool_name]["lp_token"]

def get_pool_abi(network: str, pool_name: str) -> str:
    """
    Get the ABI name to use for a Curve pool.
    
    Args:
        network: Network identifier ('etherlink')
        pool_name: Name of the pool
        
    Returns:
        ABI name as string
    """
    if network not in CURVE_POOLS:
        raise ValueError(f"Network {network} not supported")
    
    if pool_name not in CURVE_POOLS[network]:
        raise ValueError(f"Pool {pool_name} not found for network {network}")
        
    return CURVE_POOLS[network][pool_name]["abi"]

def get_available_pools(network: str) -> List[str]:
    """
    Get list of available pools for a network.
    
    Args:
        network: Network identifier
        
    Returns:
        List of pool names
    """
    if network not in CURVE_POOLS:
        raise ValueError(f"Network {network} not supported")
        
    return list(CURVE_POOLS[network].keys())

def get_supported_networks() -> List[str]:
    """
    Get list of supported networks.
    
    Returns:
        List of network identifiers
    """
    return list(CURVE_POOLS.keys())

def add_pool(network: str, pool_name: str, pool_address: str, lp_token_address: str, abi_name: str):
    """
    Add a new pool to the configuration.
    
    Args:
        network: Network identifier
        pool_name: Name of the pool
        pool_address: Address of the pool contract
        lp_token_address: Address of the LP token contract
        abi_name: Name of the ABI file to use
    """
    if network not in CURVE_POOLS:
        CURVE_POOLS[network] = {}
    
    CURVE_POOLS[network][pool_name] = {
        "pool": pool_address,
        "lp_token": lp_token_address,
        "abi": abi_name
    }
    
    print(f"Added pool {pool_name} on {network}: {pool_address}")

def write_pool_info_json(network: str, pool_name: str):
    """
    Write the pool information to curve/markets/<pool_name>/info.json
    """
    info = CURVE_POOLS[network][pool_name]
    info_dict = {
        "network": network,
        "pool_name": pool_name,
        "pool_address": info["pool"],
        "lp_token": info["lp_token"],
        "abi": info["abi"]
    }
    dir_path = os.path.join(os.path.dirname(__file__), pool_name)
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, "info.json")
    with open(file_path, "w") as f:
        json.dump(info_dict, f, indent=2)
    print(f"Pool info written to {file_path}") 