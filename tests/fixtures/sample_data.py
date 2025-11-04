"""Sample data fixtures for testing."""

from decimal import Decimal
from typing import Dict, List, Any


SAMPLE_PROTOCOLS = [
    {
        "name": "Aerodrome",
        "tvl": Decimal("602000000"),
        "pools": [
            {
                "pool_id": "USDC-ETH",
                "apy": Decimal("0.15"),
                "tvl": Decimal("50000000"),
            },
        ],
    },
    {
        "name": "Morpho",
        "tvl": Decimal("100000000"),
        "pools": [
            {
                "pool_id": "USDC-SUPPLY",
                "apy": Decimal("0.08"),
                "tvl": Decimal("20000000"),
            },
        ],
    },
]


SAMPLE_TRANSACTIONS = [
    {
        "tx_hash": "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "operation": "deposit",
        "protocol": "Aerodrome",
        "amount": Decimal("1000"),
        "status": "completed",
    },
]
