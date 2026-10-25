"""Morpho vault (MetaMorpho, ERC-4626) protocol integration.

A MetaMorpho vault pools deposits and a curator allocates them across isolated
Morpho Blue markets. To the depositor it behaves like a single lending pool:
deposit USDC, receive vault shares, and the shares appreciate as interest
accrues. That makes it executable with plain ERC-4626 calls, unlike raw Morpho
Blue markets (see morpho.py), which need per-market parameters.

Safety model (fail closed):
- Exactly one vault per token is allowlisted, pinned in MORPHO_VAULTS below
  (addresses verified on-chain), not read from .env, so a typo cannot redirect
  funds.
- Every scan re-verifies the pinned config (asset, Morpho Blue core, curator,
  owner) and governance bounds (timelock floor, fee ceiling). Any mismatch
  raises VaultGuardError, so the vault drops out of the scan and receives no
  new deposits. Withdrawals are never gated by the guard.
- MetaMorpho v1.0 realizes bad debt by lowering the share price, so a share
  price drop beyond a small RPC-lag tolerance trips a sticky in-process flag.
- No mock data in live mode: any read failure raises.

APY is computed on-chain: the vault's allocation-weighted Morpho Blue supply
rate, net of the vault fee. Rates use the same linear (APR) convention as the
Moonwell integration, which reads ~0.1pt below Morpho's compounded UI figure.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from web3 import Web3

from src.data.oracles import create_price_oracle
from src.security.audit import AuditEventType, AuditLogger, AuditSeverity
from src.utils.config import get_settings
from src.utils.logger import get_logger
from src.utils.web3_provider import get_web3

from .base import BaseProtocol, ProtocolPool

logger = get_logger(__name__)

PROTOCOL_NAME = "Morpho"

SECONDS_PER_YEAR = 31536000
WAD = 10**18
# Morpho Blue virtual shares/assets (SharesMathLib) used for share→asset math.
VIRTUAL_SHARES = 10**6
VIRTUAL_ASSETS = 1
# 1e24 shares (1e6 whole shares at 18 decimals) gives a precise share price.
SHARE_PRICE_SAMPLE_SHARES = 10**24
# A lagging RPC replica can serve a block a few seconds old, i.e. a share price
# a hair lower than the last read. Two hours of interest at 5% is ~0.1bp, so a
# 1bp tolerance absorbs lag while still catching any bad-debt event that
# matters.
SHARE_PRICE_DROP_TOLERANCE = Decimal("0.0001")

DEFAULT_MIN_TIMELOCK_SECONDS = 604800  # 7 days
DEFAULT_MAX_FEE = Decimal("0.05")  # 5% performance fee ceiling

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


@dataclass(frozen=True)
class VaultSpec:
    """Pinned, on-chain-verified identity of an allowlisted vault."""

    token: str
    address: str
    label: str
    pool_id: str
    asset: str
    asset_decimals: int
    morpho: str
    curator: str
    owner: str


# Verified on Base mainnet 2026-10-24 (eth_call): asset()=USDC,
# MORPHO()=Morpho Blue, fee()=0, timelock()=604800, MetaMorpho v1.0
# (factory 0xA9c3D3a366466Fa809d1Ae982Fb2c46E5fC41101).
MORPHO_VAULTS: Dict[str, Dict[str, VaultSpec]] = {
    "base-mainnet": {
        "USDC": VaultSpec(
            token="USDC",
            address="0xeE8F4eC5672F09119b96Ab6fB59C27E1b7e44b61",
            label="Gauntlet USDC Prime",
            pool_id="morpho-vault-gtusdcp",
            asset="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            asset_decimals=6,
            morpho="0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
            curator="0x9E33faAE38ff641094fa68c65c2cE600b3410585",
            owner="0x5a4E19842e09000a582c20A4f524C26Fb48Dd4D0",
        ),
    },
}


def get_vault_spec(token: str, network: str = "base-mainnet") -> VaultSpec:
    """Return the allowlisted vault for a token, or raise ValueError."""
    spec = MORPHO_VAULTS.get(network, {}).get(token)
    if spec is None:
        raise ValueError(f"No Morpho vault allowlisted for {token} on {network}")
    return spec


def _fn(
    name: str,
    inputs: List[Dict[str, Any]],
    outputs: List[Dict[str, Any]],
    mutability: str = "view",
) -> Dict[str, Any]:
    return {
        "inputs": inputs,
        "name": name,
        "outputs": outputs,
        "stateMutability": mutability,
        "type": "function",
    }


def _arg(name: str, typ: str) -> Dict[str, Any]:
    return {"internalType": typ, "name": name, "type": typ}


_ADDR = [_arg("", "address")]
_U256 = [_arg("", "uint256")]

# Minimal MetaMorpho ABI; every selector was confirmed by a live call on Base.
METAMORPHO_ABI: List[Dict[str, Any]] = [
    _fn("asset", [], _ADDR),
    _fn("MORPHO", [], _ADDR),
    _fn("curator", [], _ADDR),
    _fn("owner", [], _ADDR),
    _fn("fee", [], [_arg("", "uint96")]),
    _fn("timelock", [], _U256),
    _fn("totalAssets", [], _U256),
    _fn("withdrawQueueLength", [], _U256),
    _fn("withdrawQueue", [_arg("", "uint256")], [_arg("", "bytes32")]),
    _fn("balanceOf", [_arg("account", "address")], _U256),
    _fn("convertToAssets", [_arg("shares", "uint256")], _U256),
    _fn("previewRedeem", [_arg("shares", "uint256")], _U256),
    _fn("maxDeposit", [_arg("", "address")], _U256),
    _fn("maxWithdraw", [_arg("owner", "address")], _U256),
    _fn(
        "deposit",
        [_arg("assets", "uint256"), _arg("receiver", "address")],
        [_arg("shares", "uint256")],
        "nonpayable",
    ),
    _fn(
        "withdraw",
        [_arg("assets", "uint256"), _arg("receiver", "address"), _arg("owner", "address")],
        [_arg("shares", "uint256")],
        "nonpayable",
    ),
    _fn(
        "redeem",
        [_arg("shares", "uint256"), _arg("receiver", "address"), _arg("owner", "address")],
        [_arg("assets", "uint256")],
        "nonpayable",
    ),
]

_MARKET_PARAMS_COMPONENTS = [
    _arg("loanToken", "address"),
    _arg("collateralToken", "address"),
    _arg("oracle", "address"),
    _arg("irm", "address"),
    _arg("lltv", "uint256"),
]
_MARKET_COMPONENTS = [
    _arg("totalSupplyAssets", "uint128"),
    _arg("totalSupplyShares", "uint128"),
    _arg("totalBorrowAssets", "uint128"),
    _arg("totalBorrowShares", "uint128"),
    _arg("lastUpdate", "uint128"),
    _arg("fee", "uint128"),
]

MORPHO_BLUE_ABI: List[Dict[str, Any]] = [
    _fn("market", [_arg("id", "bytes32")], _MARKET_COMPONENTS),
    _fn(
        "position",
        [_arg("id", "bytes32"), _arg("user", "address")],
        [
            _arg("supplyShares", "uint256"),
            _arg("borrowShares", "uint128"),
            _arg("collateral", "uint128"),
        ],
    ),
    _fn("idToMarketParams", [_arg("id", "bytes32")], _MARKET_PARAMS_COMPONENTS),
]

IRM_ABI: List[Dict[str, Any]] = [
    _fn(
        "borrowRateView",
        [
            {
                "components": _MARKET_PARAMS_COMPONENTS,
                "internalType": "struct MarketParams",
                "name": "marketParams",
                "type": "tuple",
            },
            {
                "components": _MARKET_COMPONENTS,
                "internalType": "struct Market",
                "name": "market",
                "type": "tuple",
            },
        ],
        _U256,
    ),
]


class VaultGuardError(Exception):
    """The vault's on-chain state no longer matches its pinned allowlist."""


@dataclass
class VaultSnapshot:
    """Verified governance state of a vault at read time."""

    fee_wad: int
    timelock: int
    total_assets: int
    share_price: int

    @property
    def fee(self) -> Decimal:
        return Decimal(self.fee_wad) / Decimal(WAD)


@dataclass
class MarketAllocation:
    """The vault's position in one Morpho Blue market."""

    market_id: str
    collateral: str
    vault_assets: int
    available_liquidity: int
    supply_apr: Decimal  # percent


@dataclass
class VaultState:
    """Everything a scan learns about a vault."""

    snapshot: VaultSnapshot
    allocations: List[MarketAllocation] = field(default_factory=list)

    @property
    def gross_apr(self) -> Decimal:
        total = sum(a.vault_assets for a in self.allocations)
        if total == 0:
            return Decimal("0")
        weighted = sum(a.supply_apr * a.vault_assets for a in self.allocations)
        return Decimal(weighted) / Decimal(total)

    @property
    def net_apr(self) -> Decimal:
        return self.gross_apr * (Decimal(1) - self.snapshot.fee)

    @property
    def liquidity(self) -> int:
        return sum(a.available_liquidity for a in self.allocations)


def _same_address(a: str, b: str) -> bool:
    return Web3.to_checksum_address(a) == Web3.to_checksum_address(b)


def verify_vault_config(
    w3: Web3,
    spec: VaultSpec,
    min_timelock_seconds: int = DEFAULT_MIN_TIMELOCK_SECONDS,
    max_fee: Decimal = DEFAULT_MAX_FEE,
) -> VaultSnapshot:
    """Check a vault against its pinned identity and governance bounds.

    Raises:
        VaultGuardError: On any mismatch (wrong asset/core/curator/owner,
            timelock below the floor, fee above the ceiling).
    """
    vault = w3.eth.contract(address=Web3.to_checksum_address(spec.address), abi=METAMORPHO_ABI)
    pinned = {
        "asset": spec.asset,
        "MORPHO": spec.morpho,
        "curator": spec.curator,
        "owner": spec.owner,
    }
    for getter, expected in pinned.items():
        actual = getattr(vault.functions, getter)().call()
        if not _same_address(actual, expected):
            raise VaultGuardError(
                f"{spec.label}: {getter}() is {actual}, pinned {expected}"
            )

    timelock = int(vault.functions.timelock().call())
    if timelock < min_timelock_seconds:
        raise VaultGuardError(
            f"{spec.label}: timelock {timelock}s below floor {min_timelock_seconds}s"
        )
    fee_wad = int(vault.functions.fee().call())
    snapshot = VaultSnapshot(
        fee_wad=fee_wad,
        timelock=timelock,
        total_assets=int(vault.functions.totalAssets().call()),
        share_price=int(vault.functions.convertToAssets(SHARE_PRICE_SAMPLE_SHARES).call()),
    )
    if snapshot.fee > max_fee:
        raise VaultGuardError(f"{spec.label}: fee {snapshot.fee} above ceiling {max_fee}")
    return snapshot


def to_assets_down(shares: int, total_assets: int, total_shares: int) -> int:
    """Morpho Blue SharesMathLib.toAssetsDown."""
    return shares * (total_assets + VIRTUAL_ASSETS) // (total_shares + VIRTUAL_SHARES)


def supply_apr_percent(
    borrow_rate_per_second: int,
    total_supply_assets: int,
    total_borrow_assets: int,
    market_fee_wad: int,
) -> Decimal:
    """Linear supply APR (percent) of a Morpho Blue market."""
    if total_supply_assets == 0 or borrow_rate_per_second == 0:
        return Decimal("0")
    borrow_apr = Decimal(borrow_rate_per_second) * SECONDS_PER_YEAR / Decimal(WAD)
    utilization = Decimal(total_borrow_assets) / Decimal(total_supply_assets)
    fee = Decimal(market_fee_wad) / Decimal(WAD)
    return borrow_apr * utilization * (Decimal(1) - fee) * Decimal(100)


def read_market_allocation(
    w3: Web3, morpho: Any, vault_address: str, market_id: bytes
) -> MarketAllocation:
    """Read the vault's assets, liquidity and supply APR in one market."""
    market = morpho.functions.market(market_id).call()
    total_supply, total_supply_shares, total_borrow = market[0], market[1], market[2]
    supply_shares = morpho.functions.position(market_id, vault_address).call()[0]
    params = morpho.functions.idToMarketParams(market_id).call()
    collateral, irm = params[1], params[3]

    vault_assets = to_assets_down(supply_shares, total_supply, total_supply_shares)
    if _same_address(irm, ZERO_ADDRESS):
        # Idle market: holds USDC, earns nothing.
        apr = Decimal("0")
    else:
        irm_contract = w3.eth.contract(address=Web3.to_checksum_address(irm), abi=IRM_ABI)
        rate = irm_contract.functions.borrowRateView(tuple(params), tuple(market)).call()
        apr = supply_apr_percent(rate, total_supply, total_borrow, market[5])

    return MarketAllocation(
        market_id="0x" + bytes(market_id).hex(),
        collateral=collateral,
        vault_assets=vault_assets,
        available_liquidity=min(vault_assets, max(total_supply - total_borrow, 0)),
        supply_apr=apr,
    )


def read_vault_state(w3: Web3, spec: VaultSpec, snapshot: VaultSnapshot) -> VaultState:
    """Walk the vault's withdraw queue and read every market it lends into."""
    vault = w3.eth.contract(address=Web3.to_checksum_address(spec.address), abi=METAMORPHO_ABI)
    morpho = w3.eth.contract(address=Web3.to_checksum_address(spec.morpho), abi=MORPHO_BLUE_ABI)
    vault_address = Web3.to_checksum_address(spec.address)
    state = VaultState(snapshot=snapshot)
    length = int(vault.functions.withdrawQueueLength().call())
    for i in range(length):
        market_id = vault.functions.withdrawQueue(i).call()
        state.allocations.append(read_market_allocation(w3, morpho, vault_address, market_id))
    return state


class MorphoVaultProtocol(BaseProtocol):
    """Allowlisted MetaMorpho USDC vault, exposed as the "Morpho" protocol.

    Read-only: execution lives in ProtocolActionExecutor, which reuses
    verify_vault_config before every deposit.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(PROTOCOL_NAME, "base", config)
        self.network = config.get("network", "base-sepolia")
        self.read_only = config.get("read_only", True)
        self.use_mock_data = config.get("use_mock_data", False)
        self.audit_logger = AuditLogger()
        self.min_timelock_seconds = int(
            config.get("morpho_vault_min_timelock_seconds", DEFAULT_MIN_TIMELOCK_SECONDS)
        )
        self.max_fee = Decimal(str(config.get("morpho_vault_max_fee", DEFAULT_MAX_FEE)))
        # Vault data is always read from mainnet, like the other lending reads.
        self.vaults = MORPHO_VAULTS["base-mainnet"]
        self._last_share_price: Dict[str, int] = {}
        self._tripped: Dict[str, str] = {}
        self.web3: Optional[Web3] = None
        if not self.use_mock_data:
            self.web3 = get_web3("base-mainnet", config=get_settings())
        self._init_price_oracle(config)
        logger.info(
            f"MorphoVaultProtocol initialized: "
            f"{', '.join(f'{s.label} ({s.address})' for s in self.vaults.values())}"
        )

    def _init_price_oracle(self, config: Dict[str, Any]) -> None:
        if config.get("price_oracle") is not None:
            self.price_oracle = config["price_oracle"]
        elif config.get("chainlink_enabled", True):
            self.price_oracle = create_price_oracle(
                "chainlink",
                network="base-mainnet",
                price_network="base-mainnet",
                cache_ttl_seconds=config.get("chainlink_cache_ttl_seconds", 300),
                max_staleness_seconds=config.get("chainlink_max_staleness_seconds", 3600),
                fallback_to_mock=config.get("chainlink_fallback_to_mock", True),
            )
        else:
            self.price_oracle = create_price_oracle("mock")

    def _require_web3(self) -> Web3:
        if self.web3 is None:
            raise RuntimeError("MorphoVaultProtocol has no web3 (mock mode)")
        return self.web3

    def _check_share_price(self, spec: VaultSpec, share_price: int) -> None:
        """Trip (sticky) if the share price fell beyond the RPC-lag tolerance."""
        if spec.address in self._tripped:
            raise VaultGuardError(self._tripped[spec.address])
        last = self._last_share_price.get(spec.address)
        if last is not None and share_price < last:
            drop = Decimal(last - share_price) / Decimal(last)
            if drop > SHARE_PRICE_DROP_TOLERANCE:
                reason = (
                    f"{spec.label}: share price fell {drop:.6%} "
                    f"({last} -> {share_price}); possible bad debt. Deposits "
                    f"blocked until restart."
                )
                self._tripped[spec.address] = reason
                raise VaultGuardError(reason)
            return  # within tolerance: keep the higher reference
        self._last_share_price[spec.address] = share_price

    async def _usd_price(self, token: str) -> Decimal:
        try:
            return Decimal(str(await self.price_oracle.get_price(token)))
        except Exception as e:
            # TVL is informational only (never sizes a trade); USDC ~ $1.
            logger.warning(f"[MORPHO] Price oracle failed for {token}: {e}; using $1")
            return Decimal("1")

    async def _build_pool(self, spec: VaultSpec) -> ProtocolPool:
        w3 = self._require_web3()
        try:
            snapshot = verify_vault_config(w3, spec, self.min_timelock_seconds, self.max_fee)
            self._check_share_price(spec, snapshot.share_price)
        except VaultGuardError as e:
            logger.error(f"[MORPHO] Vault guard tripped, excluding vault: {e}")
            await self.audit_logger.log_event(
                AuditEventType.RISK_ALERT,
                AuditSeverity.CRITICAL,
                f"Morpho vault guard tripped: {e}",
                metadata={"protocol": PROTOCOL_NAME, "vault": spec.address},
            )
            raise
        state = read_vault_state(w3, spec, snapshot)
        scale = Decimal(10**spec.asset_decimals)
        price = await self._usd_price(spec.token)
        return ProtocolPool(
            pool_id=spec.pool_id,
            name=f"{spec.label} Vault",
            tokens=[spec.token],
            apy=state.net_apr,
            tvl=Decimal(snapshot.total_assets) / scale * price,
            metadata={
                "vault_address": spec.address,
                "vault_label": spec.label,
                "curator": spec.curator,
                "fee": snapshot.fee,
                "timelock": snapshot.timelock,
                "gross_apy": state.gross_apr,
                "liquidity": Decimal(state.liquidity) / scale,
                "share_price": snapshot.share_price,
                "allocations": [
                    {
                        "market_id": a.market_id,
                        "collateral": a.collateral,
                        "assets": Decimal(a.vault_assets) / scale,
                        "supply_apy": a.supply_apr,
                    }
                    for a in state.allocations
                    if a.vault_assets > 0
                ],
                "protocol_version": "metamorpho-v1",
                "risk_tier": "medium",
            },
        )

    async def get_pools(self) -> List[ProtocolPool]:
        """Return the allowlisted vault(s). Raises on any failure (fail closed)."""
        await self.audit_logger.log_event(
            AuditEventType.POOL_QUERY,
            AuditSeverity.INFO,
            "Morpho vault get_pools",
            metadata={"protocol": PROTOCOL_NAME, "data_source": "real_mainnet"},
        )
        if self.use_mock_data:
            return self._get_mock_pools()
        pools = [await self._build_pool(spec) for spec in self.vaults.values()]
        for pool in pools:
            logger.info(
                f"✅ [MORPHO] {pool.name}: {pool.apy:.2f}% net APY, ${pool.tvl:,.0f} TVL, "
                f"{pool.metadata['liquidity']:,.0f} USDC withdrawable"
            )
        return pools

    def _get_mock_pools(self) -> List[ProtocolPool]:
        return [
            ProtocolPool(
                pool_id=spec.pool_id,
                name=f"{spec.label} Vault",
                tokens=[spec.token],
                apy=Decimal("4.5"),
                tvl=Decimal("400000000"),
                metadata={"vault_address": spec.address, "mock": True},
            )
            for spec in self.vaults.values()
        ]

    def _spec_for_pool(self, pool_id: str) -> VaultSpec:
        for spec in self.vaults.values():
            if spec.pool_id == pool_id:
                return spec
        raise ValueError(f"Unknown Morpho vault pool_id: {pool_id}")

    async def get_pool_apy(self, pool_id: str) -> Decimal:
        for pool in await self.get_pools():
            if pool.pool_id == pool_id:
                return pool.apy
        raise ValueError(f"Unknown Morpho vault pool_id: {pool_id}")

    async def get_user_balance(self, pool_id: str, user_address: str) -> Decimal:
        """Underlying assets held: convertToAssets(balanceOf(user)).

        Raises on RPC failure rather than returning 0, so reconcile treats the
        pool as unchecked instead of closing a live position.
        """
        if self.use_mock_data:
            return Decimal("0")
        spec = self._spec_for_pool(pool_id)
        w3 = self._require_web3()
        vault = w3.eth.contract(address=Web3.to_checksum_address(spec.address), abi=METAMORPHO_ABI)
        shares = int(vault.functions.balanceOf(Web3.to_checksum_address(user_address)).call())
        if shares == 0:
            return Decimal("0")
        assets = int(vault.functions.convertToAssets(shares).call())
        return Decimal(assets) / Decimal(10**spec.asset_decimals)

    async def deposit(self, pool_id: str, token: str, amount: Decimal) -> str:
        """Execution lives in ProtocolActionExecutor; this class is read-only."""
        raise NotImplementedError(
            "MorphoVaultProtocol is read-only; deposits go through ProtocolActionExecutor"
        )

    async def withdraw(self, pool_id: str, token: str, amount: Decimal) -> str:
        """Execution lives in ProtocolActionExecutor; this class is read-only."""
        raise NotImplementedError(
            "MorphoVaultProtocol is read-only; withdrawals go through ProtocolActionExecutor"
        )

    async def estimate_gas(self, operation: str, params: Dict[str, Any]) -> int:
        """Typical MetaMorpho gas: deposit/withdraw loop over the vault queues."""
        estimates = {"approve": 50000, "deposit": 300000, "withdraw": 350000}
        return estimates.get(operation, 350000)

    @property
    def safety_score(self) -> int:
        """Morpho Blue core + curator layer; pinned guards bound curator risk."""
        return 85

    def __repr__(self) -> str:
        labels = ", ".join(s.label for s in self.vaults.values())
        return f"MorphoVaultProtocol(vaults=[{labels}], safety_score={self.safety_score})"
