"""StyleAI MCP server (mcp 2.x).

Development backend: MockStore.

The server exposes exactly five shopping tools:

- search_products
- get_product
- get_variants
- check_availability
- get_alternatives

The check_availability implementation lives in
mcp_server/tools/check_availability.py so that the response shape is
consistent with the rest of the MCP tool layer.
"""

from __future__ import annotations

import inspect
import os
from typing import Any

from mcp.server.mcpserver import MCPServer

from backend.shopping.stores.mock_store import MockStore

from mcp_server.tools import get_product as get_product_tool
from mcp_server.tools import search_products as search_products_tool
from mcp_server.tools import check_availability as check_availability_tool


mcp = MCPServer(
    "styleai",
    instructions="Fashion product search tools for the StyleAI Shopping Agent.",
)


# ---------------------------------------------------------------------------
# Tools implemented in mcp_server/tools/
# ---------------------------------------------------------------------------

search_products_tool.register(mcp)
get_product_tool.register(mcp)
check_availability_tool.register(mcp)


# ---------------------------------------------------------------------------
# Development store
# ---------------------------------------------------------------------------

_store = MockStore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _call(
    method: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Call a MockStore method and convert Product objects to plain data."""
    result = getattr(_store, method)(*args, **kwargs)

    if inspect.isawaitable(result):
        result = await result

    return _to_plain(result)


def _to_plain(obj: Any) -> Any:
    """Convert Product/model objects recursively to plain Python data."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()

    if isinstance(obj, (list, tuple)):
        return [_to_plain(item) for item in obj]

    if isinstance(obj, dict):
        return {key: _to_plain(value) for key, value in obj.items()}

    return obj


# ---------------------------------------------------------------------------
# get_variants
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_variants(product_id: str) -> list[dict]:
    """Get size/color variants of a product."""
    return await _call("get_variants", product_id)


# ---------------------------------------------------------------------------
# check_availability
#
# IMPORTANT:
# This tool is registered from mcp_server/tools/check_availability.py above.
#
# Do NOT define another @mcp.tool() with the same name here.
#
# The registered tool returns:
# {
#     "product_id": "...",
#     "available": True/False
# }
#
# and correctly forwards the optional size argument.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# get_alternatives
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_alternatives(
    product_id: str,
    limit: int = 5,
) -> list[dict]:
    """Get similar alternative products."""
    return await _call(
        "get_alternatives",
        product_id,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(os.getenv("PORT", "8001")),
        )
    else:
        mcp.run(
            transport="stdio",
        )