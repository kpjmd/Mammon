"""In-memory fake of the contracts a Morpho vault integration touches.

FakeWeb3 stands in for web3.Web3: `eth.contract(address=..., abi=...)` returns a
contract whose `functions.<name>(*args)` yields an object with `.call()` (read)
and `.build_transaction(tx)` (write, recorded in `FakeWeb3.built`). Handlers are
plain values or callables keyed by function name, so each test states exactly
the on-chain state it depends on.

The default state models the pinned Gauntlet USDC Prime vault lending into
three markets with round numbers:
- idle market (irm = 0): no assets
- market B: supply 1000, borrow 900, fee 0, borrow APR 5%  -> vault holds ~500
- market C: supply 100, borrow 80, fee 10%, borrow APR 10% -> vault holds ~100
"""

from decimal import Decimal
from typing import Any, Callable, Dict, List, Tuple

from web3 import Web3

from src.protocols.morpho_vault import SECONDS_PER_YEAR, WAD, get_vault_spec

SPEC = get_vault_spec("USDC")
VAULT = Web3.to_checksum_address(SPEC.address)
MORPHO = Web3.to_checksum_address(SPEC.morpho)
USDC = Web3.to_checksum_address(SPEC.asset)
IRM = "0x46415998764C29aB2a25CbeA6254146D50D22687"
ZERO = "0x0000000000000000000000000000000000000000"
WALLET = "0xE06860747338660a0474b81E401BE60aeCf96f91"

MKT_IDLE = b"\x01" * 32
MKT_B = b"\x02" * 32
MKT_C = b"\x03" * 32


def rate_for_apr(apr_pct: str) -> int:
    """Per-second borrow rate (WAD) for a linear APR in percent."""
    return int(Decimal(apr_pct) / 100 * WAD / SECONDS_PER_YEAR)


def usdc(amount: str) -> int:
    return int(Decimal(amount) * 10**6)


class _Fn:
    def __init__(self, web3: "FakeWeb3", address: str, name: str, handler: Any, args: Tuple):
        self._web3, self._address, self._name = web3, address, name
        self._handler, self._args = handler, args

    def call(self) -> Any:
        if isinstance(self._handler, Exception):
            raise self._handler
        if callable(self._handler):
            return self._handler(*self._args)
        return self._handler

    def build_transaction(self, tx: Dict[str, Any]) -> Dict[str, Any]:
        self._web3.built.append((self._address, self._name, self._args))
        return {**tx, "to": self._address, "data": f"{self._name}{self._args}"}


class _Functions:
    def __init__(self, web3: "FakeWeb3", address: str, handlers: Dict[str, Any]):
        self._web3, self._address, self._handlers = web3, address, handlers

    def __getattr__(self, name: str) -> Callable[..., _Fn]:
        handler = self._handlers.get(name)
        if handler is None:
            raise AttributeError(f"{self._address} has no handler for {name}")
        return lambda *args: _Fn(self._web3, self._address, name, handler, args)


class _Contract:
    def __init__(self, functions: _Functions):
        self.functions = functions


class _Eth:
    def __init__(self, web3: "FakeWeb3"):
        self._web3 = web3

    def contract(self, address: str, abi: List[Dict[str, Any]]) -> _Contract:
        address = Web3.to_checksum_address(address)
        return _Contract(_Functions(self._web3, address, self._web3.state.get(address, {})))

    def get_transaction_count(self, address: str) -> int:
        return 7

    def wait_for_transaction_receipt(self, tx_hash: str) -> Dict[str, Any]:
        return {"status": self._web3.receipt_status, "gasUsed": 210000, "blockNumber": 123}


def _market(supply: str, borrow: str, fee: str = "0") -> Tuple[int, ...]:
    # (totalSupplyAssets, totalSupplyShares, totalBorrowAssets, totalBorrowShares,
    #  lastUpdate, fee) with 1e6 virtual-share scaling, as on Morpho Blue.
    return (
        usdc(supply), usdc(supply) * 10**6, usdc(borrow), usdc(borrow) * 10**6,
        1, int(Decimal(fee) * WAD),
    )


class FakeWeb3:
    """Fake chain with the default vault state described in the module doc."""

    def __init__(self) -> None:
        self.built: List[Tuple[str, str, Tuple]] = []
        self.receipt_status = 1
        self.eth = _Eth(self)
        markets = {MKT_IDLE: _market("0", "0"), MKT_B: _market("1000", "900"),
                   MKT_C: _market("100", "80", "0.1")}
        params = {
            MKT_IDLE: (USDC, ZERO, ZERO, ZERO, 0),
            MKT_B: (USDC, "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf", ZERO, IRM, 860000000000000000),
            MKT_C: (USDC, "0x4200000000000000000000000000000000000006", ZERO, IRM, 860000000000000000),
        }
        positions = {MKT_IDLE: 0, MKT_B: usdc("500") * 10**6, MKT_C: usdc("100") * 10**6}
        rates = {MKT_B: rate_for_apr("5"), MKT_C: rate_for_apr("10")}
        queue = [MKT_IDLE, MKT_B, MKT_C]
        self.share_price = 1_116_712_143_577  # assets per 1e24 shares (live-like)
        self.wallet_shares = 0
        self.max_deposit = 2**256 - 1
        self.max_withdraw: Any = None  # None -> full position
        self.allowance = 0

        self.state: Dict[str, Dict[str, Any]] = {
            VAULT: {
                "asset": USDC, "MORPHO": MORPHO, "curator": SPEC.curator,
                "owner": SPEC.owner, "fee": 0, "timelock": 604800,
                "totalAssets": usdc("600"),
                "withdrawQueueLength": len(queue),
                "withdrawQueue": lambda i: queue[i],
                "convertToAssets": lambda s: s * self.share_price // 10**24,
                "previewRedeem": lambda s: s * self.share_price // 10**24,
                "balanceOf": lambda a: self.wallet_shares,
                "maxDeposit": lambda a: self.max_deposit,
                "maxWithdraw": lambda a: (
                    self.wallet_shares * self.share_price // 10**24
                    if self.max_withdraw is None else self.max_withdraw
                ),
                "deposit": lambda *a: None, "withdraw": lambda *a: None,
                "redeem": lambda *a: None,
            },
            MORPHO: {
                "market": lambda mid: markets[mid],
                "position": lambda mid, user: (positions[mid], 0, 0),
                "idToMarketParams": lambda mid: params[mid],
            },
            Web3.to_checksum_address(IRM): {
                "borrowRateView": lambda p, m: rates[MKT_B if m[0] == usdc("1000") else MKT_C],
            },
            USDC: {
                "allowance": lambda o, s: self.allowance,
                "approve": lambda *a: None,
                "decimals": 6,
                "balanceOf": lambda a: usdc("1000"),
            },
        }

    def set_vault(self, **overrides: Any) -> None:
        self.state[VAULT].update(overrides)

    def wallet_holds(self, assets: str) -> None:
        """Give the wallet vault shares worth `assets` USDC."""
        self.wallet_shares = usdc(assets) * 10**24 // self.share_price + 1

    def wallet_position_raw(self) -> int:
        return self.wallet_shares * self.share_price // 10**24
