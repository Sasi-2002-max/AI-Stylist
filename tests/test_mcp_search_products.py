import asyncio
import json

import pytest
from mcp.server.mcpserver import MCPServer

from backend.shopping.product_normalizer import Product
from backend.shopping.stores.mock_store import MockStore
from mcp_server.tools import search_products as tool

CATALOG = [
    {"product_id": "S1", "store": "Amazon", "brand": "Acme", "title": "Black Formal Shirt",
     "category": "shirt", "color": "black", "price": 1299, "currency": "INR",
     "sizes": ["S", "M", "L"], "image_url": "https://img.example/s1.jpg",
     "product_url": "https://shop.example/s1", "availability": True},
    {"product_id": "S2", "store": "Myntra", "brand": "Acme", "title": "Black Premium Shirt",
     "category": "shirt", "color": "black", "price": 2499, "currency": "INR",
     "sizes": ["M", "L"], "product_url": "https://shop.example/s2", "availability": True},
    {"product_id": "S3", "store": "H&M", "brand": "Basics", "title": "White Oxford Shirt",
     "category": "shirt", "color": "white", "price": 999, "currency": "INR",
     "sizes": ["S", "M"], "image_url": "https://img.example/s3.jpg",
     "product_url": "https://shop.example/s3", "availability": True},
    {"product_id": "P1", "store": "Zara", "brand": "Basics", "title": "Cream Chinos",
     "category": "pants", "color": "cream", "price": 1599, "currency": "INR",
     "sizes": ["30", "32"], "image_url": "https://img.example/p1.jpg",
     "product_url": "https://shop.example/p1", "availability": True},
    {"product_id": "SH1", "store": "Amazon", "brand": "Walker", "title": "Brown Leather Shoes",
     "category": "shoes", "color": "brown", "price": 1499, "currency": "INR",
     "sizes": ["8", "9"], "image_url": "https://img.example/sh1.jpg",
     "product_url": "https://shop.example/sh1", "availability": True},
]


@pytest.fixture
def store(tmp_path):
    path = tmp_path / "products.json"
    path.write_text(json.dumps(CATALOG), encoding="utf-8")
    return MockStore(products_path=path)


@pytest.fixture
def patched(store, monkeypatch):
    monkeypatch.setattr(tool, "_store", store)
    return store


def ids(items):
    return [i["product_id"] if isinstance(i, dict) else i.product_id for i in items]


# ---- MockStore returns common Product objects ----

def test_store_returns_product_objects(store):
    results = store.search_products()
    assert results and all(isinstance(p, Product) for p in results)


# ---- Filters via the tool implementation ----

def test_category_filter(patched):
    assert ids(tool.search_products_impl(category="shirt")) == ["S1", "S2", "S3"]


def test_color_filter(patched):
    assert ids(tool.search_products_impl(color="black")) == ["S1", "S2"]


def test_max_price_filter_is_inclusive(patched):
    assert ids(tool.search_products_impl(max_price=1500)) == ["S1", "S3", "SH1"]
    assert "SH1" in ids(tool.search_products_impl(max_price=1499))
    assert "SH1" not in ids(tool.search_products_impl(max_price=1498))


def test_budget_alias_still_works(patched):
    assert ids(tool.search_products_impl(budget=1500)) == ["S1", "S3", "SH1"]


def test_query_filter(patched):
    assert ids(tool.search_products_impl(query="leather")) == ["SH1"]
    assert ids(tool.search_products_impl(query="black shirt")) == ["S1", "S2"]
    assert tool.search_products_impl(query="nonexistent") == []


def test_combined_filters(patched):
    result = tool.search_products_impl(category="shirt", color="black", max_price=1500)
    assert ids(result) == ["S1"]


def test_limit_and_determinism(patched):
    first = tool.search_products_impl(category="shirt", limit=2)
    second = tool.search_products_impl(category="shirt", limit=2)
    assert ids(first) == ["S1", "S2"]
    assert first == second


# ---- Returned fields ----

def test_required_fields_present(patched):
    for item in tool.search_products_impl():
        assert type(item) is dict
        for key in ("product_id", "store", "title", "price"):
            assert item[key] not in (None, "")


def test_image_url_preserved_and_null_when_missing(patched):
    by_id = {i["product_id"]: i for i in tool.search_products_impl()}
    assert by_id["S1"]["image_url"] == "https://img.example/s1.jpg"
    assert "image_url" in by_id["S2"] and by_id["S2"]["image_url"] is None


def test_product_url_preserved(patched):
    by_id = {i["product_id"]: i for i in tool.search_products_impl()}
    assert by_id["S1"]["product_url"] == "https://shop.example/s1"
    assert by_id["SH1"]["product_url"] == "https://shop.example/sh1"


# ---- Through the real MCP layer ----

def _call_via_mcp(arguments):
    mcp = MCPServer("test")
    tool.register(mcp)
    result = asyncio.run(mcp.call_tool("search_products", arguments))
    assert not result.is_error
    return result.structured_content["result"]


def test_mcp_tool_round_trip(patched):
    items = _call_via_mcp({"category": "shirt", "color": "black", "max_price": 1500})
    assert ids(items) == ["S1"]
    assert items[0]["image_url"] == "https://img.example/s1.jpg"
    assert items[0]["product_url"] == "https://shop.example/s1"


def test_mcp_tool_null_image_and_limit(patched):
    items = _call_via_mcp({"color": "black", "limit": 5})
    s2 = next(i for i in items if i["product_id"] == "S2")
    assert s2["image_url"] is None
    assert len(_call_via_mcp({"limit": 2})) == 2


def test_mcp_tool_empty_result(patched):
    assert _call_via_mcp({"category": "hats"}) == []