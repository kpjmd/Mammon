"""Shared fixtures for security-layer unit tests.

The contract whitelist and transaction validator both expose module-global
singletons (``get_contract_whitelist`` / ``get_transaction_validator``).
These fixtures reset that global state between tests and provide freshly
constructed instances so tests never leak whitelist mutations into each other.
"""

import pytest

import src.security.contract_whitelist as cw_module
from src.security.contract_whitelist import ContractWhitelist
from src.security.transaction_validator import TransactionValidator


@pytest.fixture(autouse=True)
def _reset_whitelist_singleton():
    """Reset the module-global whitelist before and after every test."""
    cw_module._whitelist = None
    yield
    cw_module._whitelist = None


@pytest.fixture
def whitelist() -> ContractWhitelist:
    """A fresh, default ContractWhitelist (base-mainnet)."""
    return ContractWhitelist()


@pytest.fixture
def validator(whitelist: ContractWhitelist) -> TransactionValidator:
    """A strict-mode validator backed by a fresh whitelist."""
    return TransactionValidator(whitelist=whitelist, strict_mode=True)


# ---------------------------------------------------------------------------
# Known whitelisted addresses (from the default whitelist) used across tests.
# ---------------------------------------------------------------------------
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
AAVE_POOL = "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5"
MOONWELL_MUSDC = "0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22"
PERMIT2 = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
MORPHO_BLUE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"  # MEDIUM risk
UNKNOWN = "0x1111111111111111111111111111111111111111"


# ---------------------------------------------------------------------------
# Calldata builders.
# ---------------------------------------------------------------------------
def selector(sig4_hex: str) -> bytes:
    """Return the 4-byte selector for a hex string like '095ea7b3'."""
    return bytes.fromhex(sig4_hex)


def _word(value: int) -> bytes:
    """ABI-encode an int as a 32-byte big-endian word."""
    return value.to_bytes(32, "big")


def _addr_word(address: str) -> bytes:
    """ABI-encode an address into a left-padded 32-byte word."""
    return bytes(12) + bytes.fromhex(address[2:])


def erc20_approve_calldata(spender: str, amount: int) -> bytes:
    """Build ERC20 approve(address,uint256) calldata (68 bytes)."""
    return selector("095ea7b3") + _addr_word(spender) + _word(amount)
