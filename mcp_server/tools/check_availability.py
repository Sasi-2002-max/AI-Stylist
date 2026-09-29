"""
check_availability MCP tool.

    MCP Server
         v
    check_availability()          <-- this file
         v
    MockStore.check_availability()
         v
    {"product_id": ..., "available": bool}
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from backend.shopping.stores.mock_store import MockStore

_store = MockStore()


def check_availability_impl(
    product_id: str,
    size: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check whether a product is currently available.

    Args:
        product_id: The product identifier.
        size: Optional requested size.

    Returns:
        {
            "product_id": "...",
            "available": True/False
        }

    Availability is read from the store and never guessed.
    """
    available = _store.check_availability(
        product_id,
        size=size,
    )

    return {
        "product_id": product_id,
        "available": available,
    }


def register(mcp) -> None:
    """Register the check_availability tool on the MCP server."""

    @mcp.tool()
    def check_availability(
        product_id: str,
        size: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check whether a product is available, optionally for a
        specific size.
        """
        return check_availability_impl(
            product_id,
            size=size,
        )