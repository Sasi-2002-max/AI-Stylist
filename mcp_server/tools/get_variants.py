"""
get_variants MCP tool.

    MCP Server
         v
    get_variants()          <-- this file
         v
    MockStore.get_variants()
         v
    list[Product] -> serialized dicts
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.shopping.stores.mock_store import MockStore

_store = MockStore()


def get_variants_impl(product_id: str) -> List[Dict[str, Any]]:
    """
    Return other products that are variants of the given product.

    Returns:
        A list of serialized Product dicts. Empty if the product has no
        known variants or does not exist.
    """
    variants = _store.get_variants(product_id)
    return [variant.model_dump() for variant in variants]


def register(mcp) -> None:
    """Register the get_variants tool on the given FastMCP server."""

    @mcp.tool()
    def get_variants(product_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve variant products for a given product (e.g. same item,
        different color/size, where the source models that relationship).

        Args:
            product_id: The reference product's identifier.

        Returns:
            A list of product objects in the common Product shape. Empty
            list if there are no variants or the product is unknown.
        """
        return get_variants_impl(product_id)