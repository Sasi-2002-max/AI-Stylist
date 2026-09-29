import asyncio
import json

import pytest
from mcp.server.mcpserver import MCPServer

from backend.shopping.product_normalizer import Product
from backend.shopping.stores.mock_store import MockStore
from mcp_server.tools import get_product as tool

CATALOG = [
    {"product_id": "S1", "store": "Amazon", "brand": "Acme", "title": "Black Formal Shirt",
     "category": "shirt", "color": "black", "price": 1299, "currency": "INR",
     "sizes": ["S", "M", "L"], "image_url": "https://img.example/s1.jpg",
     "product_url": "https://shop.example/s1", "availability": True},
    {"product_id": "S2", "store": "Myntra", "brand": "Acme", "title": "Black Premium Shirt",
     "category": "shirt", "color": "black", "price": 2499, "currency": "INR",
     "sizes": ["M", "L"], "product_url": "https://shop.example/s2", "availability": True},
]

PRODUCT_FIELDS = {
    "product_id", "store", "brand", "title", "category", "color", "price",
    "currency", "sizes", "image_url", "product_url", "availability",
}


@pytest.fixture
def patched(tmp_path, monkeypatch):
    path = tmp_path / "products.json"
    path.write_text(json.dumps(CATALOG), encoding="utf-8")
    store = MockStore(products_path=path)
    monkeypatch.setattr(tool, "_store", store)
    return store


# ---- get_product_impl ----

def test_existing_product_returns_product_shaped_dict(patched):
    result = tool.get_product_impl("S1")
    assert type(result) is dict
    assert set(result) == PRODUCT_FIELDS
    # the dict is exactly what the common Product model serializes to
    assert result == Product(**result).model_dump()


def test_fields_are_preserved(patched):
    result = tool.get_product_impl("S1")
    assert result["product_id"] == "S1"
    assert result["store"] == "Amazon"
    assert result["title"] == "Black Formal Shirt"
    assert result["price"] == 1299
    assert result["image_url"] == "https://img.example/s1.jpg"
    assert result["product_url"] == "https://shop.example/s1"


def test_missing_image_stays_null(patched):
    result = tool.get_product_impl("S2")
    assert "image_url" in result and result["image_url"] is None
    assert result["product_url"] == "https://shop.example/s2"


def test_unknown_product_returns_none(patched):
    assert tool.get_product_impl("DOES_NOT_EXIST") is None


# ---- through the real MCP layer ----

def _call_via_mcp(product_id):
    mcp = MCPServer("test")
    tool.register(mcp)
    result = asyncio.run(mcp.call_tool("get_product", {"product_id": product_id}))
    assert not result.is_error
    return result.structured_content["result"]


def test_mcp_tool_round_trip(patched):
    item = _call_via_mcp("S1")
    assert item["product_id"] == "S1"
    assert item["image_url"] == "https://img.example/s1.jpg"
    assert item["product_url"] == "https://shop.example/s1"


def test_mcp_tool_unknown_id_returns_none(patched):
    assert _call_via_mcp("DOES_NOT_EXIST") is None