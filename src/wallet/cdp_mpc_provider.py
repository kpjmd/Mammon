"""CDP MPC Server Wallet provider (persistent, TEE-custodied custody).

Custody model
-------------
Private keys live inside Coinbase's Trusted Execution Environment and are
never materialized on this machine. Unlike
:class:`~src.wallet.local_wallet_provider.LocalWalletProvider`, no BIP-39 seed
or private key exists in this process, its environment, or on disk. This
directly remediates the Dec 2 2025 incident in which a plaintext, world-
readable seed phrase led to a drained wallet.

Persistence
-----------
The account is resolved by a stable *name* via ``get_or_create_account``:
the same ``CDP_ACCOUNT_NAME`` always yields the same address, on every run,
forever -- with nothing persisted locally that could be lost.

This is what coinbase-agentkit 0.7.4 gets wrong. Its ``CdpEvmWalletProvider``
branches on an optional ``address`` field and, when it is unset, calls
``create_account()`` -- minting a *fresh EOA every run*. MAMMON never set that
field, which is the true root cause of the "16+ wallets, funds stranded"
incident recorded in ``docs/archive/cdp_wallet_persistence_issue_RESOLVED.md``
(whose stated root cause -- "CDP can't load by address" -- is incorrect).

Why this bypasses AgentKit entirely
-----------------------------------
1. ``CdpEvmWalletProvider.send_transaction`` forwards only ``to``/``value``/
   ``data`` and DROPS ``gas``/``maxFeePerGas``/``maxPriorityFeePerGas``, even
   though ``cdp.evm_transaction_types.TransactionRequestEIP1559`` accepts all
   of them. Routing through it would silently void MAMMON's gas-price cap.
2. Its ``sign_transaction`` passes ``network=`` to an SDK method that does not
   accept it -- an unconditional ``TypeError``.
3. Its async bridging is only valid because the CDP SDK globally monkeypatches
   asyncio via ``nest_asyncio.apply()`` at import. See
   :mod:`src.wallet.async_bridge` for why we do not want to depend on that.

Of these, (1) is the decisive one: it would silently void a safety rail.
"""

from decimal import Decimal
from typing import Any, Dict, Optional

from cdp import CdpClient  # type: ignore[import-untyped]
from cdp.evm_transaction_types import (  # type: ignore[import-untyped]
    TransactionRequestEIP1559,
)
from hexbytes import HexBytes
from web3 import Web3
from web3.types import TxParams

from src.utils.logger import get_logger
from src.wallet.async_bridge import AsyncBridge
from src.wallet.base_provider import WalletProvider

logger = get_logger(__name__)

# MAMMON network id -> CDP SDK network id.
# Deliberately explicit: an unmapped network must fail loudly at init rather
# than silently transacting on the wrong chain.
_CDP_NETWORK_MAP: Dict[str, str] = {
    "base-mainnet": "base",
    "base": "base",
    "base-sepolia": "base-sepolia",
    "ethereum-mainnet": "ethereum",
    "ethereum": "ethereum",
    "ethereum-sepolia": "ethereum-sepolia",
}


class CdpMpcWalletProvider(WalletProvider):
    """Persistent MPC-custodied EVM Server Wallet backed by the CDP SDK.

    Attributes:
        web3: Web3 instance used for reads (balances, contract calls).
        address: Checksummed address of the resolved MPC account.
        account_name: Stable CDP account name used for persistence.
        network: MAMMON network id (e.g. "base-mainnet").
    """

    def __init__(
        self,
        api_key_id: str,
        api_key_secret: str,
        wallet_secret: str,
        network: str,
        web3: Web3,
        account_name: str = "mammon-hot",
        expected_address: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Resolve (or create) the named MPC account.

        Args:
            api_key_id: CDP API key id.
            api_key_secret: CDP API key secret.
            wallet_secret: CDP wallet secret (authorizes signing operations).
            network: MAMMON network id, e.g. "base-mainnet".
            web3: Web3 instance connected to the same network.
            account_name: Stable name that makes custody persistent.
            expected_address: If set, the resolved address MUST match. Guards
                against a typo'd name silently resolving to a fresh, empty
                account -- the exact failure mode that stranded funds before.
            config: Optional configuration dict.

        Raises:
            ValueError: If credentials are missing, the network is unsupported,
                or the resolved address does not match ``expected_address``.
        """
        if not api_key_id or not api_key_secret or not wallet_secret:
            raise ValueError(
                "CDP MPC custody requires api_key_id, api_key_secret and "
                "wallet_secret. Refusing to initialize with partial credentials."
            )

        if not account_name:
            raise ValueError(
                "account_name must be non-empty -- it is the persistence handle. "
                "An empty name would mint a new account every run."
            )

        cdp_network = _CDP_NETWORK_MAP.get(network.lower())
        if cdp_network is None:
            raise ValueError(
                f"Network {network!r} is not supported by CDP MPC custody. "
                f"Supported: {sorted(_CDP_NETWORK_MAP)}"
            )

        self.web3 = web3
        self.network = network
        self.account_name = account_name
        self.config = config or {}
        self._cdp_network = cdp_network
        self._bridge = AsyncBridge()

        # One long-lived client. Note: CdpClient.__aexit__ closes the client
        # permanently, so the `async with` per-call pattern used by AgentKit
        # would force a new client on every operation. Construct once instead.
        self._client = CdpClient(
            api_key_id=api_key_id,
            api_key_secret=api_key_secret,
            wallet_secret=wallet_secret,
        )

        try:
            account = self._bridge.run(self._client.evm.get_or_create_account(name=account_name))
        except Exception as e:
            self._bridge.close()
            raise ValueError(f"Failed to resolve CDP MPC account {account_name!r}: {e}") from e

        self._account = account
        self.address = Web3.to_checksum_address(account.address)

        if expected_address:
            expected = Web3.to_checksum_address(expected_address)
            if self.address != expected:
                self._bridge.close()
                raise ValueError(
                    f"CDP account name {account_name!r} resolved to {self.address}, "
                    f"but CDP_EXPECTED_ADDRESS is {expected}. Refusing to proceed: "
                    f"this usually means the account name is wrong and funds are "
                    f"held by a different account."
                )

        logger.info(f"✅ CdpMpcWalletProvider initialized: {self.address}")
        logger.info("   Custody: CDP MPC/TEE (no local key material)")
        logger.info(f"   Account name: {account_name} (persistent)")
        logger.info(f"   Network: {network} -> CDP {cdp_network}")

    def get_address(self) -> str:
        """Get the resolved MPC account address.

        Returns:
            Checksummed Ethereum address.
        """
        return self.address

    def get_balance(self, token: str = "ETH") -> Decimal:
        """Get native balance in whole ETH.

        Args:
            token: Token symbol, case-insensitive. Only ETH is supported here.

        Returns:
            Balance in whole ETH, per the WalletProvider contract.

        Raises:
            NotImplementedError: For non-ETH tokens.
        """
        if token.lower() != "eth":
            raise NotImplementedError(
                f"Token {token} not supported by CdpMpcWalletProvider. "
                f"ERC-20 balances are read via Web3 in WalletManager."
            )

        try:
            balance_wei = self.web3.eth.get_balance(self.address)
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return Decimal("0")

        # Scale here: the contract is whole units, callers must not re-scale.
        balance_eth = Decimal(balance_wei) / Decimal(10**18)
        logger.debug(f"Balance for {self.address}: {balance_eth} ETH")
        return balance_eth

    def send_transaction(self, transaction: TxParams) -> HexBytes:
        """Sign (in the TEE) and broadcast a transaction.

        Forwards the full EIP-1559 fee set. This is the critical difference
        from ``CdpEvmWalletProvider``, which drops the fee fields and would
        therefore void the gas-price cap enforced by WalletManager.

        ``nonce`` is intentionally omitted so CDP assigns it server-side.

        Args:
            transaction: Transaction params (to, value, data, gas, fees).

        Returns:
            Transaction hash as HexBytes, 0x-prefixed when hex-encoded.

        Raises:
            ValueError: If required fields are missing or the send fails.
        """
        if "to" not in transaction:
            raise ValueError("Transaction is missing required field 'to'")

        request = TransactionRequestEIP1559(
            to=Web3.to_checksum_address(transaction["to"]),
            value=int(transaction.get("value", 0) or 0),
            data=transaction.get("data") or "0x",
        )

        # Only set fee fields the caller actually provided. The SDK defaults
        # these to 0, which it treats as "estimate for me" -- so forwarding a
        # bogus 0 would be indistinguishable from omitting them.
        #
        # THIS IS THE SAFETY-CRITICAL PART: coinbase-agentkit's provider drops
        # these fields entirely, which would silently void the gas-price cap
        # that WalletManager.execute_transaction computes.
        tx_fields: Dict[str, Any] = dict(transaction)
        for field in ("gas", "maxFeePerGas", "maxPriorityFeePerGas"):
            value = tx_fields.get(field)
            if value is not None:
                setattr(request, field, int(value))

        logger.info(
            f"🔐 Submitting transaction to CDP MPC for signing "
            f"(gas={request.gas}, maxFee={request.maxFeePerGas}, "
            f"priority={request.maxPriorityFeePerGas})"
        )

        try:
            tx_hash = self._bridge.run(
                self._client.evm.send_transaction(
                    address=self.address,
                    transaction=request,
                    network=self._cdp_network,
                )
            )
        except Exception as e:
            logger.error(f"CDP transaction send failed: {e}")
            raise ValueError(f"Failed to send transaction via CDP MPC: {e}") from e

        normalized = self._normalize_tx_hash(tx_hash)
        logger.info(f"✅ Transaction sent: {normalized.hex()}")
        return normalized

    @staticmethod
    def _normalize_tx_hash(tx_hash: Any) -> HexBytes:
        """Normalize a CDP tx hash to HexBytes.

        The SDK returns a hex ``str``; the WalletProvider contract is HexBytes.
        Normalizing here keeps downstream consumers (ChainMonitor) uniform
        across providers.

        Args:
            tx_hash: Hash as returned by the CDP SDK.

        Returns:
            The hash as HexBytes.
        """
        if isinstance(tx_hash, HexBytes):
            return tx_hash
        if isinstance(tx_hash, (bytes, bytearray)):
            return HexBytes(bytes(tx_hash))
        return HexBytes(str(tx_hash))

    def sign_transaction(self, transaction: TxParams) -> bytes:
        """Not supported: CDP signs and broadcasts atomically.

        Args:
            transaction: Unused.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "CdpMpcWalletProvider cannot sign without sending. CDP's signing "
            "API takes a pre-serialized RLP transaction and keys never leave "
            "the TEE. Use send_transaction, which signs and broadcasts "
            "atomically."
        )

    def get_nonce(self) -> int:
        """Not supported: CDP assigns nonces server-side.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "CDP MPC Server Wallets assign nonces server-side. Omit 'nonce' "
            "from transactions and let CDP sequence them."
        )

    def reset_nonce(self) -> None:
        """Not supported: CDP assigns nonces server-side.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            "CDP MPC Server Wallets assign nonces server-side; there is no "
            "local nonce state to reset."
        )

    def close(self) -> None:
        """Release the CDP client and stop the async bridge.

        Idempotent.
        """
        try:
            self._bridge.run(self._client.close())
        except Exception as e:
            logger.warning(f"Error closing CDP client: {e}")
        finally:
            self._bridge.close()
