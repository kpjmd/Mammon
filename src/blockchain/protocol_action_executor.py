"""Protocol-specific transaction execution without modifying BaseProtocol.

This module handles transaction execution for DeFi protocols (withdraw, deposit, approve)
while keeping transaction logic separate from read-only protocol implementations.

Phase 4 Sprint 3: Aave V3, Moonwell, and Morpho support.
"""

from typing import Any, Dict, Optional
from decimal import Decimal
from web3 import Web3
from src.blockchain.wallet import WalletManager
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.utils.logger import get_logger
from src.utils.web3_provider import get_web3
from src.utils.config import get_settings

logger = get_logger(__name__)


# Aave V3 Pool contract addresses
AAVE_V3_POOL_ADDRESSES = {
    "base-mainnet": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
    "base-sepolia": "0x07eA79F68B2B3df564D0A34F8e19D9B1e339814b",  # Aave V3 testnet
}

# Moonwell contract addresses (Compound V2 fork)
MOONWELL_COMPTROLLER_ADDRESSES = {
    "base-mainnet": "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C",
    "base-sepolia": "0xfBb21d0380beE3312B33c4353c8936a0F13EF26C",  # Using mainnet for testing
}

# Moonwell mToken addresses (similar to cTokens)
MOONWELL_MTOKEN_ADDRESSES = {
    "base-mainnet": {
        "USDC": "0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22",  # mUSDC
        "WETH": "0x628ff693426583D9a7FB391E54366292F509D457",  # mWETH
    },
    "base-sepolia": {
        "USDC": "0xEdc817A28E8B93B03976FBd4a3dDBc9f7D176c22",  # Using mainnet for testing
        "WETH": "0x628ff693426583D9a7FB391E54366292F509D457",  # Using mainnet for testing
    },
}

# Morpho Blue contract addresses
MORPHO_BLUE_ADDRESSES = {
    "base-mainnet": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
    "base-sepolia": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",  # Using mainnet for testing
}

# Aave V3 Pool ABI for transactions
AAVE_V3_POOL_TRANSACTION_ABI = [
    # supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode)
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "onBehalfOf", "type": "address"},
            {"internalType": "uint16", "name": "referralCode", "type": "uint16"},
        ],
        "name": "supply",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # withdraw(address asset, uint256 amount, address to)
    {
        "inputs": [
            {"internalType": "address", "name": "asset", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "address", "name": "to", "type": "address"},
        ],
        "name": "withdraw",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# Moonwell mToken ABI (Compound V2 style)
MOONWELL_MTOKEN_ABI = [
    # mint(uint256 mintAmount) - deposit underlying token
    {
        "inputs": [{"internalType": "uint256", "name": "mintAmount", "type": "uint256"}],
        "name": "mint",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # redeem(uint256 redeemTokens) - withdraw by mToken amount
    {
        "inputs": [{"internalType": "uint256", "name": "redeemTokens", "type": "uint256"}],
        "name": "redeem",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # redeemUnderlying(uint256 redeemAmount) - withdraw by underlying amount
    {
        "inputs": [{"internalType": "uint256", "name": "redeemAmount", "type": "uint256"}],
        "name": "redeemUnderlying",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# Morpho Blue ABI (simplified)
MORPHO_BLUE_ABI = [
    # supply(MarketParams memory marketParams, uint256 assets, uint256 shares, address onBehalf, bytes memory data)
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "loanToken", "type": "address"},
                    {"internalType": "address", "name": "collateralToken", "type": "address"},
                    {"internalType": "address", "name": "oracle", "type": "address"},
                    {"internalType": "address", "name": "irm", "type": "address"},
                    {"internalType": "uint256", "name": "lltv", "type": "uint256"},
                ],
                "internalType": "struct MarketParams",
                "name": "marketParams",
                "type": "tuple",
            },
            {"internalType": "uint256", "name": "assets", "type": "uint256"},
            {"internalType": "uint256", "name": "shares", "type": "uint256"},
            {"internalType": "address", "name": "onBehalf", "type": "address"},
            {"internalType": "bytes", "name": "data", "type": "bytes"},
        ],
        "name": "supply",
        "outputs": [
            {"internalType": "uint256", "name": "assetsSupplied", "type": "uint256"},
            {"internalType": "uint256", "name": "sharesSupplied", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # withdraw(MarketParams memory marketParams, uint256 assets, uint256 shares, address onBehalf, address receiver)
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "loanToken", "type": "address"},
                    {"internalType": "address", "name": "collateralToken", "type": "address"},
                    {"internalType": "address", "name": "oracle", "type": "address"},
                    {"internalType": "address", "name": "irm", "type": "address"},
                    {"internalType": "uint256", "name": "lltv", "type": "uint256"},
                ],
                "internalType": "struct MarketParams",
                "name": "marketParams",
                "type": "tuple",
            },
            {"internalType": "uint256", "name": "assets", "type": "uint256"},
            {"internalType": "uint256", "name": "shares", "type": "uint256"},
            {"internalType": "address", "name": "onBehalf", "type": "address"},
            {"internalType": "address", "name": "receiver", "type": "address"},
        ],
        "name": "withdraw",
        "outputs": [
            {"internalType": "uint256", "name": "assetsWithdrawn", "type": "uint256"},
            {"internalType": "uint256", "name": "sharesWithdrawn", "type": "uint256"},
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ERC20 ABI for approve and balance checks
ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Token addresses on Base networks
TOKEN_ADDRESSES = {
    "base-mainnet": {
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "USDbC": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
        "WETH": "0x4200000000000000000000000000000000000006",
        "DAI": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
    },
    "base-sepolia": {
        "USDC": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # Testnet USDC
        "WETH": "0x4200000000000000000000000000000000000006",  # WETH on Base
    },
}


class ProtocolActionExecutor:
    """Executes protocol-specific transactions WITHOUT modifying BaseProtocol.

    This class handles transaction execution for DeFi protocols while keeping
    the transaction logic separate from the read-only protocol implementations.

    Phase 4 Sprint 1: Only Aave V3 is supported.
    Phase 5+: Will add Morpho, Moonwell, Aerodrome support.

    Attributes:
        wallet: WalletManager instance for transaction signing
        config: Configuration dictionary
        network: Network identifier (base-mainnet or base-sepolia)
        dry_run_mode: If True, simulates transactions without execution
        audit_logger: Audit logging instance
        w3: Web3 instance for contract interactions
    """

    def __init__(self, wallet_manager: WalletManager, config: Dict[str, Any]) -> None:
        """Initialize the protocol action executor.

        Args:
            wallet_manager: WalletManager instance
            config: Configuration dictionary
        """
        self.wallet = wallet_manager
        self.config = config
        self.network = config.get("network", "base-sepolia")
        self.dry_run_mode = config.get("dry_run_mode", True)
        self.audit_logger = AuditLogger()

        # Get Web3 instance with premium RPC support
        settings = get_settings()
        self.w3 = get_web3(self.network, config=settings)

        # Initialize contract instances
        self.aave_pool_address = AAVE_V3_POOL_ADDRESSES.get(self.network)
        if self.aave_pool_address:
            self.aave_pool = self.w3.eth.contract(
                address=self.aave_pool_address,
                abi=AAVE_V3_POOL_TRANSACTION_ABI,
            )
        else:
            self.aave_pool = None
            logger.warning(f"Aave V3 Pool address not configured for {self.network}")

        logger.info(
            f"ProtocolActionExecutor initialized for {self.network} "
            f"(dry_run={self.dry_run_mode})"
        )

    def _get_token_address(self, token: str) -> str:
        """Get token contract address for current network.

        Args:
            token: Token symbol (e.g., "USDC", "WETH")

        Returns:
            Token contract address

        Raises:
            ValueError: If token not found for network
        """
        network_tokens = TOKEN_ADDRESSES.get(self.network, {})
        if token not in network_tokens:
            raise ValueError(
                f"Token {token} not configured for {self.network}. "
                f"Available tokens: {list(network_tokens.keys())}"
            )
        return network_tokens[token]

    async def execute_approve(
        self,
        token: str,
        spender: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """Execute ERC20 token approval (protocol-agnostic).

        Args:
            token: Token symbol (e.g., "USDC")
            spender: Spender address (protocol contract)
            amount: Amount to approve

        Returns:
            Transaction receipt with hash, gas_used, etc.

        Raises:
            ValueError: If token not found or approval fails
        """
        token_address = self._get_token_address(token)

        logger.info(f"Approving {amount} {token} for spender {spender[:8]}...")

        # Create ERC20 contract instance
        token_contract = self.w3.eth.contract(
            address=token_address,
            abi=ERC20_ABI,
        )

        # Get token decimals
        decimals = token_contract.functions.decimals().call()
        amount_wei = int(amount * Decimal(10**decimals))

        # Build approval transaction
        wallet_address = await self.wallet.get_address()
        tx_data = token_contract.functions.approve(
            spender, amount_wei
        ).build_transaction({
            "from": wallet_address,
            "nonce": self.w3.eth.get_transaction_count(wallet_address),
        })

        if self.dry_run_mode:
            logger.info(f"[DRY RUN] Would approve {amount} {token} for {spender[:8]}")
            return {
                "success": True,
                "tx_hash": f"0xdryrun_approve_{token}",
                "gas_used": 50000,
                "dry_run": True,
            }

        # Execute transaction via WalletManager
        tx_hash = await self.wallet.send_transaction(
            to=token_address,
            data=tx_data["data"],
            value=Decimal("0"),
        )

        # Wait for confirmation
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        result = {
            "success": receipt["status"] == 1,
            "tx_hash": tx_hash,
            "gas_used": receipt["gasUsed"],
            "block_number": receipt["blockNumber"],
        }

        await self.audit_logger.log_event(
            AuditEventType.TRANSACTION_SUBMITTED,
            AuditSeverity.INFO,
            f"Approved {amount} {token} for {spender}",
            metadata={
                "token": token,
                "spender": spender,
                "amount": str(amount),
                "tx_hash": tx_hash,
            },
        )

        logger.info(f"✅ Approval successful: {tx_hash}")
        return result

    async def execute_withdraw(
        self,
        protocol_name: str,
        token: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """Execute protocol-specific withdrawal.

        Args:
            protocol_name: Protocol name (e.g., "Aave V3", "Moonwell", "Morpho")
            token: Token symbol to withdraw
            amount: Amount to withdraw

        Returns:
            Transaction receipt

        Raises:
            NotImplementedError: If protocol not supported
            ValueError: If withdrawal fails
        """
        if protocol_name == "Aave V3":
            return await self._withdraw_aave_v3(token, amount)
        elif protocol_name == "Moonwell":
            return await self._withdraw_moonwell(token, amount)
        elif protocol_name == "Morpho":
            return await self._withdraw_morpho(token, amount)
        else:
            raise NotImplementedError(
                f"Transaction execution not yet supported for {protocol_name}. "
                f"Supported protocols: Aave V3, Moonwell, Morpho"
            )

    async def execute_deposit(
        self,
        protocol_name: str,
        token: str,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """Execute protocol-specific deposit.

        Args:
            protocol_name: Protocol name (e.g., "Aave V3", "Moonwell", "Morpho")
            token: Token symbol to deposit
            amount: Amount to deposit

        Returns:
            Transaction receipt

        Raises:
            NotImplementedError: If protocol not supported
            ValueError: If deposit fails
        """
        if protocol_name == "Aave V3":
            return await self._deposit_aave_v3(token, amount)
        elif protocol_name == "Moonwell":
            return await self._deposit_moonwell(token, amount)
        elif protocol_name == "Morpho":
            return await self._deposit_morpho(token, amount)
        else:
            raise NotImplementedError(
                f"Transaction execution not yet supported for {protocol_name}. "
                f"Supported protocols: Aave V3, Moonwell, Morpho"
            )

    async def _withdraw_aave_v3(self, token: str, amount: Decimal) -> Dict[str, Any]:
        """Execute Aave V3 withdrawal.

        Args:
            token: Token symbol to withdraw
            amount: Amount to withdraw

        Returns:
            Transaction receipt
        """
        if not self.aave_pool:
            raise ValueError(f"Aave V3 Pool not configured for {self.network}")

        token_address = self._get_token_address(token)
        wallet_address = await self.wallet.get_address()

        logger.info(f"Withdrawing {amount} {token} from Aave V3...")

        # Get token decimals
        token_contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
        decimals = token_contract.functions.decimals().call()
        amount_wei = int(amount * Decimal(10**decimals))

        # Build withdraw transaction
        # withdraw(address asset, uint256 amount, address to)
        tx_data = self.aave_pool.functions.withdraw(
            token_address,
            amount_wei,
            wallet_address,  # Withdraw to our wallet
        ).build_transaction({
            "from": wallet_address,
            "nonce": self.w3.eth.get_transaction_count(wallet_address),
        })

        if self.dry_run_mode:
            logger.info(f"[DRY RUN] Would withdraw {amount} {token} from Aave V3")
            return {
                "success": True,
                "tx_hash": f"0xdryrun_withdraw_aave_{token}",
                "gas_used": 150000,
                "dry_run": True,
            }

        # Execute transaction
        tx_hash = await self.wallet.send_transaction(
            to=self.aave_pool_address,
            data=tx_data["data"],
            value=Decimal("0"),
        )

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        result = {
            "success": receipt["status"] == 1,
            "tx_hash": tx_hash,
            "gas_used": receipt["gasUsed"],
            "block_number": receipt["blockNumber"],
            "protocol": "Aave V3",
            "action": "withdraw",
        }

        await self.audit_logger.log_event(
            AuditEventType.TRANSACTION_SUBMITTED,
            AuditSeverity.INFO,
            f"Withdrew {amount} {token} from Aave V3",
            metadata={
                "protocol": "Aave V3",
                "token": token,
                "amount": str(amount),
                "tx_hash": tx_hash,
            },
        )

        logger.info(f"✅ Withdrawal successful: {tx_hash}")
        return result

    async def _deposit_aave_v3(self, token: str, amount: Decimal) -> Dict[str, Any]:
        """Execute Aave V3 deposit (supply).

        Args:
            token: Token symbol to deposit
            amount: Amount to deposit

        Returns:
            Transaction receipt
        """
        if not self.aave_pool:
            raise ValueError(f"Aave V3 Pool not configured for {self.network}")

        token_address = self._get_token_address(token)
        wallet_address = await self.wallet.get_address()

        logger.info(f"Depositing {amount} {token} to Aave V3...")

        # Extended ERC20 ABI with allowance
        extended_erc20_abi = ERC20_ABI + [{
            "inputs": [
                {"internalType": "address", "name": "owner", "type": "address"},
                {"internalType": "address", "name": "spender", "type": "address"},
            ],
            "name": "allowance",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        }]

        # Get token decimals
        token_contract = self.w3.eth.contract(address=token_address, abi=extended_erc20_abi)
        decimals = token_contract.functions.decimals().call()
        amount_wei = int(amount * Decimal(10**decimals))

        # Check current allowance
        current_allowance = token_contract.functions.allowance(
            wallet_address, self.aave_pool_address
        ).call()

        logger.info(f"Current allowance: {current_allowance}, needed: {amount_wei}")

        if current_allowance < amount_wei:
            # Approve max uint256 to avoid repeated approvals
            logger.info(f"Approving Aave V3 Pool to spend {token} (max approval)...")

            # Build approval transaction directly with max uint256
            max_uint256 = 2**256 - 1
            approve_tx_data = token_contract.functions.approve(
                self.aave_pool_address, max_uint256
            ).build_transaction({
                "from": wallet_address,
                "nonce": self.w3.eth.get_transaction_count(wallet_address),
            })

            if not self.dry_run_mode:
                # Execute approval
                approve_tx_hash = await self.wallet.send_transaction(
                    to=token_address,
                    data=approve_tx_data["data"],
                    value=Decimal("0"),
                )
                approve_receipt = self.w3.eth.wait_for_transaction_receipt(approve_tx_hash)

                if approve_receipt["status"] != 1:
                    return {
                        "success": False,
                        "error": "Approval transaction failed",
                        "tx_hash": approve_tx_hash,
                    }
                logger.info(f"✅ Approval complete: {approve_tx_hash}")
            else:
                logger.info(f"[DRY RUN] Would approve {token} for Aave V3 Pool")

        # Build supply transaction - get fresh nonce after approval
        # supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode)
        tx_data = self.aave_pool.functions.supply(
            token_address,
            amount_wei,
            wallet_address,  # Deposit on behalf of our wallet
            0,  # No referral code
        ).build_transaction({
            "from": wallet_address,
            "nonce": self.w3.eth.get_transaction_count(wallet_address),
        })

        if self.dry_run_mode:
            logger.info(f"[DRY RUN] Would deposit {amount} {token} to Aave V3")
            return {
                "success": True,
                "tx_hash": f"0xdryrun_deposit_aave_{token}",
                "gas_used": 120000,
                "dry_run": True,
            }

        # Execute transaction
        tx_hash = await self.wallet.send_transaction(
            to=self.aave_pool_address,
            data=tx_data["data"],
            value=Decimal("0"),
        )

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        result = {
            "success": receipt["status"] == 1,
            "tx_hash": tx_hash,
            "gas_used": receipt["gasUsed"],
            "block_number": receipt["blockNumber"],
            "protocol": "Aave V3",
            "action": "deposit",
        }

        await self.audit_logger.log_event(
            AuditEventType.TRANSACTION_SUBMITTED,
            AuditSeverity.INFO,
            f"Deposited {amount} {token} to Aave V3",
            metadata={
                "protocol": "Aave V3",
                "token": token,
                "amount": str(amount),
                "tx_hash": tx_hash,
            },
        )

        logger.info(f"✅ Deposit successful: {tx_hash}")
        return result

    async def get_token_balance(self, token: str, address: Optional[str] = None) -> Decimal:
        """Get token balance for an address.

        Args:
            token: Token symbol
            address: Address to check (defaults to wallet address)

        Returns:
            Token balance as Decimal
        """
        if address is None:
            address = await self.wallet.get_address()

        token_address = self._get_token_address(token)
        token_contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)

        balance_wei = token_contract.functions.balanceOf(address).call()
        decimals = token_contract.functions.decimals().call()

        balance = Decimal(balance_wei) / Decimal(10**decimals)
        return balance

    # ================================================================
    # MOONWELL PROTOCOL METHODS
    # ================================================================

    async def _deposit_moonwell(self, token: str, amount: Decimal) -> Dict[str, Any]:
        """Execute Moonwell deposit (Compound V2 style).

        Args:
            token: Token symbol to deposit
            amount: Amount to deposit

        Returns:
            Transaction receipt
        """
        logger.info(f"Depositing {amount} {token} to Moonwell...")

        # Get mToken address
        mtoken_addresses = MOONWELL_MTOKEN_ADDRESSES.get(self.network, {})
        mtoken_address = mtoken_addresses.get(token)

        if not mtoken_address:
            raise ValueError(f"Moonwell mToken not configured for {token} on {self.network}")

        token_address = self._get_token_address(token)
        wallet_address = await self.wallet.get_address()

        # Get token decimals and convert amount
        # Extended ERC20 ABI with allowance
        extended_erc20_abi = ERC20_ABI + [{
            "inputs": [
                {"internalType": "address", "name": "owner", "type": "address"},
                {"internalType": "address", "name": "spender", "type": "address"},
            ],
            "name": "allowance",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        }]

        token_contract = self.w3.eth.contract(address=token_address, abi=extended_erc20_abi)
        decimals = token_contract.functions.decimals().call()
        amount_wei = int(amount * Decimal(10**decimals))

        # Check current allowance
        current_allowance = token_contract.functions.allowance(
            wallet_address, mtoken_address
        ).call()

        logger.info(f"Current allowance: {current_allowance}, needed: {amount_wei}")

        if current_allowance < amount_wei:
            # Approve max uint256 to avoid repeated approvals
            logger.info(f"Approving Moonwell mToken to spend {token} (max approval)...")

            # Build approval transaction directly with max uint256
            max_uint256 = 2**256 - 1
            approve_tx_data = token_contract.functions.approve(
                mtoken_address, max_uint256
            ).build_transaction({
                "from": wallet_address,
                "nonce": self.w3.eth.get_transaction_count(wallet_address),
            })

            if not self.dry_run_mode:
                # Execute approval
                approve_tx_hash = await self.wallet.send_transaction(
                    to=token_address,
                    data=approve_tx_data["data"],
                    value=Decimal("0"),
                )
                approve_receipt = self.w3.eth.wait_for_transaction_receipt(approve_tx_hash)

                if approve_receipt["status"] != 1:
                    return {
                        "success": False,
                        "error": "Approval transaction failed",
                        "tx_hash": approve_tx_hash,
                    }
                logger.info(f"✅ Approval complete: {approve_tx_hash}")
            else:
                logger.info(f"[DRY RUN] Would approve {token} for Moonwell mToken")

        # Create mToken contract instance
        mtoken_contract = self.w3.eth.contract(address=mtoken_address, abi=MOONWELL_MTOKEN_ABI)

        if self.dry_run_mode:
            logger.info(f"[DRY RUN] Would deposit {amount} {token} to Moonwell")
            return {
                "success": True,
                "tx_hash": f"0xdryrun_deposit_moonwell_{token}",
                "gas_used": 200000,
                "dry_run": True,
            }

        # Build mint transaction (Compound V2 style)
        tx_data = mtoken_contract.functions.mint(amount_wei).build_transaction({
            "from": wallet_address,
            "nonce": self.w3.eth.get_transaction_count(wallet_address),
        })

        # Execute transaction
        tx_hash = await self.wallet.send_transaction(
            to=mtoken_address,
            data=tx_data["data"],
            value=Decimal("0"),
        )

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        result = {
            "success": receipt["status"] == 1,
            "tx_hash": tx_hash,
            "gas_used": receipt["gasUsed"],
            "block_number": receipt["blockNumber"],
            "protocol": "Moonwell",
            "action": "deposit",
        }

        await self.audit_logger.log_event(
            AuditEventType.TRANSACTION_SUBMITTED,
            AuditSeverity.INFO,
            f"Deposited {amount} {token} to Moonwell",
            metadata={
                "protocol": "Moonwell",
                "token": token,
                "amount": str(amount),
                "tx_hash": tx_hash,
            },
        )

        logger.info(f"✅ Deposited {amount} {token} to Moonwell: {tx_hash}")
        return result

    async def _withdraw_moonwell(self, token: str, amount: Decimal) -> Dict[str, Any]:
        """Execute Moonwell withdrawal (Compound V2 style).

        Args:
            token: Token symbol to withdraw
            amount: Amount to withdraw

        Returns:
            Transaction receipt
        """
        logger.info(f"Withdrawing {amount} {token} from Moonwell...")

        # Get mToken address
        mtoken_addresses = MOONWELL_MTOKEN_ADDRESSES.get(self.network, {})
        mtoken_address = mtoken_addresses.get(token)

        if not mtoken_address:
            raise ValueError(f"Moonwell mToken not configured for {token} on {self.network}")

        token_address = self._get_token_address(token)
        wallet_address = await self.wallet.get_address()

        # Get token decimals and convert amount
        token_contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
        decimals = token_contract.functions.decimals().call()
        amount_wei = int(amount * Decimal(10**decimals))

        # Create mToken contract instance
        mtoken_contract = self.w3.eth.contract(address=mtoken_address, abi=MOONWELL_MTOKEN_ABI)

        if self.dry_run_mode:
            logger.info(f"[DRY RUN] Would withdraw {amount} {token} from Moonwell")
            return {
                "success": True,
                "tx_hash": f"0xdryrun_withdraw_moonwell_{token}",
                "gas_used": 150000,
                "dry_run": True,
            }

        # Build redeemUnderlying transaction (withdraw by underlying amount)
        tx_data = mtoken_contract.functions.redeemUnderlying(amount_wei).build_transaction({
            "from": wallet_address,
            "nonce": self.w3.eth.get_transaction_count(wallet_address),
        })

        # Execute transaction
        tx_hash = await self.wallet.send_transaction(
            to=mtoken_address,
            data=tx_data["data"],
            value=Decimal("0"),
        )

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        result = {
            "success": receipt["status"] == 1,
            "tx_hash": tx_hash,
            "gas_used": receipt["gasUsed"],
            "block_number": receipt["blockNumber"],
            "protocol": "Moonwell",
            "action": "withdraw",
        }

        await self.audit_logger.log_event(
            AuditEventType.TRANSACTION_SUBMITTED,
            AuditSeverity.INFO,
            f"Withdrew {amount} {token} from Moonwell",
            metadata={
                "protocol": "Moonwell",
                "token": token,
                "amount": str(amount),
                "tx_hash": tx_hash,
            },
        )

        logger.info(f"✅ Withdrew {amount} {token} from Moonwell: {tx_hash}")
        return result

    # ================================================================
    # MORPHO BLUE PROTOCOL METHODS
    # ================================================================

    async def _deposit_morpho(self, token: str, amount: Decimal) -> Dict[str, Any]:
        """Execute Morpho Blue deposit.

        Args:
            token: Token symbol to deposit
            amount: Amount to deposit

        Returns:
            Transaction receipt

        Note:
            Morpho Blue requires market parameters. This is a simplified implementation
            that would need to be extended with proper market selection logic.
        """
        logger.warning(
            f"Morpho deposit for {token}: Simplified implementation. "
            "Production version needs proper market parameter selection."
        )

        if self.dry_run_mode:
            logger.info(f"[DRY RUN] Would deposit {amount} {token} to Morpho")
            return {
                "success": True,
                "tx_hash": f"0xdryrun_deposit_morpho_{token}",
                "gas_used": 250000,
                "dry_run": True,
            }

        # In production, we would:
        # 1. Query available Morpho markets for this token
        # 2. Select the best market based on APY/risk
        # 3. Build market parameters struct
        # 4. Execute supply transaction

        raise NotImplementedError(
            "Morpho deposit requires market parameter selection. "
            "This will be implemented in a future sprint with proper market discovery."
        )

    async def _withdraw_morpho(self, token: str, amount: Decimal) -> Dict[str, Any]:
        """Execute Morpho Blue withdrawal.

        Args:
            token: Token symbol to withdraw
            amount: Amount to withdraw

        Returns:
            Transaction receipt

        Note:
            Morpho Blue requires market parameters. This is a simplified implementation
            that would need to be extended with proper market selection logic.
        """
        logger.warning(
            f"Morpho withdraw for {token}: Simplified implementation. "
            "Production version needs proper market parameter selection."
        )

        if self.dry_run_mode:
            logger.info(f"[DRY RUN] Would withdraw {amount} {token} from Morpho")
            return {
                "success": True,
                "tx_hash": f"0xdryrun_withdraw_morpho_{token}",
                "gas_used": 200000,
                "dry_run": True,
            }

        # In production, we would:
        # 1. Query user's Morpho positions
        # 2. Get market parameters for the position
        # 3. Build withdraw transaction with market params
        # 4. Execute withdraw

        raise NotImplementedError(
            "Morpho withdrawal requires market parameter selection. "
            "This will be implemented in a future sprint with proper position tracking."
        )

    # ================================================================
    # UNISWAP V3 SWAP METHODS
    # ================================================================

    async def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        slippage_percent: Decimal = Decimal("0.5"),
        fee_tier: int = 3000,
    ) -> Dict[str, Any]:
        """Execute token swap via Uniswap V3.

        Args:
            token_in: Input token symbol (e.g., "USDC")
            token_out: Output token symbol (e.g., "WETH")
            amount_in: Amount of input token
            slippage_percent: Maximum slippage tolerance (default 0.5%)
            fee_tier: Uniswap pool fee tier (500, 3000, or 10000)

        Returns:
            Transaction receipt with swap details
        """
        from src.protocols.uniswap_v3_router import UniswapV3Router
        from src.protocols.uniswap_v3_quoter import UniswapV3Quoter

        logger.info(f"Swapping {amount_in} {token_in} → {token_out}...")

        wallet_address = await self.wallet.get_address()

        # Get token addresses and decimals
        token_in_address = self._get_token_address(token_in)
        token_out_address = self._get_token_address(token_out)

        token_in_contract = self.w3.eth.contract(address=token_in_address, abi=ERC20_ABI)
        token_out_contract = self.w3.eth.contract(address=token_out_address, abi=ERC20_ABI)

        token_in_decimals = token_in_contract.functions.decimals().call()
        token_out_decimals = token_out_contract.functions.decimals().call()

        amount_in_wei = int(amount_in * Decimal(10**token_in_decimals))

        # Get quote for expected output
        quoter = UniswapV3Quoter(self.w3, self.network)
        quote_result = await quoter.quote_exact_input(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            fee_tier=fee_tier,
        )

        if not quote_result:
            return {
                "success": False,
                "error": f"Could not get quote for {token_in} → {token_out}",
            }

        expected_out = quote_result.amount_out  # raw units
        expected_out_formatted = quote_result.amount_out_formatted

        # Calculate minimum output with slippage
        slippage_multiplier = (Decimal("100") - slippage_percent) / Decimal("100")
        amount_out_min = int(Decimal(str(expected_out)) * slippage_multiplier)
        amount_out_min_formatted = Decimal(str(amount_out_min)) / Decimal(10**token_out_decimals)

        logger.info(
            f"Quote: {amount_in} {token_in} → {expected_out_formatted} {token_out} "
            f"(min: {amount_out_min_formatted})"
        )

        # Check and approve swap router
        from src.utils.constants import UNISWAP_V3_ADDRESSES
        router_address = UNISWAP_V3_ADDRESSES[self.network]["swap_router_02"]

        # Extended ERC20 ABI with allowance
        extended_erc20_abi = ERC20_ABI + [{
            "inputs": [
                {"internalType": "address", "name": "owner", "type": "address"},
                {"internalType": "address", "name": "spender", "type": "address"},
            ],
            "name": "allowance",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        }]

        token_with_allowance = self.w3.eth.contract(
            address=token_in_address,
            abi=extended_erc20_abi
        )

        current_allowance = token_with_allowance.functions.allowance(
            wallet_address, router_address
        ).call()

        if current_allowance < amount_in_wei:
            logger.info(f"Approving Uniswap V3 Router to spend {token_in}...")

            max_uint256 = 2**256 - 1
            approve_tx_data = token_in_contract.functions.approve(
                router_address, max_uint256
            ).build_transaction({
                "from": wallet_address,
                "nonce": self.w3.eth.get_transaction_count(wallet_address),
            })

            if not self.dry_run_mode:
                approve_tx_hash = await self.wallet.send_transaction(
                    to=token_in_address,
                    data=approve_tx_data["data"],
                    value=Decimal("0"),
                )
                approve_receipt = self.w3.eth.wait_for_transaction_receipt(approve_tx_hash)

                if approve_receipt["status"] != 1:
                    return {
                        "success": False,
                        "error": "Approval transaction failed",
                        "tx_hash": approve_tx_hash,
                    }
                logger.info(f"✅ Approval complete: {approve_tx_hash}")

        if self.dry_run_mode:
            logger.info(f"[DRY RUN] Would swap {amount_in} {token_in} → {expected_out_formatted} {token_out}")
            return {
                "success": True,
                "tx_hash": f"0xdryrun_swap_{token_in}_{token_out}",
                "gas_used": 150000,
                "dry_run": True,
                "amount_in": str(amount_in),
                "expected_out": str(expected_out_formatted),
                "token_in": token_in,
                "token_out": token_out,
            }

        # Build and execute swap
        router = UniswapV3Router(self.w3, self.network)
        swap_tx = router.build_exact_input_single_swap(
            token_in=token_in_address,
            token_out=token_out_address,
            amount_in=amount_in_wei,
            amount_out_minimum=amount_out_min,
            recipient=wallet_address,
            fee_tier=fee_tier,
        )

        # Update nonce
        swap_tx["nonce"] = self.w3.eth.get_transaction_count(wallet_address)

        # Execute swap
        tx_hash = await self.wallet.send_transaction(
            to=router_address,
            data=swap_tx["data"],
            value=Decimal("0"),
        )

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        # Get actual output amount from logs (simplified - just report success)
        result = {
            "success": receipt["status"] == 1,
            "tx_hash": tx_hash,
            "gas_used": receipt["gasUsed"],
            "block_number": receipt["blockNumber"],
            "amount_in": str(amount_in),
            "token_in": token_in,
            "token_out": token_out,
            "expected_out": str(expected_out_formatted),
        }

        await self.audit_logger.log_event(
            AuditEventType.TRANSACTION_SUBMITTED,
            AuditSeverity.INFO,
            f"Swapped {amount_in} {token_in} → {token_out}",
            metadata={
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": str(amount_in),
                "expected_out": str(expected_out_formatted),
                "tx_hash": tx_hash,
            },
        )

        logger.info(f"✅ Swap successful: {tx_hash}")
        return result
