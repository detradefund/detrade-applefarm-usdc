# DeTrade AppleFarm USDC Oracle

This repository contains the oracle service for DeTrade AppleFarm USDC, which aggregates and monitors positions across multiple protocols on Etherlink and Base networks.

## Project Structure

```
oracle.detrade.fund-applefarm-usdc/
├── builder/                 # Core aggregation and pushing logic
│   ├── aggregator.py       # Aggregates balances from all protocols
│   └── pusher.py           # Handles MongoDB storage of aggregated data
├── config/                  # Configuration files
│   └── networks.py         # Network and token configurations
├── cowswap/                # CoW Protocol integration
│   └── cow_client.py       # Client for price discovery and quotes
├── curve/                  # Curve protocol integration
│   ├── abis/              # Smart contract ABIs
│   ├── balance/           # Balance and reward management
│   ├── curve_manager.py   # Main Curve protocol interface
│   └── markets/           # Market configurations
├── merkl/                  # Merkl rewards integration
│   └── merkl_client.py    # Client for checking claimable rewards
├── mongo/                  # MongoDB utilities
│   ├── check_mongo.py     # Database connection verification
│   ├── delete_document.py # Single document deletion
│   └── delete_documents_after_date.py # Batch document deletion
├── shares/                 # Share token utilities
│   └── supply_reader.py   # Total supply reading and formatting
├── spot/                   # Spot token management
│   └── balance_manager.py # Spot token balance tracking
├── superlend/             # Superlend protocol integration
│   └── check_balance.py   # Lending position monitoring
└── utils/                 # Utility functions
    └── retry.py           # API retry mechanism
```

## Core Components

### Builder Module
- **aggregator.py**: Main aggregator that combines balances from multiple protocols:
  - Superlend (Etherlink) - slUSDC monitoring
  - Spot Tokens (Etherlink) - XTZ, WXTZ, Apple XTZ & USDC monitoring
  - Curve (Etherlink) - USDC/USDT LP position monitoring
  - Merkl (Etherlink) - Claimable rewards monitoring

- **pusher.py**: Handles the storage of portfolio balances in MongoDB:
  - Connects to MongoDB using environment variables
  - Processes and formats data for storage
  - Includes retry mechanisms and error handling

### Protocol Integrations

#### Curve Protocol
- Monitors LP positions in USDC/USDT pool
- Calculates optimal withdrawal strategies
- Tracks rewards and balances

#### Superlend Protocol
- Monitors lending positions (slUSDC)
- Tracks borrowed positions
- Calculates net positions

#### Spot Tokens
- Monitors native token balances
- Tracks wrapped token positions
- Handles Apple XTZ positions

#### Merkl Rewards
- Checks claimable rewards
- Monitors active campaigns
- Tracks reward amounts and types

### Utilities

#### MongoDB Tools
- **check_mongo.py**: Verifies database connection and access
- **delete_document.py**: Removes specific documents
- **delete_documents_after_date.py**: Batch deletion with date filtering

#### Other Utilities
- **retry.py**: Implements exponential backoff for API calls
- **supply_reader.py**: Handles share token supply calculations

## Environment Setup

Required environment variables:
```env
# RPC URLs
BASE_RPC=            # Base network RPC URL
ETHERLINK_RPC=       # Etherlink network RPC URL

# MongoDB Configuration
MONGO_URI=          # MongoDB connection string
DATABASE_NAME=      # Database name
COLLECTION_NAME=    # Collection name

# Contract Addresses
PRODUCTION_ADDRESS= # Main contract address
```

## GitHub Actions

The repository includes a GitHub Action (`hourly-pusher.yml`) that:
- Runs hourly to fetch and store protocol data
- Can be triggered manually
- Includes debug information and environment checks

## Usage

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the pusher
python -m builder.pusher
```

### Manual Data Check
```bash
# Check MongoDB connection
python -m mongo.check_mongo

# Check specific protocol balances
python -m superlend.check_balance
python -m curve.curve_manager
```

## Error Handling

The system includes several error handling mechanisms:
- API retry with exponential backoff
- MongoDB connection verification
- Data validation before storage
- Detailed logging for debugging

## Monitoring

The system logs:
- Protocol balance changes
- Share price calculations
- MongoDB operations
- API interactions
- Error conditions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

Proprietary - All rights reserved
