"""Token utilities for MAMMON.

Provides ERC20 token interaction utilities for querying balances,
metadata, and allowances across multiple networks.
"""

from .erc20 import ERC20Token, get_token_balance, get_token_info

__all__ = ["ERC20Token", "get_token_balance", "get_token_info"]
