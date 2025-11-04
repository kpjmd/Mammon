"""Streamlit dashboard for MAMMON monitoring and control.

This dashboard provides a web interface for:
- Viewing current positions
- Monitoring yields
- Approving transactions
- Viewing performance metrics
"""

import streamlit as st
from decimal import Decimal
from typing import Dict, List


def main() -> None:
    """Main dashboard application."""
    st.set_page_config(
        page_title="MAMMON - DeFi Yield Optimizer",
        page_icon="💰",
        layout="wide",
    )

    st.title("💰 MAMMON - Autonomous DeFi Yield Optimizer")
    st.markdown("*Optimizing yields on Base network with AI*")

    # Sidebar navigation
    page = st.sidebar.selectbox(
        "Navigation",
        ["Overview", "Positions", "Opportunities", "Transactions", "Approvals", "Settings"],
    )

    if page == "Overview":
        show_overview()
    elif page == "Positions":
        show_positions()
    elif page == "Opportunities":
        show_opportunities()
    elif page == "Transactions":
        show_transactions()
    elif page == "Approvals":
        show_approvals()
    elif page == "Settings":
        show_settings()


def show_overview() -> None:
    """Show overview dashboard."""
    st.header("Portfolio Overview")

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Value", "$0.00", "0%")

    with col2:
        st.metric("Average APY", "0.00%", "0%")

    with col3:
        st.metric("Daily Yield", "$0.00", "$0.00")

    with col4:
        st.metric("Gas Spent (24h)", "$0.00")

    st.info("⚠️ MAMMON is not yet fully implemented. This is a placeholder dashboard.")


def show_positions() -> None:
    """Show current positions."""
    st.header("Current Positions")
    st.info("No positions yet. Start by configuring MAMMON and deploying capital.")


def show_opportunities() -> None:
    """Show yield opportunities."""
    st.header("Yield Opportunities")
    st.info("Protocol scanning not yet implemented.")


def show_transactions() -> None:
    """Show transaction history."""
    st.header("Transaction History")
    st.info("No transactions yet.")


def show_approvals() -> None:
    """Show pending approvals."""
    st.header("Pending Approvals")
    st.info("No pending approvals.")


def show_settings() -> None:
    """Show settings panel."""
    st.header("Settings")

    st.subheader("Security Limits")
    max_tx = st.number_input("Max Transaction Value (USD)", value=1000, min_value=0)
    daily_limit = st.number_input("Daily Spending Limit (USD)", value=5000, min_value=0)
    approval_threshold = st.number_input("Approval Threshold (USD)", value=100, min_value=0)

    st.subheader("Network")
    network = st.selectbox("Network", ["Base Sepolia (Testnet)", "Base Mainnet"])

    st.warning("⚠️ Settings are not yet persisted. Implementation pending.")

    if st.button("Save Settings"):
        st.success("Settings saved! (Not really - implementation pending)")


if __name__ == "__main__":
    main()
