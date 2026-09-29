"""
get_product MCP tool.

    MCP Server
         v
    get_product()                 <-- this file
         v
    MockStore.get_product()       (development source; SerpApi/Google
                                   Shopping will replace this later,
                                   without changing this tool's name
                                   or return shape)
         v
    Product -> serialized dict (Product.model_dump()), or None
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.shopping.stores.mock_store import MockStore

_store = MockStore()


def get_product_impl(product_id: str) -> Optional[Dict[str, Any]]:
    """
    Look up a single product by id.

    Returns:
        The common Product serialized with Product.model_dump(), or None
        if no product with that id exists.
    """
    product = _store.get_product(product_id)
    if product is None:
        return None
    return product.model_dump()


def register(mcp) -> None:
    """Register the get_product tool on the given MCPServer."""

    @mcp.tool()
    def get_product(product_id: str) -> Optional[Dict[str, Any]]:
        """
        Get one product by its identifier.

        Args:
            product_id: The product identifier (the product_id field of a
                product returned by search_products).

        Returns:
            The complete common Product object with: product_id, store,
            brand, title, category, color, price, currency, sizes,
            image_url, product_url, availability. Returns null if the
            product does not exist.

            image_url is the product image the frontend displays. It is
            null when the source has no image for that product; it is
            never fabricated. product_url is the original retailer/product
            page URL, used by the frontend's View/Buy action.
        """
        return get_product_impl(product_id)