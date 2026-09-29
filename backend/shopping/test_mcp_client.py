"""
Tests for backend/shopping/mcp_client.py.

These start the REAL mcp_server.server as a STDIO subprocess (MockStore
behind it) and talk to it through MCPShoppingClient. asyncio.run is used
(like the existing MCP tests) so no async pytest plugin is required.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.shopping.mcp_client import (
    EXPECTED_TOOLS,
    MCPClientError,
    MCPConnectionError,
    MCPShoppingClient,
    MCPToolError,
)

COMMON_PRODUCT_FIELDS = {
    "product_id", "store", "brand", "title", "category", "color",
    "price", "currency", "sizes", "image_url", "product_url", "availability",
}


def _with_client(coro_fn):
    """Run `coro_fn(client)` against a freshly started MCP server."""

    async def runner():
        async with MCPShoppingClient() as client:
            return await coro_fn(client)

    return asyncio.run(runner())


# A. connect ---------------------------------------------------------------

def test_client_connects_to_mcp_server():
    async def check(client):
        return client.is_connected

    assert _with_client(check) is True


def test_client_is_disconnected_after_context_exit():
    async def runner():
        client = MCPShoppingClient()
        async with client:
            assert client.is_connected
        return client.is_connected

    assert asyncio.run(runner()) is False


def test_calling_before_connect_raises_clear_error():
    with pytest.raises(MCPClientError):
        asyncio.run(MCPShoppingClient().get_product("MOCK001"))


def test_bad_server_command_raises_connection_error_not_fake_data():
    async def runner():
        await MCPShoppingClient(args=["-m", "no_such_module_xyz"]).connect()

    with pytest.raises(MCPConnectionError):
        asyncio.run(runner())


# B. discover the five tools -------------------------------------------------

def test_client_lists_the_five_tools():
    names = _with_client(lambda c: c.list_tools())
    assert EXPECTED_TOOLS.issubset(set(names))


# C. search_products ---------------------------------------------------------

def test_search_products_can_be_called():
    results = _with_client(lambda c: c.search_products(query="", category="dresses"))
    assert isinstance(results, list) and len(results) > 0
    assert all(isinstance(p, dict) for p in results)
    assert all(p["category"] == "dresses" for p in results)


def test_search_products_respects_budget():
    results = _with_client(lambda c: c.search_products(query="", budget=5000))
    assert len(results) > 0
    assert all(p["price"] <= 5000 for p in results)


# D. get_product -------------------------------------------------------------

def test_get_product_can_be_called():
    product = _with_client(lambda c: c.get_product("MOCK001"))
    assert product is not None
    assert COMMON_PRODUCT_FIELDS.issubset(product.keys())
    assert product["product_id"] == "MOCK001"


def test_get_product_unknown_id_returns_none():
    assert _with_client(lambda c: c.get_product("DOES_NOT_EXIST")) is None


def test_missing_image_url_stays_null_through_the_client():
    product = _with_client(lambda c: c.get_product("MOCK003"))
    assert product is not None
    assert product["image_url"] is None
    assert product["product_url"]


# E. get_variants ------------------------------------------------------------

def test_get_variants_can_be_called():
    results = _with_client(lambda c: c.get_variants("MOCK022"))
    assert isinstance(results, list)
    assert all(isinstance(v, dict) for v in results)
    assert all(v["product_id"] != "MOCK022" for v in results)


# F / G. check_availability --------------------------------------------------

def test_check_availability_with_size_can_be_called():
    async def check(client):
        product = await client.get_product("MOCK001")
        result = await client.check_availability("MOCK001", size="S")
        return product, result

    product, result = _with_client(check)
    assert result["product_id"] == "MOCK001"
    assert isinstance(result["available"], bool)
    # The answer must agree with the catalog: S is available only if it is a listed size.
    if "S" not in product["sizes"]:
        assert result["available"] is False


def test_check_availability_without_size_can_be_called():
    result = _with_client(lambda c: c.check_availability("MOCK001"))
    assert result == {"product_id": "MOCK001", "available": True}


def test_check_availability_with_unavailable_size_is_false():
    result = _with_client(
        lambda c: c.check_availability("MOCK001", size="NOT_A_REAL_SIZE")
    )
    assert result["product_id"] == "MOCK001"
    assert result["available"] is False


# H. get_alternatives --------------------------------------------------------

def test_get_alternatives_can_be_called():
    results = _with_client(lambda c: c.get_alternatives("MOCK022", limit=3))
    assert 0 < len(results) <= 3
    assert all(isinstance(p, dict) for p in results)
    assert all(p["product_id"] != "MOCK022" for p in results)


# errors are surfaced, not swallowed -------------------------------------------

def test_unknown_tool_raises_tool_error():
    with pytest.raises(MCPToolError):
        _with_client(lambda c: c.call_tool("not_a_real_tool", {}))