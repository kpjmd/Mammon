"""Tests for CdpMpcWalletProvider.

All CDP calls are mocked -- these tests never touch the network and never
create real accounts.

Two of these are regression tests for the incidents that motivated WS7:

- Persistence: coinbase-agentkit minted a NEW EOA per run, stranding funds
  across 16+ wallets. ``get_or_create_account(name=...)`` must be the only
  account-resolution path, and ``create_account`` must never be called.
- Fee forwarding: AgentKit drops EIP-1559 fee fields on send, which would
  silently void the gas-price cap enforced by WalletManager.
"""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest
from web3.types import HexBytes

from src.wallet.cdp_mpc_provider import CdpMpcWalletProvider

# EIP-55 checksummed; the provider checksums whatever it resolves.
FUNDED_ADDRESS = "0x742d35CC6634c0532925a3B844bC9e7595F0BeB4"
OTHER_ADDRESS = "0x1111111111111111111111111111111111111111"
RECIPIENT = "0x2222222222222222222222222222222222222222"


@pytest.fixture
def mock_web3():
    """Web3 double returning a fixed 1 ETH native balance."""
    web3 = Mock()
    web3.eth.get_balance = Mock(return_value=10**18)
    return web3


@pytest.fixture
def mock_cdp_client():
    """Patch CdpClient so no real client or network call is constructed.

    Returns the client instance double, whose ``evm`` surface is an
    ``AsyncMock``-backed namespace.
    """
    with patch("src.wallet.cdp_mpc_provider.CdpClient") as client_cls:
        client = MagicMock()

        account = Mock()
        account.address = FUNDED_ADDRESS

        async def _get_or_create_account(name=None):
            return account

        async def _send_transaction(address=None, transaction=None, network=None):
            _send_transaction.calls.append(
                {"address": address, "transaction": transaction, "network": network}
            )
            return "0x" + "ab" * 32

        _send_transaction.calls = []

        async def _close():
            return None

        client.evm.get_or_create_account = Mock(side_effect=_get_or_create_account)
        client.evm.create_account = Mock()
        client.evm.get_account = Mock()
        client.evm.send_transaction = Mock(side_effect=_send_transaction)
        client.close = Mock(side_effect=_close)

        client_cls.return_value = client
        yield client


def _make_provider(mock_web3, **overrides):
    """Construct a provider with sane test defaults."""
    kwargs = dict(
        api_key_id="key-id",
        api_key_secret="key-secret",
        wallet_secret="wallet-secret",
        network="base-mainnet",
        web3=mock_web3,
        account_name="mammon-hot",
    )
    kwargs.update(overrides)
    return CdpMpcWalletProvider(**kwargs)


class TestPersistence:
    """The core WS7 guarantee: same name -> same address, every run."""

    def test_resolves_account_by_name(self, mock_cdp_client, mock_web3):
        """Account is resolved via get_or_create_account(name=...)."""
        provider = _make_provider(mock_web3)
        try:
            mock_cdp_client.evm.get_or_create_account.assert_called_once_with(name="mammon-hot")
            assert provider.get_address() == FUNDED_ADDRESS
        finally:
            provider.close()

    def test_never_calls_create_account(self, mock_cdp_client, mock_web3):
        """Regression: create_account is what minted a new EOA every run.

        AgentKit calls it whenever its optional `address` field is unset. This
        provider must never reach that path.
        """
        provider = _make_provider(mock_web3)
        try:
            mock_cdp_client.evm.create_account.assert_not_called()
        finally:
            provider.close()

    def test_repeated_construction_yields_same_address(self, mock_cdp_client, mock_web3):
        """Two runs with the same name resolve to the same address.

        This is the property whose absence stranded funds across 16+ wallets.
        """
        first = _make_provider(mock_web3)
        first_address = first.get_address()
        first.close()

        second = _make_provider(mock_web3)
        second_address = second.get_address()
        second.close()

        assert first_address == second_address == FUNDED_ADDRESS
        assert mock_cdp_client.evm.create_account.call_count == 0

    def test_empty_account_name_rejected(self, mock_cdp_client, mock_web3):
        """An empty name would defeat persistence, so it is refused."""
        with pytest.raises(ValueError, match="persistence handle"):
            _make_provider(mock_web3, account_name="")


class TestExpectedAddressGuard:
    """The safety net against a typo'd account name."""

    def test_matching_expected_address_succeeds(self, mock_cdp_client, mock_web3):
        """A matching expected address permits startup."""
        provider = _make_provider(mock_web3, expected_address=FUNDED_ADDRESS)
        try:
            assert provider.get_address() == FUNDED_ADDRESS
        finally:
            provider.close()

    def test_mismatched_expected_address_raises(self, mock_cdp_client, mock_web3):
        """A mismatch must abort rather than run against an empty account."""
        with pytest.raises(ValueError, match="CDP_EXPECTED_ADDRESS"):
            _make_provider(mock_web3, expected_address=OTHER_ADDRESS)

    def test_expected_address_is_case_insensitive(self, mock_cdp_client, mock_web3):
        """Checksum casing must not cause a spurious mismatch."""
        provider = _make_provider(mock_web3, expected_address=FUNDED_ADDRESS.lower())
        try:
            assert provider.get_address() == FUNDED_ADDRESS
        finally:
            provider.close()


class TestFeeForwarding:
    """The gas-price cap is only real if the fee fields reach the chain."""

    def test_forwards_all_eip1559_fee_fields(self, mock_cdp_client, mock_web3):
        """Regression: AgentKit drops these, silently voiding the gas cap."""
        provider = _make_provider(mock_web3)
        try:
            provider.send_transaction(
                {
                    "to": RECIPIENT,
                    "value": 10**17,
                    "gas": 21000,
                    "maxFeePerGas": 5_000_000_000,
                    "maxPriorityFeePerGas": 1_000_000_000,
                }
            )
        finally:
            provider.close()

        request = mock_cdp_client.evm.send_transaction.call_args.kwargs["transaction"]
        assert request.gas == 21000
        assert request.maxFeePerGas == 5_000_000_000
        assert request.maxPriorityFeePerGas == 1_000_000_000
        assert request.value == 10**17

    def test_omitted_fee_fields_left_for_cdp_to_estimate(self, mock_cdp_client, mock_web3):
        """Absent fee fields must not be forwarded as a bogus explicit 0."""
        provider = _make_provider(mock_web3)
        try:
            provider.send_transaction({"to": RECIPIENT, "value": 0})
        finally:
            provider.close()

        request = mock_cdp_client.evm.send_transaction.call_args.kwargs["transaction"]
        # SDK default 0 means "estimate for me".
        assert request.gas == 0
        assert request.maxFeePerGas == 0

    def test_sends_on_mapped_network(self, mock_cdp_client, mock_web3):
        """MAMMON's network id is translated to the CDP network id."""
        provider = _make_provider(mock_web3, network="base-mainnet")
        try:
            provider.send_transaction({"to": RECIPIENT})
        finally:
            provider.close()

        assert mock_cdp_client.evm.send_transaction.call_args.kwargs["network"] == "base"

    def test_missing_to_field_rejected(self, mock_cdp_client, mock_web3):
        """A transaction without a recipient is refused before any send."""
        provider = _make_provider(mock_web3)
        try:
            with pytest.raises(ValueError, match="'to'"):
                provider.send_transaction({"value": 1})
            mock_cdp_client.evm.send_transaction.assert_not_called()
        finally:
            provider.close()

    def test_returns_hexbytes_hash(self, mock_cdp_client, mock_web3):
        """The SDK returns a str hash; the ABC contract is HexBytes.

        Note: hexbytes >= 1.0 returns an UNPREFIXED string from .hex(), so the
        0x prefix is re-added by WalletManager, not here. This asserts the
        decoded bytes are correct rather than the string formatting.
        """
        provider = _make_provider(mock_web3)
        try:
            tx_hash = provider.send_transaction({"to": RECIPIENT})
        finally:
            provider.close()

        assert isinstance(tx_hash, HexBytes)
        assert tx_hash == HexBytes("0x" + "ab" * 32)


class TestBalance:
    """get_balance must honor the whole-token-units contract."""

    def test_returns_whole_eth_not_wei(self, mock_cdp_client, mock_web3):
        """1e18 wei must surface as Decimal('1'), scaled inside the provider."""
        provider = _make_provider(mock_web3)
        try:
            assert provider.get_balance("ETH") == Decimal("1")
        finally:
            provider.close()

    def test_token_argument_is_case_insensitive(self, mock_cdp_client, mock_web3):
        """'eth' and 'ETH' behave identically."""
        provider = _make_provider(mock_web3)
        try:
            assert provider.get_balance("eth") == provider.get_balance("ETH")
        finally:
            provider.close()

    def test_non_eth_token_raises(self, mock_cdp_client, mock_web3):
        """ERC-20 balances are read elsewhere; don't silently return 0."""
        provider = _make_provider(mock_web3)
        try:
            with pytest.raises(NotImplementedError):
                provider.get_balance("USDC")
        finally:
            provider.close()

    def test_rpc_failure_returns_zero(self, mock_cdp_client, mock_web3):
        """An RPC error degrades to 0 rather than crashing the loop."""
        mock_web3.eth.get_balance = Mock(side_effect=Exception("rpc down"))
        provider = _make_provider(mock_web3)
        try:
            assert provider.get_balance("ETH") == Decimal("0")
        finally:
            provider.close()


class TestUnsupportedOperations:
    """Operations that MUST fail loudly rather than silently misbehave."""

    def test_sign_transaction_raises(self, mock_cdp_client, mock_web3):
        """Keys never leave the TEE, so detached signing is impossible."""
        provider = _make_provider(mock_web3)
        try:
            with pytest.raises(NotImplementedError, match="without sending"):
                provider.sign_transaction({"to": RECIPIENT})
        finally:
            provider.close()

    def test_get_nonce_raises(self, mock_cdp_client, mock_web3):
        """CDP assigns nonces server-side; a local guess would be wrong."""
        provider = _make_provider(mock_web3)
        try:
            with pytest.raises(NotImplementedError, match="server-side"):
                provider.get_nonce()
        finally:
            provider.close()

    def test_reset_nonce_raises(self, mock_cdp_client, mock_web3):
        """There is no local nonce state to reset."""
        provider = _make_provider(mock_web3)
        try:
            with pytest.raises(NotImplementedError, match="server-side"):
                provider.reset_nonce()
        finally:
            provider.close()


class TestConstructionGuards:
    """Fail fast on misconfiguration."""

    @pytest.mark.parametrize(
        "missing",
        ["api_key_id", "api_key_secret", "wallet_secret"],
    )
    def test_partial_credentials_rejected(self, mock_cdp_client, mock_web3, missing):
        """Refuse to initialize with incomplete credentials."""
        with pytest.raises(ValueError, match="partial credentials"):
            _make_provider(mock_web3, **{missing: ""})

    def test_unsupported_network_rejected(self, mock_cdp_client, mock_web3):
        """An unmapped network must fail loudly, not transact on a wrong chain."""
        with pytest.raises(ValueError, match="not supported"):
            _make_provider(mock_web3, network="arbitrum-sepolia")

    def test_account_resolution_failure_is_wrapped(self, mock_cdp_client, mock_web3):
        """A CDP-side failure surfaces as a clear ValueError."""

        async def _fail(name=None):
            raise RuntimeError("cdp unavailable")

        mock_cdp_client.evm.get_or_create_account = Mock(side_effect=_fail)

        with pytest.raises(ValueError, match="Failed to resolve CDP MPC account"):
            _make_provider(mock_web3)
