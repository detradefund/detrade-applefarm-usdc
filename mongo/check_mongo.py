from pymongo import MongoClient
from datetime import datetime
from pprint import pprint
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_mongodb():
    """Check MongoDB connection and display most recent document from database"""
    try:
        # Get MongoDB URI from .env
        mongo_uri = os.getenv('MONGO_URI')

        # Get database name and collection from environment variables
        database_name = os.getenv('DATABASE_NAME', 'detrade-applefarm-usdc')
        
        collection_name = os.getenv('MONGO_COLLECTION', 'oracle')
        
        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        
        # Test connection
        client.admin.command('ping')
        print("✓ Connection successful!")
        
        print(f"\n{'='*80}")
        print(f"Database: {database_name}")
        print(f"{'='*80}")
        
        # Get database and collection
        db = client[database_name]
        collection = db[collection_name]
            
        # Get most recent document based on timestamp
        print(f"\nFetching most recent document...")
        doc = collection.find_one(
            sort=[('timestamp', -1)]
        )
        
        if doc:
            print("\nMost recent document:")
            print("-"*40)
            print(f"ID: {doc['_id']}")
            print(f"Address: {doc['address']}")
            print(f"Timestamp: {doc['timestamp']}")
            print(f"Total Value: {doc['nav']['usdc']} USDC")
        else:
            print(f"No documents found in {database_name}.{collection_name}")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
    finally:
        client.close()

if __name__ == "__main__":
    check_mongodb() 