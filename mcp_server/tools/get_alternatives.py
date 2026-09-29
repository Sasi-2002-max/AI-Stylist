"""
get_alternatives MCP tool.

    MCP Server
         v
    get_alternatives()          <-- this file
         v
    MockStore.get_alternatives()
         v
    list[Product] -> serialized dicts
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.shopping.stores.mock_store import MockStore

_store = MockStore()


def get_alternatives_impl(product_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Suggest alternative products to the given one.

    Returns:
        A list of serialized Product dicts. Empty if the product is
        unknown or has no alternatives. Never fabricated.
    """
    alternatives = _store.get_alternatives(product_id, limit=limit)
    return [alternative.model_dump() for alternative in alternatives]


def register(mcp) -> None:
    """Register the get_alternatives tool on the given FastMCP server."""

    @mcp.tool()
    def get_alternatives(product_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Suggest alternative products to a given product (e.g. for
        "explore alternatives" or a Critic Agent revision request).

        Args:
            product_id: The reference product's identifier.
            limit: Maximum number of alternatives to return.

        Returns:
            A list of product objects in the common Product shape.
        """
        return get_alternatives_impl(product_id, limit=limit)