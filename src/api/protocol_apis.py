"""External API clients for DeFi protocols.

This module provides HTTP clients for fetching data from
protocol APIs and subgraphs.
"""

from typing import Any, Dict, List, Optional
import aiohttp
from decimal import Decimal


class ProtocolAPIClient:
    """Base class for protocol API clients.

    Provides common HTTP functionality for API requests.

    Attributes:
        base_url: API base URL
        session: aiohttp session
    """

    def __init__(self, base_url: str) -> None:
        """Initialize API client.

        Args:
            base_url: API base URL
        """
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> None:
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()

    async def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make GET request.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            Response JSON
        """
        await self._ensure_session()
        assert self.session is not None

        url = f"{self.base_url}/{endpoint}"
        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json()

    async def _post(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make POST request.

        Args:
            endpoint: API endpoint
            data: Form data
            json: JSON data

        Returns:
            Response JSON
        """
        await self._ensure_session()
        assert self.session is not None

        url = f"{self.base_url}/{endpoint}"
        async with self.session.post(url, data=data, json=json) as response:
            response.raise_for_status()
            return await response.json()

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()


class DefiLlamaClient(ProtocolAPIClient):
    """Client for DefiLlama API (TVL and yield data).

    DefiLlama provides aggregated DeFi protocol data.
    """

    def __init__(self) -> None:
        """Initialize DefiLlama client."""
        super().__init__("https://api.llama.fi")

    async def get_protocol_tvl(self, protocol: str) -> Decimal:
        """Get total value locked for a protocol.

        Args:
            protocol: Protocol slug

        Returns:
            TVL in USD
        """
        raise NotImplementedError("TVL fetching not yet implemented")

    async def get_yields(self, chain: str = "Base") -> List[Dict[str, Any]]:
        """Get yield data for a specific chain.

        Args:
            chain: Blockchain name

        Returns:
            List of yield opportunities
        """
        raise NotImplementedError("Yield fetching not yet implemented")


class TheGraphClient:
    """Client for The Graph subgraphs.

    Used for querying protocol-specific subgraphs.
    """

    def __init__(self, subgraph_url: str) -> None:
        """Initialize The Graph client.

        Args:
            subgraph_url: Subgraph query URL
        """
        self.subgraph_url = subgraph_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def query(self, graphql_query: str) -> Dict[str, Any]:
        """Execute a GraphQL query.

        Args:
            graphql_query: GraphQL query string

        Returns:
            Query results
        """
        raise NotImplementedError("Graph query not yet implemented")

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
