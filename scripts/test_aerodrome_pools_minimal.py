#!/usr/bin/env python3
"""Minimal test for Aerodrome pool queries - bypasses audit logging."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.web3_provider import get_web3
from src.utils.aerodrome_abis import AERODROME_FACTORY_ABI, AERODROME_POOL_ABI
from src.utils.contracts import ContractHelper

def main():
    print("\n🧪 Minimal Aerodrome Pool Query Test\n")

    try:
        # Get Web3
        print("1. Connecting to Base mainnet...")
        w3 = get_web3("base-mainnet")
        print(f"   ✅ Connected! Block: {w3.eth.block_number}\n")

        # Get factory
        print("2. Loading factory contract...")
        factory_address = "0x420DD381b31aEf6683db6B902084cB0FFECe40Da"
        factory = ContractHelper.get_contract(w3, factory_address, AERODROME_FACTORY_ABI)
        print(f"   ✅ Factory loaded\n")

        # Get pool count
        print("3. Querying pool count...")
        pool_count = factory.functions.allPoolsLength().call()
        print(f"   ✅ {pool_count} pools found\n")

        # Query first 3 pools
        print(f"4. Querying first 3 pools...\n")
        for i in range(3):
            pool_addr = factory.functions.allPools(i).call()
            pool = ContractHelper.get_contract(w3, pool_addr, AERODROME_POOL_ABI)

            # Get metadata
            metadata = pool.functions.metadata().call()
            dec0, dec1, res0, res1, stable, token0, token1 = metadata

            # Get tokens
            token0_contract = ContractHelper.get_erc20_contract(w3, token0)
            token1_contract = ContractHelper.get_erc20_contract(w3, token1)

            symbol0 = token0_contract.functions.symbol().call()
            symbol1 = token1_contract.functions.symbol().call()

            print(f"   Pool #{i+1}: {symbol0}/{symbol1}")
            print(f"     Address: {pool_addr}")
            print(f"     Reserves: {res0 / 10**dec0:,.2f} {symbol0} | {res1 / 10**dec1:,.2f} {symbol1}")
            print(f"     Stable: {stable}\n")

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
