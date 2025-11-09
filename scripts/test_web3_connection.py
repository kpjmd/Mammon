#!/usr/bin/env python3
"""Test script for Web3 connections to Base mainnet and Arbitrum Sepolia.

This script verifies:
1. Can connect to Base mainnet RPC
2. Can connect to Arbitrum Sepolia RPC
3. Can query block numbers and chain IDs
4. Can query gas prices
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.web3_provider import get_web3, check_network_health
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_base_mainnet():
    """Test connection to Base mainnet."""
    print("\n" + "=" * 60)
    print("Testing Base Mainnet Connection")
    print("=" * 60)

    try:
        # Get Web3 instance
        w3 = get_web3("base-mainnet")

        # Check connection
        print(f"✅ Connected: {w3.is_connected()}")
        print(f"✅ Chain ID: {w3.eth.chain_id}")
        print(f"✅ Latest Block: {w3.eth.block_number}")
        print(f"✅ Gas Price: {w3.from_wei(w3.eth.gas_price, 'gwei'):.2f} Gwei")

        # Get health check
        health = check_network_health("base-mainnet")
        print(f"\n📊 Health Check:")
        print(f"   Connected: {health['connected']}")
        print(f"   Chain ID Match: {health['chain_id_match']}")
        print(f"   Block Number: {health['block_number']}")
        print(f"   Gas Price: {health['gas_price_gwei']:.2f} Gwei")

        return True

    except Exception as e:
        print(f"❌ Error connecting to Base mainnet: {e}")
        logger.error(f"Base mainnet connection failed: {e}", exc_info=True)
        return False


def test_arbitrum_sepolia():
    """Test connection to Arbitrum Sepolia testnet."""
    print("\n" + "=" * 60)
    print("Testing Arbitrum Sepolia Connection")
    print("=" * 60)

    try:
        # Get Web3 instance
        w3 = get_web3("arbitrum-sepolia")

        # Check connection
        print(f"✅ Connected: {w3.is_connected()}")
        print(f"✅ Chain ID: {w3.eth.chain_id}")
        print(f"✅ Latest Block: {w3.eth.block_number}")
        print(f"✅ Gas Price: {w3.from_wei(w3.eth.gas_price, 'gwei'):.2f} Gwei")

        # Get health check
        health = check_network_health("arbitrum-sepolia")
        print(f"\n📊 Health Check:")
        print(f"   Connected: {health['connected']}")
        print(f"   Chain ID Match: {health['chain_id_match']}")
        print(f"   Block Number: {health['block_number']}")
        print(f"   Gas Price: {health['gas_price_gwei']:.2f} Gwei")

        return True

    except Exception as e:
        print(f"❌ Error connecting to Arbitrum Sepolia: {e}")
        logger.error(f"Arbitrum Sepolia connection failed: {e}", exc_info=True)
        return False


def main():
    """Run all connection tests."""
    print("\n🚀 Starting Web3 Connection Tests")
    print("This will test connections to Base mainnet and Arbitrum Sepolia\n")

    results = {
        "base_mainnet": test_base_mainnet(),
        "arbitrum_sepolia": test_arbitrum_sepolia(),
    }

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for network, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{network.replace('_', ' ').title()}: {status}")

    all_passed = all(results.values())
    print(f"\n{'✅ All tests passed!' if all_passed else '❌ Some tests failed'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
