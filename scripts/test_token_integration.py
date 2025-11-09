#!/usr/bin/env python3
"""Test script for ERC20 token integration.

Tests token metadata retrieval and balance queries on Base mainnet.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tokens.erc20 import ERC20Token, get_token_balance, get_token_info
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_token_metadata():
    """Test retrieving token metadata (USDC on Base)."""
    print("\n" + "=" * 70)
    print("Test 1: Token Metadata Retrieval")
    print("=" * 70)

    # USDC on Base mainnet
    usdc_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

    try:
        print(f"\nQuerying USDC token at {usdc_address}...")
        token = ERC20Token("base-mainnet", usdc_address)

        # Get metadata
        symbol = token.get_symbol()
        decimals = token.get_decimals()
        name = token.get_name()

        print(f"\n✅ Token Metadata Retrieved:")
        print(f"   Name: {name}")
        print(f"   Symbol: {symbol}")
        print(f"   Decimals: {decimals}")

        # Get full info
        info = token.get_info()
        print(f"\n📊 Full Token Info:")
        for key, value in info.items():
            print(f"   {key}: {value}")

        # Verify expected values
        assert symbol == "USDC", f"Expected USDC, got {symbol}"
        assert decimals == 6, f"Expected 6 decimals, got {decimals}"

        print("\n✅ USDC metadata test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error(f"Token metadata test failed: {e}", exc_info=True)
        return False


def test_weth_metadata():
    """Test retrieving WETH metadata on Base."""
    print("\n" + "=" * 70)
    print("Test 2: WETH Metadata Retrieval")
    print("=" * 70)

    # WETH on Base mainnet
    weth_address = "0x4200000000000000000000000000000000000006"

    try:
        print(f"\nQuerying WETH token at {weth_address}...")

        # Use convenience function
        info = get_token_info("base-mainnet", weth_address)

        print(f"\n✅ WETH Metadata Retrieved:")
        print(f"   Name: {info['name']}")
        print(f"   Symbol: {info['symbol']}")
        print(f"   Decimals: {info['decimals']}")

        # Verify expected values
        assert info['symbol'] == "WETH", f"Expected WETH, got {info['symbol']}"
        assert info['decimals'] == 18, f"Expected 18 decimals, got {info['decimals']}"

        print("\n✅ WETH metadata test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error(f"WETH metadata test failed: {e}", exc_info=True)
        return False


def test_token_balance():
    """Test querying token balance (Aerodrome AERO token)."""
    print("\n" + "=" * 70)
    print("Test 3: Token Balance Query")
    print("=" * 70)

    # AERO token on Base mainnet
    aero_address = "0x940181a94A35A4569E4529a3CDfB74e38FD98631"

    # Aerodrome treasury address (should have AERO tokens)
    treasury_address = "0x4200000000000000000000000000000000000042"

    try:
        print(f"\nQuerying AERO balance for treasury...")
        print(f"Token: {aero_address}")
        print(f"Address: {treasury_address}")

        token = ERC20Token("base-mainnet", aero_address)

        # Get balance (raw)
        raw_balance = token.get_balance(treasury_address)
        print(f"\n📊 Raw Balance: {raw_balance}")

        # Get balance (formatted)
        formatted_balance = token.get_balance_formatted(treasury_address)
        print(f"📊 Formatted Balance: {formatted_balance:,.2f} AERO")

        # Test format_amount method
        test_amount = 1_000_000_000_000_000_000  # 1.0 AERO (18 decimals)
        formatted = token.format_amount(test_amount)
        print(f"\n🧪 Format Test: {test_amount} raw = {formatted} formatted")

        assert formatted == 1.0, f"Expected 1.0, got {formatted}"

        print("\n✅ Balance query test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error(f"Balance query test failed: {e}", exc_info=True)
        return False


def test_convenience_functions():
    """Test convenience functions."""
    print("\n" + "=" * 70)
    print("Test 4: Convenience Functions")
    print("=" * 70)

    usdc_address = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    # Coinbase fee collector address (has USDC)
    address = "0x8e5F7b18BcAd5CB2D97E98c1EFEAe47c7abb0D6c"

    try:
        print(f"\nTesting get_token_balance() convenience function...")

        # Get formatted balance
        balance_formatted = get_token_balance(
            "base-mainnet",
            usdc_address,
            address,
            formatted=True
        )
        print(f"✅ Formatted Balance: {balance_formatted:,.6f} USDC")

        # Get raw balance
        balance_raw = get_token_balance(
            "base-mainnet",
            usdc_address,
            address,
            formatted=False
        )
        print(f"✅ Raw Balance: {balance_raw}")

        print("\n✅ Convenience functions test PASSED")
        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error(f"Convenience functions test failed: {e}", exc_info=True)
        return False


def main():
    """Run all token integration tests."""
    print("\n🚀 Token Integration Test Suite")
    print("Testing ERC20 token utilities on Base mainnet\n")

    results = {
        "USDC Metadata": test_token_metadata(),
        "WETH Metadata": test_weth_metadata(),
        "Token Balance": test_token_balance(),
        "Convenience Functions": test_convenience_functions(),
    }

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name}: {status}")

    all_passed = all(results.values())
    print(f"\n{'✅ All tests passed!' if all_passed else '❌ Some tests failed'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
