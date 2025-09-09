from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime
import sys
from dateutil import parser

# Load environment variables
load_dotenv()

def delete_documents_after_date(database_name: str, cutoff_date: str) -> None:
    """Delete all documents from MongoDB created after the specified date"""
    try:
        # Get MongoDB URI from .env
        mongo_uri = os.getenv('MONGO_URI')
        # Get collection name from environment variable
        collection_name = os.getenv('MONGO_COLLECTION', 'oracle')
        
        print("\nConnecting to MongoDB...")
        print(f"Database: {database_name}")
        print(f"Collection: {collection_name}")
        print(f"Cutoff date: {cutoff_date}\n")
        
        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        
        # Test connection
        client.admin.command('ping')
        print("✓ Connection successful!")
        
        # Get database and collection
        db = client[database_name]
        collection = db[collection_name]
        
        # Parse the cutoff date
        cutoff_datetime = parser.parse(cutoff_date)
        
        # Find documents to delete
        query = {
            "created_at": {"$gt": cutoff_datetime.strftime("%Y-%m-%d %H:%M:%S UTC")}
        }
        
        # Get count of documents to delete
        count = collection.count_documents(query)
        
        if count == 0:
            print("\nNo documents found after the specified date")
            return
            
        # Find and display all documents to delete
        print(f"\nFound {count} documents to delete:")
        print("="*80)
        
        for doc in collection.find(query):
            print(f"\nID: {doc['_id']}")
            print(f"Address: {doc.get('address', 'N/A')}")
            print(f"Created at: {doc.get('created_at', 'N/A')}")
            if 'nav' in doc:
                print(f"Total Value: {doc['nav']['weth']} WETH")
            print("-"*40)
        
        print("="*80)
        
        # Confirm deletion
        confirm = input(f"\nAre you sure you want to delete these {count} documents? (y/N): ")
        if confirm.lower() != 'y':
            print("Deletion cancelled")
            return
            
        # Delete documents
        result = collection.delete_many(query)
        
        if result.deleted_count > 0:
            print(f"\n✓ Successfully deleted {result.deleted_count} documents")
        else:
            print("\n❌ Failed to delete documents")
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
    finally:
        client.close()
        print("\n✓ MongoDB connection closed")

def main():
    """CLI entry point for document deletion by date"""
    if len(sys.argv) != 3:
        print("Usage: python -m mongo.delete_documents_after_date <database_name> <cutoff_date>")
        print("Example: python -m mongo.delete_documents_after_date $DATABASE_NAME '2025-06-03 11:25:41 UTC'")
        sys.exit(1)
        
    database_name = sys.argv[1] if len(sys.argv) > 1 else os.getenv('DATABASE_NAME', 'applefarm-usdc')
    cutoff_date = sys.argv[2]
    delete_documents_after_date(database_name, cutoff_date)

if __name__ == "__main__":
    main() 