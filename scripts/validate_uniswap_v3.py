"""Validate Uniswap V3 deployment on Base Sepolia.

This script verifies that all Uniswap V3 contracts are deployed correctly
and that the ETH/USDC pool has sufficient liquidity for testing.
"""

import asyncio
import os
import sys
from decimal import Decimal
from web3 import Web3

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.constants import UNISWAP_V3_ADDRESSES, TOKEN_ADDRESSES
from src.utils.web3_provider import get_web3
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Minimal ABI for contract verification
MINIMAL_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "factory",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

# Factory ABI for pool lookup
FACTORY_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "tokenA", "type": "address"},
            {"name": "tokenB", "type": "address"},
            {"name": "fee", "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

# Pool ABI for liquidity check
POOL_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "liquidity",
        "outputs": [{"name": "", "type": "uint128"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token1",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "fee",
        "outputs": [{"name": "", "type": "uint24"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# ERC20 ABI for balance checks
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def check_contract_exists(w3: Web3, address: str, name: str) -> bool:
    """Check if contract exists at address.

    Args:
        w3: Web3 instance
        address: Contract address
        name: Contract name for logging

    Returns:
        True if contract exists
    """
    try:
        code = w3.eth.get_code(Web3.to_checksum_address(address))
        if code == b"" or code == "0x":
            logger.error(f"❌ {name}: No code at {address}")
            return False
        logger.info(f"✅ {name}: Verified at {address}")
        return True
    except Exception as e:
        logger.error(f"❌ {name}: Error checking {address}: {e}")
        return False


def check_pool_liquidity(
    w3: Web3, pool_address: str, min_liquidity: int = 1000
) -> tuple[bool, dict]:
    """Check pool liquidity and details.

    Args:
        w3: Web3 instance
        pool_address: Pool contract address
        min_liquidity: Minimum required liquidity

    Returns:
        Tuple of (success, pool_info_dict)
    """
    try:
        pool = w3.eth.contract(
            address=Web3.to_checksum_address(pool_address), abi=POOL_ABI
        )

        # Get pool details
        liquidity = pool.functions.liquidity().call()
        token0_address = pool.functions.token0().call()
        token1_address = pool.functions.token1().call()
        fee = pool.functions.fee().call()

        # Get token symbols
        token0 = w3.eth.contract(
            address=Web3.to_checksum_address(token0_address), abi=ERC20_ABI
        )
        token1 = w3.eth.contract(
            address=Web3.to_checksum_address(token1_address), abi=ERC20_ABI
        )

        token0_symbol = token0.functions.symbol().call()
        token1_symbol = token1.functions.symbol().call()
        token0_decimals = token0.functions.decimals().call()
        token1_decimals = token1.functions.decimals().call()

        # Get pool balances
        token0_balance = token0.functions.balanceOf(pool_address).call()
        token1_balance = token1.functions.balanceOf(pool_address).call()

        token0_balance_formatted = Decimal(token0_balance) / Decimal(
            10**token0_decimals
        )
        token1_balance_formatted = Decimal(token1_balance) / Decimal(
            10**token1_decimals
        )

        pool_info = {
            "address": pool_address,
            "token0": token0_symbol,
            "token1": token1_symbol,
            "fee": fee,
            "liquidity": liquidity,
            "token0_balance": float(token0_balance_formatted),
            "token1_balance": float(token1_balance_formatted),
        }

        if liquidity < min_liquidity:
            logger.warning(
                f"⚠️  Pool has low liquidity: {liquidity} (min: {min_liquidity})"
            )
            return False, pool_info

        logger.info(
            f"✅ Pool verified: {token0_symbol}/{token1_symbol} "
            f"(fee: {fee/10000}%, liquidity: {liquidity})"
        )
        logger.info(
            f"   Balances: {token0_balance_formatted:.4f} {token0_symbol}, "
            f"{token1_balance_formatted:.4f} {token1_symbol}"
        )

        return True, pool_info

    except Exception as e:
        logger.error(f"❌ Error checking pool: {e}")
        return False, {}


async def main():
    """Run validation checks."""
    logger.info("=" * 60)
    logger.info("Uniswap V3 Base Sepolia Validation")
    logger.info("=" * 60)

    network = "base-sepolia"
    w3 = get_web3(network)

    # Check connection (try to get block number to verify)
    try:
        chain_id = w3.eth.chain_id
        block_number = w3.eth.block_number

        logger.info(f"✅ Connected to {network}")
        logger.info(f"   Chain ID: {chain_id}")
        logger.info(f"   Block: {block_number}")
        logger.info("")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Base Sepolia: {e}")
        return False

    # Get addresses
    uniswap_addresses = UNISWAP_V3_ADDRESSES[network]
    token_addresses = TOKEN_ADDRESSES[network]

    # Validate contracts
    logger.info("Validating Uniswap V3 Contracts:")
    logger.info("-" * 60)

    all_valid = True

    contracts = {
        "Universal Router": uniswap_addresses["universal_router"],
        "SwapRouter02": uniswap_addresses["swap_router_02"],
        "Factory": uniswap_addresses["factory"],
        "QuoterV2": uniswap_addresses["quoter_v2"],
        "WETH": uniswap_addresses["weth"],
    }

    for name, address in contracts.items():
        if not check_contract_exists(w3, address, name):
            all_valid = False

    logger.info("")

    # Check ETH/USDC pool
    logger.info("Checking ETH/USDC Pool:")
    logger.info("-" * 60)

    factory = w3.eth.contract(
        address=Web3.to_checksum_address(uniswap_addresses["factory"]),
        abi=FACTORY_ABI,
    )

    # Check 0.05% fee tier (500) - common for ETH/stablecoin
    fee_tier = 500
    weth_address = token_addresses["WETH"]
    usdc_address = token_addresses["USDC"]

    try:
        pool_address = factory.functions.getPool(
            Web3.to_checksum_address(weth_address),
            Web3.to_checksum_address(usdc_address),
            fee_tier,
        ).call()

        if pool_address == "0x0000000000000000000000000000000000000000":
            logger.warning(
                f"⚠️  ETH/USDC pool with {fee_tier/10000}% fee does not exist"
            )
            logger.info("   Trying 0.3% fee tier...")

            # Try 0.3% fee tier
            fee_tier = 3000
            pool_address = factory.functions.getPool(
                Web3.to_checksum_address(weth_address),
                Web3.to_checksum_address(usdc_address),
                fee_tier,
            ).call()

            if pool_address == "0x0000000000000000000000000000000000000000":
                logger.error("❌ ETH/USDC pool not found on any fee tier")
                all_valid = False
            else:
                logger.info(f"✅ Found pool at {pool_address}")
                pool_valid, pool_info = check_pool_liquidity(w3, pool_address)
                if not pool_valid:
                    all_valid = False
        else:
            logger.info(f"✅ Found pool at {pool_address}")
            pool_valid, pool_info = check_pool_liquidity(w3, pool_address)
            if not pool_valid:
                all_valid = False

    except Exception as e:
        logger.error(f"❌ Error querying factory: {e}")
        all_valid = False

    logger.info("")
    logger.info("=" * 60)

    if all_valid:
        logger.info("✅ All validation checks passed!")
        logger.info("   Base Sepolia Uniswap V3 is ready for testing")
    else:
        logger.error("❌ Some validation checks failed")
        logger.error("   Review errors above before proceeding")

    logger.info("=" * 60)

    return all_valid


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
