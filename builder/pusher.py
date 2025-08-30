import sys
from pathlib import Path
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from typing import Dict, Any
import logging
import os
# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent))

from aggregator import BalanceAggregator, build_overview

# Add parent directory to PYTHONPATH and load environment variables
root_path = str(Path(__file__).parent.parent)
env_path = Path(root_path) / '.env'
load_dotenv(env_path)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Debug: Check if .env file exists and variables are loaded
logger.info(f"Looking for .env file at: {env_path}")
logger.info(f".env file exists: {env_path.exists()}")
logger.info(f"MONGO_URI exists: {bool(os.getenv('MONGO_URI'))}")
logger.info(f"DATABASE_NAME_1 exists: {bool(os.getenv('DATABASE_NAME_1'))}")
logger.info(f"COLLECTION_NAME exists: {bool(os.getenv('COLLECTION_NAME'))}")
logger.info(f"ADDRESSES exists: {bool(os.getenv('ADDRESSES'))}")

class BalancePusher:
    """
    Handles the storage of portfolio balances in MongoDB.
    Acts as a bridge between the BalanceAggregator and the database.
    """
    def __init__(self, database_name=None, collection_name=None):
        # Required MongoDB configuration from environment variables
        self.mongo_uri = os.getenv('MONGO_URI')
        self.database_name = database_name or os.getenv('DATABASE_NAME_1')
        self.collection_name = collection_name or os.getenv('COLLECTION_NAME')
        
        if not all([self.mongo_uri, self.database_name, self.collection_name]):
            raise ValueError("Missing required environment variables for MongoDB connection")
        
        # Initialize MongoDB connection
        self._init_mongo_connection()
        
        # Initialize aggregator
        self.aggregator = BalanceAggregator()

    def _init_mongo_connection(self) -> None:
        """Initialize MongoDB connection and verify access"""
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            
            # Test connection with timeout
            self.client.admin.command('ping')
            logger.info("MongoDB connection initialized successfully")
            logger.info(f"Database: {self.database_name}")
            logger.info(f"Collection: {self.collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB connection: {str(e)}")
            raise

    def _prepare_balance_data(self, raw_data: Dict[str, Any], address: str) -> Dict[str, Any]:
        """Prepare balance data for storage"""
        # Convert large numbers to strings
        data = self.convert_large_numbers_to_strings(raw_data)
        
        # Add metadata
        timestamp = datetime.now(timezone.utc)
        data.update({
            'address': address,
            'created_at': timestamp,
            'timestamp': timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        })
        
        return data

    def _verify_insertion(self, doc_id: Any) -> bool:
        """Verify document was properly inserted"""
        try:
            inserted_doc = self.collection.find_one({"_id": doc_id})
            return bool(inserted_doc)
        except Exception as e:
            logger.error(f"Failed to verify document insertion: {str(e)}")
            return False

    def convert_large_numbers_to_strings(self, data: Dict) -> Dict:
        """Recursively converts large integers to strings"""
        if isinstance(data, dict):
            return {k: self.convert_large_numbers_to_strings(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.convert_large_numbers_to_strings(x) for x in data]
        elif isinstance(data, int) and data > 2**53:
            return str(data)
        return data

    def push_balance_data(self, address: str) -> None:
        """
        Main method to fetch and store portfolio balance data.
        """
        try:
            # Capture start time in UTC for data collection
            collection_timestamp = datetime.now(timezone.utc)
            
            logger.info("="*80)
            logger.info(f"PUSHING BALANCE DATA FOR {address}")
            logger.info("="*80)

            # 1. Fetch current portfolio data
            logger.info("1. Fetching portfolio data...")
            logger.info(f"Collection started at: {collection_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            all_balances = self.aggregator.get_all_balances(address)
            if not all_balances:
                raise Exception("Failed to fetch portfolio data")
            logger.info("Portfolio data fetched successfully")

            # 2. Build overview
            logger.info("2. Building overview...")
            overview = build_overview(all_balances, address)
            logger.info("Overview built successfully")

            # 3. Calculate share price
            logger.info("3. Calculating share price...")
            try:
                total_supply_wei = self.aggregator.supply_reader.get_total_supply()
                total_supply_formatted = self.aggregator.supply_reader.format_total_supply()
                
                # Calculate share price: NAV / Total Supply
                from decimal import Decimal
                nav_usdc_wei = Decimal(overview["nav"]["usdc_wei"])
                supply_wei = Decimal(total_supply_wei)
                
                if supply_wei > 0:
                    # Share price in USDC (with 18 decimals precision)
                    share_price_wei = nav_usdc_wei * Decimal(10**18) / supply_wei
                    share_price_formatted = share_price_wei / Decimal(10**6)  # Convert back to USDC (6 decimals)
                else:
                    share_price_formatted = Decimal(0)
                
                logger.info(f"Total Supply: {total_supply_formatted} dtUSDC")
                logger.info(f"NAV: {overview['nav']['usdc']} USDC")
                logger.info(f"Share Price: {share_price_formatted:.6f} USDC per dtUSDC")
                
            except Exception as e:
                logger.error(f"Error calculating share price: {str(e)}")
                total_supply_wei = "0"
                share_price_formatted = Decimal(0)

            # 4. Prepare data for storage
            logger.info("4. Preparing data for storage...")
            push_timestamp = datetime.now(timezone.utc)
            
            # Update nav with share price information
            enhanced_nav = {
                "total_assets_wei": overview["nav"]["total_assets_wei"],
                "total_assets": overview["nav"]["total_assets"],
                "price_per_share": f"{share_price_formatted:.6f}",
                "total_supply": f"{Decimal(total_supply_wei) / Decimal(10**18):.6f}"
            }
            
            # Combine overview with the rest of the data
            prepared_data = {
                'timestamp': collection_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
                'created_at': push_timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
                'address': address,
                'nav': enhanced_nav,
                'positions': overview['positions'],
                'protocols': all_balances['protocols']
            }
            
            # Convert large numbers to strings
            prepared_data = self.convert_large_numbers_to_strings(prepared_data)
            
            logger.info("Data prepared successfully")

            # 5. Store data in MongoDB
            logger.info("5. Storing data in MongoDB...")
            result = self.collection.insert_one(prepared_data)
            
            if not result.inserted_id:
                raise Exception("No document ID returned after insertion")
            
            logger.info(f"Document inserted with ID: {result.inserted_id}")

            # 6. Verify insertion
            logger.info("6. Verifying document insertion...")
            if self._verify_insertion(result.inserted_id):
                logger.info("Document verified in database")
            else:
                raise Exception("Document verification failed")

            # 7. Print summary avec la durée de collection
            collection_duration = (push_timestamp - collection_timestamp).total_seconds()
            logger.info("="*80)
            logger.info("SUMMARY")
            logger.info("="*80)
            logger.info(f"Address: {address}")
            logger.info(f"Total Assets: {enhanced_nav['total_assets']} USDC")
            logger.info(f"Price per Share: {enhanced_nav['price_per_share']} USDC per dtUSDC")
            logger.info(f"Total Supply: {enhanced_nav['total_supply']} dtUSDC")
            logger.info(f"Collection started at: {prepared_data['timestamp']}")
            logger.info(f"Pushed at: {push_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            logger.info(f"Collection duration: {collection_duration:.2f} seconds")
            logger.info(f"Database: {self.database_name}")
            logger.info(f"Collection: {self.collection_name}")
            logger.info(f"Document ID: {result.inserted_id}")
            logger.info("="*80)

        except Exception as e:
            logger.error(f"Error in push_balance_data: {str(e)}")
            raise
        
    def close(self):
        """Close MongoDB connection"""
        try:
            self.client.close()
            logger.info("MongoDB connection closed")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {str(e)}")

def main():
    """CLI entry point for testing balance pushing functionality."""
    # Configuration for USDC - uses .env variables
    configurations = [
        {
            'address': os.getenv('PRODUCTION_ADDRESS', '0xA6548c1F8D3F3c97f75deE8D030B942b6c88B6ce'),
            'database_name': os.getenv('DATABASE_NAME_1', 'detrade-core-usdc'),
            'collection_name': os.getenv('COLLECTION_NAME', 'oracle')
        }
    ]
    
    for config in configurations:
        pusher = BalancePusher(
            database_name=config['database_name'],
            collection_name=config['collection_name']
        )
        try:
            pusher.push_balance_data(config['address'])
        finally:
            pusher.close()

if __name__ == "__main__":
    main()