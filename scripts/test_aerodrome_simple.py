#!/usr/bin/env python3
"""Simple test to verify Aerodrome factory contract access."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.web3_provider import get_web3
from src.utils.aerodrome_abis import AERODROME_FACTORY_ABI
from src.utils.contracts import ContractHelper

def main():
    print("\n🧪 Simple Aerodrome Factory Test\n")

    try:
        # Get Web3
        print("1. Connecting to Base mainnet...")
        w3 = get_web3("base-mainnet")
        print(f"   ✅ Connected! Block: {w3.eth.block_number}\n")

        # Get factory
        print("2. Getting Aerodrome factory contract...")
        factory_address = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
        factory = ContractHelper.get_contract(w3, factory_address, AERODROME_FACTORY_ABI)
        print(f"   ✅ Factory contract loaded\n")

        # Query pool count
        print("3. Querying total number of pools...")
        pool_count = factory.functions.allPoolsLength().call()
        print(f"   ✅ Found {pool_count} total pools!\n")

        # Get first pool address
        print("4. Getting first pool address...")
        first_pool = factory.functions.allPools(0).call()
        print(f"   ✅ First pool: {first_pool}\n")

        print("=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
