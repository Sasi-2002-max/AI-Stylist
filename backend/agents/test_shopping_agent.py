"""
Tests for the Shopping Agent (Part 39).

MCPShoppingClient is replaced with FakeMCPShoppingClient -- a minimal
stand-in implementing the same async-context-manager protocol and public
methods -- so these tests never spawn a real MCP subprocess. This tests the
Shopping Agent's own logic while treating MCPShoppingClient's documented
contract as the source of truth, per the project's testing convention.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from backend.agents.shopping_agent import ShoppingAgent, extract_requirements
from backend.shopping.mcp_client import MCPConnectionError, MCPToolError


class FakeMCPShoppingClient:
    """Stand-in for MCPShoppingClient with the same async context-manager protocol."""

    def __init__(
        self,
        *,
        search_results: Optional[List[Dict[str, Any]]] = None,
        availability: Optional[Dict[str, Dict[str, Any]]] = None,
        get_product_result: Optional[Dict[str, Any]] = None,
        variants: Optional[List[Dict[str, Any]]] = None,
        alternatives: Optional[List[Dict[str, Any]]] = None,
        search_error: Optional[Exception] = None,
        connect_error: Optional[Exception] = None,
    ) -> None:
        self._search_results = search_results if search_results is not None else []
        self._availability = availability or {}
        self._get_product_result = get_product_result
        self._variants = variants if variants is not None else []
        self._alternatives = alternatives if alternatives is not None else []
        self._search_error = search_error
        self._connect_error = connect_error

        self.search_calls: List[Dict[str, Any]] = []
        self.availability_calls: List[Dict[str, Any]] = []

    async def __aenter__(self):
        if self._connect_error:
            raise self._connect_error
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def search_products(self, query="", budget=None, category=None, color=None):
        self.search_calls.append(
            {"query": query, "budget": budget, "category": category, "color": color}
        )
        if self._search_error:
            raise self._search_error
        return self._search_results

    async def check_availability(self, product_id, size=None):
        self.availability_calls.append({"product_id": product_id, "size": size})
        return self._availability.get(
            product_id, {"product_id": product_id, "available": True}
        )

    async def get_product(self, product_id):
        return self._get_product_result

    async def get_variants(self, product_id):
        return self._variants

    async def get_alternatives(self, product_id, limit=5):
        return self._alternatives[:limit]


def _run(coro):
    return asyncio.run(coro)


def _patched(fake_client: FakeMCPShoppingClient):
    return patch("backend.agents.shopping_agent.MCPShoppingClient", return_value=fake_client)


SHIRT_PRODUCT = {
    "product_id": "MOCK001",
    "store": "Demo Fashion",
    "brand": "Urban Weave",
    "title": "Black Oxford Shirt",
    "category": "shirts",
    "color": "black",
    "price": 1299.0,
    "currency": "INR",
    "sizes": ["S", "M", "L", "XL"],
    "image_url": "https://cdn.mockfashionstore.test/images/mock001.jpg",
    "product_url": "https://www.mockfashionstore.test/product/MOCK001",
    "availability": True,
}

NO_IMAGE_PRODUCT = {
    "product_id": "MOCK003",
    "store": "Demo Style",
    "brand": "Casely",
    "title": "Navy Casual Shirt",
    "category": "shirts",
    "color": "navy",
    "price": 999.0,
    "currency": "INR",
    "sizes": ["S", "M", "L"],
    "image_url": None,
    "product_url": "https://www.demostyle.test/product/MOCK003",
    "availability": True,
}


# 1. Basic shopping search works
def test_basic_search_returns_products():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="black shirt"))
    assert len(results) == 1
    assert results[0]["product_id"] == "MOCK001"


# 2. The agent uses MCPShoppingClient
def test_agent_uses_mcp_shopping_client():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake) as mock_client_cls:
        _run(ShoppingAgent().search(query="black shirt"))
    mock_client_cls.assert_called()


# 3. Search query forwarded correctly
def test_query_is_forwarded():
    fake = FakeMCPShoppingClient(search_results=[])
    with _patched(fake):
        _run(ShoppingAgent().search(query="black shirt for wedding"))
    assert fake.search_calls[0]["query"] == "black shirt for wedding"


# 4. Budget respected
def test_budget_is_forwarded_to_mcp():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake):
        _run(ShoppingAgent().search(query="shirt", budget=1500))
    assert fake.search_calls[0]["budget"] == 1500


# 5. Category filtering works
def test_category_is_forwarded_to_mcp():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake):
        _run(ShoppingAgent().search(query="", category="shirts"))
    assert fake.search_calls[0]["category"] == "shirts"


# 6. Color filtering works
def test_color_is_forwarded_to_mcp():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake):
        _run(ShoppingAgent().search(query="", color="black"))
    assert fake.search_calls[0]["color"] == "black"


# 7. Size-specific availability is handled
def test_size_specific_availability_filters_out_unavailable_size():
    fake = FakeMCPShoppingClient(
        search_results=[SHIRT_PRODUCT],
        availability={"MOCK001": {"product_id": "MOCK001", "available": False}},
    )
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="shirt", size="M"))
    assert results == []
    assert fake.availability_calls[0] == {"product_id": "MOCK001", "size": "M"}


def test_size_specific_availability_keeps_available_product():
    fake = FakeMCPShoppingClient(
        search_results=[SHIRT_PRODUCT],
        availability={"MOCK001": {"product_id": "MOCK001", "available": True}},
    )
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="shirt", size="M"))
    assert len(results) == 1


def test_requested_size_absent_from_product_sizes_excludes_it_without_extra_call():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="shirt", size="XXXL"))
    assert results == []
    assert fake.availability_calls == []


# 8. Empty search results remain empty
def test_empty_search_results_remain_empty():
    fake = FakeMCPShoppingClient(search_results=[])
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="nonexistent product zzz"))
    assert results == []


# 9. MCPConnectionError is not swallowed
def test_mcp_connection_error_is_not_swallowed():
    fake = FakeMCPShoppingClient(connect_error=MCPConnectionError("could not connect"))
    with _patched(fake):
        with pytest.raises(MCPConnectionError):
            _run(ShoppingAgent().search(query="shirt"))


# 10. MCPToolError is not swallowed
def test_mcp_tool_error_is_not_swallowed():
    fake = FakeMCPShoppingClient(search_error=MCPToolError("search_products", "boom"))
    with _patched(fake):
        with pytest.raises(MCPToolError):
            _run(ShoppingAgent().search(query="shirt"))


# 11. Product metadata preserved
def test_product_metadata_is_fully_preserved():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="shirt"))
    for key, value in SHIRT_PRODUCT.items():
        assert results[0][key] == value


# 12. image_url is preserved
def test_image_url_is_preserved():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="shirt"))
    assert results[0]["image_url"] == SHIRT_PRODUCT["image_url"]


# 13. image_url=None remains None
def test_missing_image_url_remains_none():
    fake = FakeMCPShoppingClient(search_results=[NO_IMAGE_PRODUCT])
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="shirt"))
    assert results[0]["image_url"] is None


# 14. product_url preserved separately
def test_product_url_is_preserved_separately():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="shirt"))
    assert results[0]["product_url"] == SHIRT_PRODUCT["product_url"]
    assert results[0]["image_url"] != results[0]["product_url"]


# 15 & 16. Neither URL is ever cross-derived
def test_urls_are_never_cross_derived():
    fake = FakeMCPShoppingClient(search_results=[NO_IMAGE_PRODUCT])
    with _patched(fake):
        results = _run(ShoppingAgent().search(query="shirt"))
    result = results[0]
    assert result["image_url"] is None
    assert result["product_url"] == NO_IMAGE_PRODUCT["product_url"]


# 17. Results are deterministic
def test_results_are_deterministic():
    fake1 = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT, NO_IMAGE_PRODUCT])
    fake2 = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT, NO_IMAGE_PRODUCT])

    with _patched(fake1):
        first = _run(ShoppingAgent().search(query="shirt", color="black"))
    with _patched(fake2):
        second = _run(ShoppingAgent().search(query="shirt", color="black"))

    assert [p["product_id"] for p in first] == [p["product_id"] for p in second]


# 18. The agent does not import MockStore or other store implementations
def test_agent_module_does_not_import_forbidden_modules():
    from backend.agents import shopping_agent as module

    source = inspect.getsource(module)
    forbidden = [
        "MockStore", "BaseStore", "AmazonStore", "MyntraStore",
        "HMStore", "AjioStore", "mcp_server", "products.json",
    ]
    for name in forbidden:
        assert name not in source, f"shopping_agent.py must not reference {name}"


# Extra: natural-language requirement extraction (find_products entry point)
def test_extract_requirements_finds_category_color_and_budget():
    requirements = extract_requirements("I need a black shirt under ₹1500")
    assert requirements["category"] == "shirts"
    assert requirements["color"] == "black"
    assert requirements["budget"] == 1500.0


def test_extract_requirements_handles_missing_signals_gracefully():
    requirements = extract_requirements("something stylish")
    assert requirements["category"] is None
    assert requirements["color"] is None
    assert requirements["budget"] is None


def test_find_products_uses_extracted_requirements():
    fake = FakeMCPShoppingClient(search_results=[SHIRT_PRODUCT])
    with _patched(fake):
        results = _run(ShoppingAgent().find_products("I need a black shirt under ₹1500"))
    assert fake.search_calls[0]["category"] == "shirts"
    assert fake.search_calls[0]["color"] == "black"
    assert fake.search_calls[0]["budget"] == 1500.0
    assert len(results) == 1