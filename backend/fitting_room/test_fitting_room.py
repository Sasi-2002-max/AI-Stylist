"""
Tests for the Fitting Room Service (Parts 42-43).

Part 42 tests follow the same fake-MCP-client pattern as
test_shopping_agent.py: backend.agents.shopping_agent.MCPShoppingClient is
patched with a fake, so FittingRoomService is exercised through the real
(unmodified) ShoppingAgent.

Part 43 tests inject a FakeShoppingAgent directly into FittingRoomService.
That fake records every call and FAILS the test if any search method
(search / search_outfit / find_products) is ever invoked. Its product data
is TEST FIXTURE DATA ONLY and is not part of any production catalog.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from backend.fitting_room.schemas import MannequinGender, OutfitSummary
from backend.fitting_room.service import (
    FittingRoomService,
    InvalidMannequinGenderError,
    PRODUCT_NOT_FOUND_ERROR,
)
from backend.shopping.mcp_client import MCPConnectionError, MCPToolError


# ===========================================================================
# Fixtures (Part 42)
# ===========================================================================

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

PANTS_PRODUCT = {
    "product_id": "MOCK014",
    "store": "Demo Trends",
    "brand": "Chino Co",
    "title": "Beige Chinos",
    "category": "pants",
    "color": "beige",
    "price": 1399.0,
    "currency": "INR",
    "sizes": ["30", "32", "34"],
    "image_url": "https://cdn.demotrends.test/images/mock014.jpg",
    "product_url": "https://www.demotrends.test/product/MOCK014",
    "availability": True,
}

WHITE_VARIANT = {
    "product_id": "MOCK001-WHITE",
    "color": "white",
    "image_url": "https://cdn.mockfashionstore.test/images/mock001-white.jpg",
    "product_url": "https://www.mockfashionstore.test/product/MOCK001-WHITE",
    "price": 1299.0,
    "currency": "INR",
}

ALT_SHIRT = {
    "product_id": "MOCK002",
    "store": "Demo Style",
    "brand": "InkPrint",
    "title": "Black Graphic Shirt",
    "category": "shirts",
    "color": "black",
    "price": 1199.0,
    "currency": "INR",
    "sizes": ["S", "M", "L"],
    "image_url": None,
    "product_url": "https://www.demostyle.test/product/MOCK002",
    "availability": True,
}

COMPLETE_OUTFIT = {
    "status": "complete",
    "selected_products": [
        {"product_id": "MOCK001", "category": "shirts", "item_index": 0},
        {"product_id": "MOCK014", "category": "pants", "item_index": 1},
    ],
    "total_price": 2698.0,
    "missing_items": [],
}

INCOMPLETE_OUTFIT = {
    "status": "incomplete",
    "selected_products": [
        {"product_id": "MOCK001", "category": "shirts", "item_index": 0},
    ],
    "total_price": 1299.0,
    "missing_items": [
        {"index": 1, "item": {"category": "pants", "item": "x"}, "status": "no_results"}
    ],
}

EMPTY_OUTFIT = {
    "status": "incomplete",
    "selected_products": [],
    "total_price": 0.0,
    "missing_items": [],
}


# ===========================================================================
# Fake MCP client (Part 42)
# ===========================================================================

class FakeProductMCPClient:
    """Fake MCPShoppingClient exposing only what FittingRoomService needs."""

    def __init__(
        self,
        *,
        products: Optional[Dict[str, Dict[str, Any]]] = None,
        variants: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        alternatives: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        connect_error: Optional[Exception] = None,
        get_product_error: Optional[Exception] = None,
    ) -> None:
        self._products = products or {}
        self._variants = variants or {}
        self._alternatives = alternatives or {}
        self._connect_error = connect_error
        self._get_product_error = get_product_error

        self.search_calls: List[Dict[str, Any]] = []
        self.get_product_calls: List[str] = []
        self.get_variants_calls: List[str] = []
        self.get_alternatives_calls: List[str] = []

    async def __aenter__(self) -> "FakeProductMCPClient":
        if self._connect_error:
            raise self._connect_error
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def search_products(self, query="", budget=None, category=None, color=None):
        self.search_calls.append(
            {"query": query, "budget": budget, "category": category, "color": color}
        )
        return []

    async def get_product(self, product_id: str) -> Dict[str, Any]:
        self.get_product_calls.append(product_id)
        if self._get_product_error:
            raise self._get_product_error
        product = self._products.get(product_id)
        if product is None:
            return {"found": False, "product_id": product_id, "product": None}
        return {"found": True, "product_id": product_id, "product": product}

    async def get_variants(self, product_id: str) -> List[Dict[str, Any]]:
        self.get_variants_calls.append(product_id)
        return self._variants.get(product_id, [])

    async def get_alternatives(self, product_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        self.get_alternatives_calls.append(product_id)
        return self._alternatives.get(product_id, [])[:limit]

    async def check_availability(self, product_id: str, size=None) -> Dict[str, Any]:
        return {"product_id": product_id, "available": True}


def _run(awaitable):
    return asyncio.run(awaitable)


def _patched(fake: FakeProductMCPClient):
    return patch("backend.agents.shopping_agent.MCPShoppingClient", return_value=fake)


# ===========================================================================
# PART 42 TESTS (unchanged)
# ===========================================================================

def test_female_mannequin_resolves_correctly():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(COMPLETE_OUTFIT, "female")
        )
    assert response.mannequin.gender == MannequinGender.FEMALE
    assert response.mannequin.asset == "assets/fitting-room/female-mannequin.png"


def test_male_mannequin_resolves_correctly():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(COMPLETE_OUTFIT, "male")
        )
    assert response.mannequin.gender == MannequinGender.MALE
    assert response.mannequin.asset == "assets/fitting-room/male-mannequin.png"


def test_invalid_mannequin_gender_is_rejected():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        with pytest.raises(InvalidMannequinGenderError):
            _run(FittingRoomService().prepare_fitting_room(COMPLETE_OUTFIT, "robot"))


def test_complete_outfit_returns_ready_status():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(COMPLETE_OUTFIT, "female")
        )
    assert response.status == "ready"


def test_incomplete_outfit_stays_incomplete():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(INCOMPLETE_OUTFIT, "female")
        )
    assert response.status == "incomplete"


def test_selected_products_are_resolved():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=False
            )
        )
    assert response.items[0].product.product_id == "MOCK001"
    assert response.items[1].product.product_id == "MOCK014"


def test_product_metadata_is_fully_preserved():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=False
            )
        )
    shirt = response.items[0].product
    for key, value in SHIRT_PRODUCT.items():
        assert getattr(shirt, key) == value


def test_image_url_is_preserved():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=False
            )
        )
    assert response.items[0].product.image_url == SHIRT_PRODUCT["image_url"]


def test_product_url_is_preserved():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=False
            )
        )
    assert response.items[0].product.product_url == SHIRT_PRODUCT["product_url"]


def test_missing_product_is_reported_not_fabricated():
    fake = FakeProductMCPClient(products={"MOCK014": PANTS_PRODUCT})  # MOCK001 absent
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=False
            )
        )
    missing_item = response.items[0]
    assert missing_item.product is None
    assert missing_item.error == PRODUCT_NOT_FOUND_ERROR


def test_variants_are_returned_when_enabled():
    fake = FakeProductMCPClient(
        products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT},
        variants={"MOCK001": [WHITE_VARIANT]},
    )
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_alternatives=False
            )
        )
    assert len(response.items[0].color_variations) == 1
    assert response.items[0].color_variations[0].product_id == "MOCK001-WHITE"


def test_no_variants_returns_empty_list():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_alternatives=False
            )
        )
    assert response.items[0].color_variations == []


def test_alternatives_are_returned_when_enabled():
    fake = FakeProductMCPClient(
        products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT},
        alternatives={"MOCK001": [ALT_SHIRT]},
    )
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False
            )
        )
    assert len(response.items[0].alternatives) == 1
    assert response.items[0].alternatives[0].product_id == "MOCK002"


def test_no_alternatives_returns_empty_list():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False
            )
        )
    assert response.items[0].alternatives == []


def test_include_variants_false_makes_no_variant_calls():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=True
            )
        )
    assert fake.get_variants_calls == []


def test_include_alternatives_false_makes_no_alternative_calls():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=True, include_alternatives=False
            )
        )
    assert fake.get_alternatives_calls == []


def test_no_new_search_is_performed():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        _run(FittingRoomService().prepare_fitting_room(COMPLETE_OUTFIT, "female"))
    assert fake.search_calls == []


def test_item_order_and_index_follow_selected_products():
    fake = FakeProductMCPClient(
        products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT},
    )
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=False
            )
        )
    assert [item.item_index for item in response.items] == [0, 1]
    assert [item.product.product_id for item in response.items] == ["MOCK001", "MOCK014"]


def test_total_price_is_preserved_from_outfit():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                COMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=False
            )
        )
    assert response.outfit.total_price == COMPLETE_OUTFIT["total_price"]


def test_missing_items_are_preserved():
    fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT})
    with _patched(fake):
        response = _run(
            FittingRoomService().prepare_fitting_room(
                INCOMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=False
            )
        )
    assert len(response.outfit.missing_items) == 1
    assert response.outfit.missing_items[0]["status"] == "no_results"


def test_mcp_connection_error_propagates():
    fake = FakeProductMCPClient(
        products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT},
        connect_error=MCPConnectionError("down"),
    )
    with _patched(fake):
        with pytest.raises(MCPConnectionError):
            _run(FittingRoomService().prepare_fitting_room(COMPLETE_OUTFIT, "female"))


def test_mcp_tool_error_propagates():
    fake = FakeProductMCPClient(
        products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT},
        get_product_error=MCPToolError("get_product", "boom"),
    )
    with _patched(fake):
        with pytest.raises(MCPToolError):
            _run(FittingRoomService().prepare_fitting_room(COMPLETE_OUTFIT, "female"))


def test_empty_selected_products_is_handled():
    fake = FakeProductMCPClient()
    with _patched(fake):
        response = _run(FittingRoomService().prepare_fitting_room(EMPTY_OUTFIT, "female"))
    assert response.items == []
    assert response.status == "incomplete"
    assert fake.get_product_calls == []


def test_service_is_deterministic():
    def run_once():
        fake = FakeProductMCPClient(products={"MOCK001": SHIRT_PRODUCT, "MOCK014": PANTS_PRODUCT})
        with _patched(fake):
            return _run(
                FittingRoomService().prepare_fitting_room(
                    COMPLETE_OUTFIT, "female", include_variants=False, include_alternatives=False
                )
            )

    first, second = run_once(), run_once()
    assert first.model_dump() == second.model_dump()


# ===========================================================================
# PART 43 -- product visual source
# ===========================================================================
#
# TEST FIXTURE DATA ONLY. Not part of any production catalog.

P43_SHIRT = {
    "product_id": "AMZ123",
    "store": "Demo Fashion",
    "brand": "Urban Weave",
    "title": "Black Oxford Shirt",
    "category": "shirts",
    "color": "black",
    "price": 1299,
    "currency": "INR",
    "sizes": ["S", "M", "L"],
    "image_url": "https://example.test/amz123.jpg",
    "product_url": "https://example.test/amz123",
    "availability": True,
}

P43_PANTS = {
    "product_id": "MYN456",
    "store": "Demo Trends",
    "brand": "Chino Co",
    "title": "Cream Chinos",
    "category": "pants",
    "color": "cream",
    "price": 1499,
    "currency": "INR",
    "sizes": ["30", "32", "34"],
    "image_url": "https://example.test/myn456.jpg",
    "product_url": "https://example.test/myn456",
    "availability": True,
}

# Real product with NO image: image_url must stay None.
P43_SHOES_NO_IMAGE = {
    "product_id": "AJ789",
    "store": "Demo Footwear",
    "brand": "StepUp",
    "title": "Brown Leather Loafers",
    "category": "shoes",
    "color": "brown",
    "price": 1599,
    "currency": "INR",
    "sizes": ["8", "9", "10"],
    "image_url": None,
    "product_url": "https://example.test/aj789",
    "availability": True,
}

P43_SHIRT_VARIANTS = [
    {
        "product_id": "AMZ123-WHITE",
        "color": "white",
        "image_url": "https://example.test/amz123-white.jpg",
        "product_url": "https://example.test/amz123-white",
        "price": 1299,
        "currency": "INR",
    },
    {
        "product_id": "AMZ123-NAVY",
        "color": "navy",
        "image_url": None,  # real source has no variation image
        "product_url": "https://example.test/amz123-navy",
        "price": 1349,
        "currency": "INR",
    },
]

P43_SHIRT_ALTERNATIVES = [
    {
        "product_id": "AMZ124",
        "store": "Demo Fashion",
        "brand": "Urban Weave",
        "title": "Black Linen Shirt",
        "category": "shirts",
        "color": "black",
        "price": 1399,
        "currency": "INR",
        "sizes": ["M", "L"],
        "image_url": "https://example.test/amz124.jpg",
        "product_url": "https://example.test/amz124",
        "availability": True,
    }
]

P43_COMPLETE_OUTFIT = {
    "status": "complete",
    "selected_products": [
        {"product_id": "AMZ123", "category": "shirts", "item_index": 0},
        {"product_id": "MYN456", "category": "pants", "item_index": 1},
        {"product_id": "AJ789", "category": "shoes", "item_index": 2},
    ],
    "total_price": 4397,
    "missing_items": [],
}

P43_INCOMPLETE_OUTFIT = {
    "status": "incomplete",
    "selected_products": [
        {"product_id": "AMZ123", "category": "shirts", "item_index": 0},
        {"product_id": "MYN456", "category": "pants", "item_index": 1},
    ],
    "total_price": 2798,
    "missing_items": [
        {"index": 2, "item": {"category": "shoes", "item": "brown"}, "status": "no_results"}
    ],
}


class FakeShoppingAgent:
    """
    Fake ShoppingAgent injected directly into FittingRoomService.

    Only get_product / get_variants / get_alternatives are legitimate. Any
    call to search / search_outfit / find_products is recorded in
    `forbidden_calls` and raises AssertionError, so a test fails whether
    or not the service swallows the exception.
    """

    def __init__(
        self,
        *,
        products: Optional[Dict[str, Dict[str, Any]]] = None,
        variants: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        alternatives: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        get_product_error: Optional[Exception] = None,
        get_variants_error: Optional[Exception] = None,
        get_alternatives_error: Optional[Exception] = None,
    ) -> None:
        self._products = products or {}
        self._variants = variants or {}
        self._alternatives = alternatives or {}
        self._get_product_error = get_product_error
        self._get_variants_error = get_variants_error
        self._get_alternatives_error = get_alternatives_error

        self.get_product_calls: List[str] = []
        self.get_variants_calls: List[str] = []
        self.get_alternatives_calls: List[str] = []
        self.forbidden_calls: List[str] = []

    async def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        self.get_product_calls.append(product_id)
        if self._get_product_error:
            raise self._get_product_error
        return self._products.get(product_id)

    async def get_variants(self, product_id: str) -> List[Dict[str, Any]]:
        self.get_variants_calls.append(product_id)
        if self._get_variants_error:
            raise self._get_variants_error
        return self._variants.get(product_id, [])

    async def get_alternatives(self, product_id: str) -> List[Dict[str, Any]]:
        self.get_alternatives_calls.append(product_id)
        if self._get_alternatives_error:
            raise self._get_alternatives_error
        return self._alternatives.get(product_id, [])

    async def search(self, *args, **kwargs):
        self.forbidden_calls.append("search")
        raise AssertionError("Fitting room must not call ShoppingAgent.search()")

    async def search_outfit(self, *args, **kwargs):
        self.forbidden_calls.append("search_outfit")
        raise AssertionError("Fitting room must not call ShoppingAgent.search_outfit()")

    async def find_products(self, *args, **kwargs):
        self.forbidden_calls.append("find_products")
        raise AssertionError("Fitting room must not call ShoppingAgent.find_products()")


def _full_catalog() -> Dict[str, Dict[str, Any]]:
    return {
        "AMZ123": P43_SHIRT,
        "MYN456": P43_PANTS,
        "AJ789": P43_SHOES_NO_IMAGE,
    }


def _prepare(agent: FakeShoppingAgent, outfit=None, gender="female", **kwargs):
    service = FittingRoomService(shopping_agent=agent)
    return _run(
        service.prepare_fitting_room(outfit or P43_COMPLETE_OUTFIT, gender, **kwargs)
    )


# 1. Part 41 selected product IDs are resolved correctly
def test_p43_selected_product_ids_are_resolved():
    agent = FakeShoppingAgent(products=_full_catalog())
    response = _prepare(agent)
    assert [i.product.product_id for i in response.items] == ["AMZ123", "MYN456", "AJ789"]


# 2. Multiple selected products remain separate (shirt / pants / shoes)
def test_p43_multiple_products_remain_separate():
    agent = FakeShoppingAgent(products=_full_catalog())
    response = _prepare(agent)
    by_index = {i.item_index: i for i in response.items}
    assert by_index[0].product.product_id == "AMZ123"
    assert by_index[0].category == "shirts"
    assert by_index[1].product.product_id == "MYN456"
    assert by_index[1].category == "pants"
    assert by_index[2].product.product_id == "AJ789"
    assert by_index[2].category == "shoes"
    assert by_index[0].product.title != by_index[1].product.title != by_index[2].product.title


# 3. Exact product_id preserved
def test_p43_exact_product_id_preserved():
    agent = FakeShoppingAgent(products=_full_catalog())
    response = _prepare(agent)
    for item, selected in zip(response.items, P43_COMPLETE_OUTFIT["selected_products"]):
        assert item.product.product_id == selected["product_id"]


# 4. Exact image_url preserved
def test_p43_exact_image_url_preserved():
    agent = FakeShoppingAgent(products=_full_catalog())
    response = _prepare(agent)
    assert response.items[0].product.image_url == "https://example.test/amz123.jpg"
    assert response.items[1].product.image_url == "https://example.test/myn456.jpg"


# 5. product_url preserved
def test_p43_product_url_preserved():
    agent = FakeShoppingAgent(products=_full_catalog())
    response = _prepare(agent)
    assert response.items[0].product.product_url == "https://example.test/amz123"
    assert response.items[2].product.product_url == "https://example.test/aj789"


# 6. image_url=None stays None (and no visual_source is claimed)
def test_p43_image_url_none_remains_none():
    agent = FakeShoppingAgent(products=_full_catalog())
    response = _prepare(agent)
    shoes = response.items[2]
    assert shoes.product.image_url is None
    assert shoes.visual_source is None
    assert shoes.error is None


def test_p43_visual_source_is_product_image_when_image_exists():
    agent = FakeShoppingAgent(products=_full_catalog())
    response = _prepare(agent)
    assert response.items[0].visual_source == "product_image"
    assert response.items[1].visual_source == "product_image"


# 7. No fake product is created
def test_p43_no_fake_product_is_created():
    agent = FakeShoppingAgent(products={"AMZ123": P43_SHIRT})  # MYN456, AJ789 unknown
    response = _prepare(agent)
    assert response.items[0].product.product_id == "AMZ123"
    for item in response.items[1:]:
        assert item.product is None
        assert item.visual_source is None
        assert item.color_variations == []
        assert item.alternatives == []
        assert item.error == PRODUCT_NOT_FOUND_ERROR


# 8. No fitting-room search is ever performed
def test_p43_no_search_methods_are_called():
    agent = FakeShoppingAgent(
        products=_full_catalog(),
        variants={"AMZ123": P43_SHIRT_VARIANTS},
        alternatives={"AMZ123": P43_SHIRT_ALTERNATIVES},
    )
    _prepare(agent, include_variants=True, include_alternatives=True)
    assert agent.forbidden_calls == []


# 9. get_product() is called for each selected product
def test_p43_get_product_called_for_each_selected_product():
    agent = FakeShoppingAgent(products=_full_catalog())
    _prepare(agent)
    assert agent.get_product_calls == ["AMZ123", "MYN456", "AJ789"]


# 10. get_variants() only when include_variants=True
def test_p43_get_variants_only_when_requested():
    agent = FakeShoppingAgent(products=_full_catalog())
    _prepare(agent, include_variants=False, include_alternatives=False)
    assert agent.get_variants_calls == []

    agent = FakeShoppingAgent(products=_full_catalog())
    _prepare(agent, include_variants=True, include_alternatives=False)
    assert agent.get_variants_calls == ["AMZ123", "MYN456", "AJ789"]


# 11. get_alternatives() only when include_alternatives=True
def test_p43_get_alternatives_only_when_requested():
    agent = FakeShoppingAgent(products=_full_catalog())
    _prepare(agent, include_variants=False, include_alternatives=False)
    assert agent.get_alternatives_calls == []

    agent = FakeShoppingAgent(products=_full_catalog())
    _prepare(agent, include_variants=False, include_alternatives=True)
    assert agent.get_alternatives_calls == ["AMZ123", "MYN456", "AJ789"]


# A missing product must not trigger variant/alternative lookups
def test_p43_missing_product_skips_variant_and_alternative_calls():
    agent = FakeShoppingAgent(products={})
    _prepare(agent, include_variants=True, include_alternatives=True)
    assert agent.get_variants_calls == []
    assert agent.get_alternatives_calls == []


# 12. Real color variations preserved (including image_url=None)
def test_p43_real_color_variations_preserved():
    agent = FakeShoppingAgent(
        products=_full_catalog(),
        variants={"AMZ123": P43_SHIRT_VARIANTS},
    )
    response = _prepare(agent, include_alternatives=False)
    variations = response.items[0].color_variations
    assert [v.product_id for v in variations] == ["AMZ123-WHITE", "AMZ123-NAVY"]
    assert [v.color for v in variations] == ["white", "navy"]
    assert variations[0].image_url == "https://example.test/amz123-white.jpg"
    assert variations[0].product_url == "https://example.test/amz123-white"
    assert variations[0].price == 1299
    assert variations[0].currency == "INR"
    assert variations[1].image_url is None  # not invented
    assert variations[1].price == 1349


# 13. Real alternatives preserved
def test_p43_real_alternatives_preserved():
    agent = FakeShoppingAgent(
        products=_full_catalog(),
        alternatives={"AMZ123": P43_SHIRT_ALTERNATIVES},
    )
    response = _prepare(agent, include_variants=False)
    alts = response.items[0].alternatives
    assert len(alts) == 1
    assert alts[0].product_id == "AMZ124"
    assert alts[0].image_url == "https://example.test/amz124.jpg"
    assert alts[0].product_url == "https://example.test/amz124"


# 14. Missing product produces error = "product_not_found"
def test_p43_missing_product_error():
    agent = FakeShoppingAgent(products={"MYN456": P43_PANTS, "AJ789": P43_SHOES_NO_IMAGE})
    response = _prepare(agent)
    assert response.items[0].product is None
    assert response.items[0].error == "product_not_found"


# 15. MCPConnectionError propagates
def test_p43_mcp_connection_error_propagates():
    agent = FakeShoppingAgent(get_product_error=MCPConnectionError("down"))
    with pytest.raises(MCPConnectionError):
        _prepare(agent)


# 16. MCPToolError propagates (from every resolution call)
def test_p43_mcp_tool_error_propagates_from_get_product():
    agent = FakeShoppingAgent(get_product_error=MCPToolError("get_product", "boom"))
    with pytest.raises(MCPToolError):
        _prepare(agent)


def test_p43_mcp_tool_error_propagates_from_get_variants():
    agent = FakeShoppingAgent(
        products=_full_catalog(),
        get_variants_error=MCPToolError("get_variants", "boom"),
    )
    with pytest.raises(MCPToolError):
        _prepare(agent, include_variants=True)


def test_p43_mcp_tool_error_propagates_from_get_alternatives():
    agent = FakeShoppingAgent(
        products=_full_catalog(),
        get_alternatives_error=MCPToolError("get_alternatives", "boom"),
    )
    with pytest.raises(MCPToolError):
        _prepare(agent, include_alternatives=True)


# 17. Female mannequin
def test_p43_female_mannequin():
    response = _prepare(FakeShoppingAgent(products=_full_catalog()), gender="female")
    assert response.mannequin.gender == MannequinGender.FEMALE
    assert response.mannequin.asset == "assets/fitting-room/female-mannequin.png"


# 18. Male mannequin
def test_p43_male_mannequin():
    response = _prepare(FakeShoppingAgent(products=_full_catalog()), gender="male")
    assert response.mannequin.gender == MannequinGender.MALE
    assert response.mannequin.asset == "assets/fitting-room/male-mannequin.png"


# 19. Invalid mannequin gender still raises the existing error
def test_p43_invalid_mannequin_gender_raises():
    agent = FakeShoppingAgent(products=_full_catalog())
    with pytest.raises(InvalidMannequinGenderError):
        _prepare(agent, gender="robot")
    # Fails before any product resolution.
    assert agent.get_product_calls == []


# 20. Incomplete outfit stays incomplete, never "ready"
def test_p43_incomplete_outfit_never_ready():
    agent = FakeShoppingAgent(products=_full_catalog())
    response = _prepare(agent, outfit=P43_INCOMPLETE_OUTFIT)
    assert response.status == "incomplete"
    assert response.status != "ready"


# 21. Complete outfit becomes "ready"
def test_p43_complete_outfit_is_ready():
    response = _prepare(FakeShoppingAgent(products=_full_catalog()))
    assert response.status == "ready"


# 22. total_price preserved (not recomputed)
def test_p43_total_price_preserved():
    response = _prepare(FakeShoppingAgent(products=_full_catalog()))
    assert response.outfit.total_price == 4397


# 23. missing_items preserved
def test_p43_missing_items_preserved():
    agent = FakeShoppingAgent(products=_full_catalog())
    response = _prepare(agent, outfit=P43_INCOMPLETE_OUTFIT)
    assert response.outfit.missing_items == P43_INCOMPLETE_OUTFIT["missing_items"]
    assert len(response.items) == 2  # only what Part 41 selected


# 24. Dict-based and model-based OutfitSummary both work
def test_p43_dict_and_model_outfit_inputs_work():
    from_dict = _prepare(FakeShoppingAgent(products=_full_catalog()), outfit=P43_COMPLETE_OUTFIT)
    from_model = _prepare(
        FakeShoppingAgent(products=_full_catalog()),
        outfit=OutfitSummary.model_validate(P43_COMPLETE_OUTFIT),
    )
    assert from_dict.status == from_model.status == "ready"
    assert from_dict.model_dump() == from_model.model_dump()


# 25. Deterministic
def test_p43_response_is_deterministic():
    def run_once():
        agent = FakeShoppingAgent(
            products=_full_catalog(),
            variants={"AMZ123": P43_SHIRT_VARIANTS},
            alternatives={"AMZ123": P43_SHIRT_ALTERNATIVES},
        )
        return _prepare(agent)

    assert run_once().model_dump() == run_once().model_dump()