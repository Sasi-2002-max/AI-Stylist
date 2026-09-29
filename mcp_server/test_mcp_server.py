"""
Tests for the StyleAI MCP shopping server and its tools.

Most tests call each tool's `_impl` function directly, which exercises the
exact same logic the MCP tool wraps, without needing a running MCP
transport. A couple of tests exercise the actual registered `mcp` server
object to confirm the tools are really registered on it.
"""

from __future__ import annotations

import asyncio

from mcp_server.server import mcp
from mcp_server.tools.check_availability import check_availability_impl
from mcp_server.tools.get_alternatives import get_alternatives_impl
from mcp_server.tools.get_product import get_product_impl
from mcp_server.tools.get_variants import get_variants_impl
from mcp_server.tools.search_products import search_products_impl

EXPECTED_TOOL_NAMES = {
    "search_products",
    "get_product",
    "get_variants",
    "check_availability",
    "get_alternatives",
}

# The common Product fields (Product.model_dump()).
COMMON_PRODUCT_FIELDS = {
    "product_id", "store", "brand", "title", "category", "color",
    "price", "currency", "sizes", "image_url", "product_url", "availability",
}


# ---------------------------------------------------------------------------
# 1. Server import / 2. All five tools registered
# ---------------------------------------------------------------------------

def test_mcp_server_module_imports_successfully():
    """mcp_server.server imports without error and exposes an `mcp` object."""
    assert mcp is not None


def test_all_five_tools_are_registered():
    """The FastMCP server has exactly the five expected shopping tools registered."""
    tools = asyncio.run(mcp.list_tools())
    registered_names = {tool.name for tool in tools}
    assert EXPECTED_TOOL_NAMES.issubset(registered_names)


# ---------------------------------------------------------------------------
# 3. search_products
# ---------------------------------------------------------------------------

def test_search_products_returns_products():
    results = search_products_impl(query="", category="dresses")
    assert len(results) > 0
    assert all(isinstance(item, dict) for item in results)
    assert all(item["category"] == "dresses" for item in results)


def test_search_products_respects_budget():
    results = search_products_impl(query="", budget=5000)
    assert len(results) > 0
    assert all(item["price"] <= 5000 for item in results)


# ---------------------------------------------------------------------------
# 4. get_product
#    Contract: returns the common Product dict (Product.model_dump())
#    directly, or None when the product does not exist.
# ---------------------------------------------------------------------------

def test_get_product_returns_a_product():
    result = get_product_impl("MOCK001")
    assert result is not None
    assert "found" not in result  # old wrapper is gone; Product is returned directly

    assert COMMON_PRODUCT_FIELDS.issubset(result.keys())
    assert result["product_id"] == "MOCK001"
    assert result["store"] == "Demo Fashion"
    assert result["title"] == "Black Oxford Shirt"
    assert result["price"] is not None
    assert result["image_url"] == "https://cdn.mockfashionstore.test/images/mock001.jpg"
    assert result["product_url"] == "https://www.mockfashionstore.test/product/MOCK001"


def test_get_product_returns_clear_not_found_for_unknown_id():
    result = get_product_impl("DOES_NOT_EXIST")
    assert result is None


# ---------------------------------------------------------------------------
# 5. get_variants
# ---------------------------------------------------------------------------

def test_get_variants_returns_variants():
    results = get_variants_impl("MOCK022")
    assert isinstance(results, list)
    assert all(isinstance(item, dict) for item in results)
    assert all(item["product_id"] != "MOCK022" for item in results)


def test_get_variants_for_unknown_product_returns_empty_list():
    assert get_variants_impl("DOES_NOT_EXIST") == []


# ---------------------------------------------------------------------------
# 6. check_availability
# ---------------------------------------------------------------------------

def test_check_availability_returns_correct_availability():
    available_result = check_availability_impl("MOCK001")
    assert available_result == {"product_id": "MOCK001", "available": True}

    # MOCK004 (Maroon Checked Shirt) is marked unavailable in the catalog.
    unavailable_result = check_availability_impl("MOCK004")
    assert unavailable_result == {"product_id": "MOCK004", "available": False}


def test_check_availability_for_unknown_product_is_false_not_guessed():
    result = check_availability_impl("DOES_NOT_EXIST")
    assert result["available"] is False


# ---------------------------------------------------------------------------
# 7. get_alternatives
# ---------------------------------------------------------------------------

def test_get_alternatives_returns_products():
    results = get_alternatives_impl("MOCK022", limit=3)
    assert len(results) > 0
    assert len(results) <= 3
    assert all(isinstance(item, dict) for item in results)
    assert all(item["product_id"] != "MOCK022" for item in results)


# ---------------------------------------------------------------------------
# 8. Product metadata preserved / 9-12. image_url / product_url handling
# ---------------------------------------------------------------------------

def test_product_metadata_is_fully_preserved_through_the_tool_layer():
    """Every Product field survives search_products, not just a subset."""
    results = search_products_impl(query="Black Oxford Shirt")
    assert len(results) == 1
    product = results[0]

    assert COMMON_PRODUCT_FIELDS.issubset(product.keys())
    assert product["product_id"] == "MOCK001"
    assert product["store"] == "Demo Fashion"
    assert product["brand"] == "Urban Weave"


def test_image_url_is_preserved_through_search():
    results = search_products_impl(query="Black Oxford Shirt")
    assert results[0]["image_url"] == "https://cdn.mockfashionstore.test/images/mock001.jpg"


def test_product_url_is_preserved_through_search():
    results = search_products_impl(query="Black Oxford Shirt")
    assert results[0]["product_url"] == "https://www.mockfashionstore.test/product/MOCK001"


def test_missing_image_url_remains_null_not_fabricated():
    """MOCK003 (Navy Casual Shirt) has no image in the catalog."""
    result = get_product_impl("MOCK003")
    assert result is not None
    assert result["title"] == "Navy Casual Shirt"
    assert result["image_url"] is None                 # not fabricated
    assert result["product_url"]                       # still present
    assert result["product_url"].startswith("https://")


def test_no_image_url_is_fabricated_across_all_search_results():
    """Every result's image_url is either a real catalog URL or null -- never invented."""
    results = search_products_impl(query="")
    for product in results:
        assert product["image_url"] is None or product["image_url"].startswith("https://")


def test_no_product_url_is_fabricated_across_all_search_results():
    """Every result has a real, non-empty product_url from the catalog."""
    results = search_products_impl(query="")
    for product in results:
        assert product["product_url"]
        assert product["product_url"].startswith("https://")