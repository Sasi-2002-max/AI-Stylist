"""
search_products MCP tool.

    MCP Server
         v
    search_products()             <-- this file
         v
    MockStore.search_products()   (development source; SerpApi/Google
                                   Shopping will replace this later,
                                   without changing this tool's name
                                   or return shape)
         v
    Product objects -> serialized dicts
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.shopping.stores.mock_store import DEFAULT_LIMIT, MockStore

_store = MockStore()


def search_products_impl(
    query: str = "",
    category: Optional[str] = None,
    color: Optional[str] = None,
    max_price: Optional[float] = None,
    limit: int = DEFAULT_LIMIT,
    budget: Optional[float] = None,  # backward-compatible alias for max_price
) -> List[Dict[str, Any]]:
    """
    Search for products matching the given filters.

    Filtering is deterministic and done by the store (no LLM).

    Returns:
        A list of serialized Product dicts (via Product.model_dump()).
        Never a custom/second schema. May be empty.
    """
    if max_price is None:
        max_price = budget

    products = _store.search_products(
        query=query or "",
        budget=max_price,  # MockStore's name for the inclusive max price
        category=category,
        color=color,
        limit=limit,
    )
    return [product.model_dump() for product in products]


def register(mcp) -> None:
    """Register the search_products tool on the given MCPServer."""

    @mcp.tool()
    def search_products(
        query: str = "",
        category: Optional[str] = None,
        color: Optional[str] = None,
        max_price: Optional[float] = None,
        limit: int = DEFAULT_LIMIT,
    ) -> List[Dict[str, Any]]:
        """
        Search the shopping product source for fashion products.

        Args:
            query: Free-text search terms, e.g. "black shirt".
            category: Optional exact category filter, e.g. "shirt".
            color: Optional exact color filter, e.g. "black".
            max_price: Optional maximum price (inclusive).
            limit: Maximum number of products to return.

        Returns:
            A list of product objects, each with: product_id, store, brand,
            title, category, color, price, currency, sizes, image_url,
            product_url, availability. image_url is null when the source
            has no image for that product; it is never fabricated.
        """
        return search_products_impl(
            query=query, category=category, color=color, max_price=max_price, limit=limit
        )