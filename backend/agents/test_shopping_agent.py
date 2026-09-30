"""
Part 40 and Part 41 — Shopping Agent outfit-level tests.

Part 40 verifies:

Stylist OutfitPlan
        ↓
ShoppingAgent
        ↓
MCPShoppingClient
        ↓
search_products()
        ↓
Products
        ↓
Normalizer
        ↓
Ranker
        ↓
Ranked candidates

Part 41 verifies:

Ranked candidates (Part 40)
        ↓
select_outfit() / build_outfit()
        ↓
One selected product per outfit item + total price
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from backend.agents.shopping_agent import (
    ShoppingAgent,
    normalize_color,
    resolve_item_category,
    select_outfit,
)
from backend.schemas.outfit import OutfitItem, OutfitPlan
from backend.shopping.mcp_client import (
    MCPConnectionError,
    MCPToolError,
)


# ===========================================================================
# Test product fixtures
# ===========================================================================

SHIRT_PRODUCT = {
    "product_id": "MOCK001",
    "store": "Demo Fashion",
    "brand": "Oxford House",
    "title": "Black Oxford Shirt",
    "category": "shirts",
    "color": "black",
    "price": 1299.0,
    "currency": "INR",
    "sizes": ["S", "M", "L", "XL"],
    "image_url": "https://cdn.demofashion.test/images/mock001.jpg",
    "product_url": "https://www.demofashion.test/product/MOCK001",
    "availability": True,
}


NO_IMAGE_PRODUCT = {
    "product_id": "MOCK002",
    "store": "Demo Fashion",
    "brand": "Plainwear",
    "title": "Black Basic Shirt",
    "category": "shirts",
    "color": "black",
    "price": 1199.0,
    "currency": "INR",
    "sizes": ["S", "M", "L"],
    "image_url": None,
    "product_url": "https://www.demofashion.test/product/MOCK002",
    "availability": True,
}


NAVY_SHIRT_PRODUCT = {
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


SHOES_PRODUCT = {
    "product_id": "MOCK027",
    "store": "Demo Fashion",
    "brand": "Stridewell",
    "title": "Brown Leather Loafers",
    "category": "shoes",
    "color": "brown",
    "price": 1899.0,
    "currency": "INR",
    "sizes": ["6", "7", "8", "9", "10"],
    "image_url": None,
    "product_url": "https://www.mockfashionstore.test/product/MOCK027",
    "availability": True,
}


WATCH_PRODUCT = {
    "product_id": "MOCK032",
    "store": "Demo Fashion",
    "brand": "Timekeep",
    "title": "Silver Analog Watch",
    "category": "watches",
    "color": "silver",
    "price": 1999.0,
    "currency": "INR",
    "sizes": ["One Size"],
    "image_url": "https://cdn.mockfashionstore.test/images/mock032.jpg",
    "product_url": "https://www.mockfashionstore.test/product/MOCK032",
    "availability": True,
}


# ===========================================================================
# Fake MCP client
# ===========================================================================

class FakeMCPShoppingClient:
    """
    Test-only MCP client.

    This deliberately mimics the application-level interface used by
    ShoppingAgent without touching the real MCP server or store adapters.
    """

    def __init__(
        self,
        *,
        connect_error: Optional[Exception] = None,
        search_error: Optional[Exception] = None,
    ) -> None:
        self.connect_error = connect_error
        self._search_error = search_error

        self.search_calls: List[Dict[str, Any]] = []
        self.availability_calls: List[Dict[str, Any]] = []

    async def __aenter__(self) -> "FakeMCPShoppingClient":
        if self.connect_error:
            raise self.connect_error

        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        return None

    async def search_products(
        self,
        query: str = "",
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self.search_calls.append(
            {
                "query": query,
                "budget": budget,
                "category": category,
                "color": color,
            }
        )

        if self._search_error:
            raise self._search_error

        return []

    async def check_availability(
        self,
        product_id: str,
        size: str,
    ) -> Dict[str, Any]:
        self.availability_calls.append(
            {
                "product_id": product_id,
                "size": size,
            }
        )

        return {"available": True}

    async def get_product(
        self,
        product_id: str,
    ) -> Optional[Dict[str, Any]]:
        return None

    async def get_variants(
        self,
        product_id: str,
    ) -> List[Dict[str, Any]]:
        return []

    async def get_alternatives(
        self,
        product_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        return []


class CategoryAwareFakeClient(FakeMCPShoppingClient):
    """
    Fake MCP client that returns products according to searched category.
    """

    def __init__(
        self,
        by_category: Dict[str, List[Dict[str, Any]]],
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._by_category = by_category

    async def search_products(
        self,
        query: str = "",
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self.search_calls.append(
            {
                "query": query,
                "budget": budget,
                "category": category,
                "color": color,
            }
        )

        if self._search_error:
            raise self._search_error

        return self._by_category.get(category, [])


# ===========================================================================
# Test helpers
# ===========================================================================

def _run(awaitable: Any) -> Any:
    """
    Run an async test operation without requiring pytest-asyncio.
    """
    import asyncio

    return asyncio.run(awaitable)


def _patched(fake: FakeMCPShoppingClient):
    """
    Patch ShoppingAgent's MCP client with the supplied fake.
    """
    return patch(
        "backend.agents.shopping_agent.MCPShoppingClient",
        return_value=fake,
    )


def _plan(
    items: Optional[List[OutfitItem]] = None,
    accessories: Optional[List[OutfitItem]] = None,
    budget: Optional[float] = None,
) -> OutfitPlan:
    return OutfitPlan(
        occasion="wedding",
        style="elegant",
        items=items or [],
        accessories=accessories or [],
        budget=budget,
    )


# ===========================================================================
# Outfit fixtures
# ===========================================================================

BLACK_SHIRT = OutfitItem(
    category="shirt",
    item="Black Oxford shirt",
    color="Black",
)

BEIGE_CHINOS = OutfitItem(
    category="pants",
    item="Beige chinos",
    color="beige",
)

BROWN_LOAFERS = OutfitItem(
    category="shoes",
    item="Brown leather loafers",
    color="brown",
)

BROWN_BELT = OutfitItem(
    category="belt",
    item="Brown leather belt",
    color="brown",
)

SILVER_WATCH = OutfitItem(
    category="accessory",
    item="Silver watch",
    color="silver",
)


# ===========================================================================
# PART 40 — OUTFIT-LEVEL SEARCH
# ===========================================================================

# ===========================================================================
# 1. One stylist item -> one MCP search
# ===========================================================================

def test_one_outfit_item_makes_one_mcp_search():
    fake = CategoryAwareFakeClient(
        {"shirts": [SHIRT_PRODUCT]}
    )

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(
                _plan(items=[BLACK_SHIRT])
            )
        )

    assert len(fake.search_calls) == 1
    assert fake.search_calls[0]["category"] == "shirts"
    assert fake.search_calls[0]["color"] == "black"

    assert results[0]["status"] == "ok"
    assert results[0]["products"][0]["product_id"] == "MOCK001"


# ===========================================================================
# 2 & 7. Multiple items -> independent searches
# ===========================================================================

def test_multiple_outfit_items_are_searched_independently():
    fake = CategoryAwareFakeClient(
        {
            "shirts": [SHIRT_PRODUCT],
            "pants": [PANTS_PRODUCT],
            "shoes": [SHOES_PRODUCT],
        }
    )

    plan = _plan(
        items=[
            BLACK_SHIRT,
            BEIGE_CHINOS,
            BROWN_LOAFERS,
        ]
    )

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(plan)
        )

    assert [c["category"] for c in fake.search_calls] == [
        "shirts",
        "pants",
        "shoes",
    ]

    assert [c["color"] for c in fake.search_calls] == [
        "black",
        "beige",
        "brown",
    ]

    assert [
        [p["product_id"] for p in r["products"]]
        for r in results
    ] == [
        ["MOCK001"],
        ["MOCK014"],
        ["MOCK027"],
    ]


def test_accessories_are_searched_too():
    fake = CategoryAwareFakeClient(
        {"watches": [WATCH_PRODUCT]}
    )

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(
                _plan(accessories=[SILVER_WATCH])
            )
        )

    assert fake.search_calls[0]["category"] == "watches"
    assert results[0]["source"] == "accessories"
    assert results[0]["products"][0]["product_id"] == "MOCK032"


# ===========================================================================
# 3. Category normalization
# ===========================================================================

@pytest.mark.parametrize(
    "category,item_text,expected",
    [
        ("shirt", "Black Oxford shirt", "shirts"),
        ("pants", "Beige chinos", "pants"),
        ("bottom", "Beige chinos", "pants"),
        ("trousers", "Cream trousers", "pants"),
        ("footwear", "White sneakers", "shoes"),
        ("shoes", "Brown loafers", "shoes"),
        ("accessory", "Silver watch", "watches"),
        ("top", "Black t-shirt", "t-shirts"),
        ("dress", "Wrap dress", "dresses"),
    ],
)
def test_category_normalization(
    category: str,
    item_text: str,
    expected: str,
):
    item = OutfitItem(
        category=category,
        item=item_text,
    )

    assert resolve_item_category(item) == expected


# ===========================================================================
# 4. Unknown category is not guessed
# ===========================================================================

def test_unknown_category_resolves_to_none():
    assert resolve_item_category(BROWN_BELT) is None

    assert (
        resolve_item_category(
            OutfitItem(
                category="outerwear",
                item="Blazer",
            )
        )
        is None
    )


# ===========================================================================
# 5 & 6. Color normalization
# ===========================================================================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Black", "black"),
        ("WHITE", "white"),
        ("Navy Blue", "navy"),
        ("Gray", "grey"),
        ("charcoal", None),
        ("", None),
        (None, None),
    ],
)
def test_color_normalization(
    raw: Optional[str],
    expected: Optional[str],
):
    assert normalize_color(raw) == expected


def test_unknown_color_is_searched_without_color():
    item = OutfitItem(
        category="shirt",
        item="Charcoal shirt",
        color="charcoal",
    )

    fake = CategoryAwareFakeClient(
        {"shirts": [SHIRT_PRODUCT]}
    )

    with _patched(fake):
        _run(
            ShoppingAgent().search_outfit(
                _plan(items=[item])
            )
        )

    assert fake.search_calls[0]["color"] is None


# ===========================================================================
# 14. Unsupported category
# ===========================================================================

def test_unsupported_category_is_not_searched():
    fake = CategoryAwareFakeClient({})

    with _patched(fake) as mock_client_cls:
        results = _run(
            ShoppingAgent().search_outfit(
                _plan(items=[BROWN_BELT])
            )
        )

    assert results[0]["status"] == "unsupported_category"
    assert results[0]["products"] == []
    assert results[0]["search_params"] is None
    assert fake.search_calls == []

    mock_client_cls.assert_not_called()


def test_unsupported_item_does_not_erase_other_results():
    fake = CategoryAwareFakeClient(
        {"shirts": [SHIRT_PRODUCT]}
    )

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(
                _plan(
                    items=[
                        BLACK_SHIRT,
                        BROWN_BELT,
                    ]
                )
            )
        )

    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "unsupported_category"

    assert len(fake.search_calls) == 1


# ===========================================================================
# Duplicate labels
# ===========================================================================

def test_duplicate_items_keep_separate_entries():
    fake = CategoryAwareFakeClient(
        {"shirts": [SHIRT_PRODUCT]}
    )

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(
                _plan(
                    items=[
                        BLACK_SHIRT,
                        BLACK_SHIRT,
                    ]
                )
            )
        )

    assert [r["index"] for r in results] == [0, 1]

    assert all(
        len(r["products"]) == 1
        for r in results
    )

    assert len(fake.search_calls) == 2


# ===========================================================================
# Budget forwarding
# ===========================================================================

def test_plan_budget_is_forwarded_to_every_search():
    fake = CategoryAwareFakeClient(
        {
            "shirts": [SHIRT_PRODUCT],
            "pants": [PANTS_PRODUCT],
        }
    )

    with _patched(fake):
        _run(
            ShoppingAgent().search_outfit(
                _plan(
                    items=[
                        BLACK_SHIRT,
                        BEIGE_CHINOS,
                    ],
                    budget=5000,
                )
            )
        )

    assert [c["budget"] for c in fake.search_calls] == [
        5000,
        5000,
    ]


@pytest.mark.parametrize(
    "budget",
    [None, 0],
)
def test_missing_or_zero_budget_is_not_forwarded(
    budget: Optional[float],
):
    fake = CategoryAwareFakeClient(
        {"shirts": [SHIRT_PRODUCT]}
    )

    with _patched(fake):
        _run(
            ShoppingAgent().search_outfit(
                _plan(
                    items=[BLACK_SHIRT],
                    budget=budget,
                )
            )
        )

    assert fake.search_calls[0]["budget"] is None


# ===========================================================================
# Size handling
# ===========================================================================

def test_sizes_apply_only_to_their_category():
    fake = CategoryAwareFakeClient(
        {
            "shirts": [SHIRT_PRODUCT],
            "pants": [PANTS_PRODUCT],
        }
    )

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(
                _plan(
                    items=[
                        BLACK_SHIRT,
                        BEIGE_CHINOS,
                    ]
                ),
                sizes={"shirts": "M"},
            )
        )

    assert fake.availability_calls == [
        {
            "product_id": "MOCK001",
            "size": "M",
        }
    ]

    assert len(results[0]["products"]) == 1

    # Pants has no requested size.
    assert len(results[1]["products"]) == 1


def test_size_not_listed_is_excluded_without_availability_call():
    fake = CategoryAwareFakeClient(
        {"shirts": [SHIRT_PRODUCT]}
    )

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(
                _plan(items=[BLACK_SHIRT]),
                sizes={"shirts": "XXXL"},
            )
        )

    assert results[0]["products"] == []
    assert results[0]["status"] == "no_results"
    assert fake.availability_calls == []


# ===========================================================================
# 8. Empty results
# ===========================================================================

def test_empty_results_have_no_results_status():
    fake = CategoryAwareFakeClient({})

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(
                _plan(items=[BLACK_SHIRT])
            )
        )

    assert results[0]["status"] == "no_results"
    assert results[0]["products"] == []


# ===========================================================================
# 9 & 10. MCP errors propagate
# ===========================================================================

def test_outfit_search_propagates_connection_error():
    fake = CategoryAwareFakeClient(
        {},
        connect_error=MCPConnectionError("down"),
    )

    with _patched(fake):
        with pytest.raises(MCPConnectionError):
            _run(
                ShoppingAgent().search_outfit(
                    _plan(items=[BLACK_SHIRT])
                )
            )


def test_outfit_search_propagates_tool_error():
    fake = CategoryAwareFakeClient(
        {},
        search_error=MCPToolError(
            "search_products",
            "boom",
        ),
    )

    with _patched(fake):
        with pytest.raises(MCPToolError):
            _run(
                ShoppingAgent().search_outfit(
                    _plan(items=[BLACK_SHIRT])
                )
            )


# ===========================================================================
# 11-13. Metadata and URLs preserved
# ===========================================================================

def test_outfit_search_preserves_metadata_and_urls():
    fake = CategoryAwareFakeClient(
        {
            "shirts": [SHIRT_PRODUCT],
            "shoes": [SHOES_PRODUCT],
        }
    )

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(
                _plan(
                    items=[
                        BLACK_SHIRT,
                        BROWN_LOAFERS,
                    ]
                )
            )
        )

    shirt = results[0]["products"][0]

    for key, value in SHIRT_PRODUCT.items():
        assert shirt[key] == value

    shoe = results[1]["products"][0]

    assert shoe["image_url"] is None

    assert (
        shoe["product_url"]
        == SHOES_PRODUCT["product_url"]
    )


# ===========================================================================
# 15. Deterministic results
# ===========================================================================

def test_outfit_search_is_deterministic():
    def run_once():
        fake = CategoryAwareFakeClient(
            {
                "shirts": [
                    SHIRT_PRODUCT,
                    NO_IMAGE_PRODUCT,
                ]
            }
        )

        with _patched(fake):
            return _run(
                ShoppingAgent().search_outfit(
                    _plan(items=[BLACK_SHIRT])
                )
            )

    first = run_once()
    second = run_once()

    assert [
        p["product_id"]
        for p in first[0]["products"]
    ] == [
        p["product_id"]
        for p in second[0]["products"]
    ]


# ===========================================================================
# Dict plans
# ===========================================================================

def test_outfit_search_accepts_plan_as_dict():
    fake = CategoryAwareFakeClient(
        {"shirts": [SHIRT_PRODUCT]}
    )

    plan = _plan(
        items=[BLACK_SHIRT]
    ).model_dump()

    with _patched(fake):
        results = _run(
            ShoppingAgent().search_outfit(plan)
        )

    assert results[0]["status"] == "ok"


# ===========================================================================
# PART 41 — SELECT ONE PRODUCT PER OUTFIT ITEM
# ===========================================================================

def _entry(
    index: int,
    products: List[Dict[str, Any]],
    status: str = "ok",
    item: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a hand-made search_outfit() entry for testing select_outfit()
    without any MCP client.
    """
    return {
        "index": index,
        "source": "items",
        "item": item or {"category": "x", "item": "x"},
        "search_params": None,
        "status": status,
        "products": products,
    }


# ===========================================================================
# 1. Complete outfit: one product per item, total = sum of real prices
# ===========================================================================

def test_complete_outfit_selects_one_product_per_item():
    fake = CategoryAwareFakeClient(
        {
            "shirts": [SHIRT_PRODUCT],
            "pants": [PANTS_PRODUCT],
            "shoes": [SHOES_PRODUCT],
        }
    )

    plan = _plan(
        items=[
            BLACK_SHIRT,
            BEIGE_CHINOS,
            BROWN_LOAFERS,
        ]
    )

    with _patched(fake):
        outfit = _run(
            ShoppingAgent().build_outfit(plan)
        )

    assert outfit["status"] == "complete"
    assert outfit["missing_items"] == []

    assert [
        p["product_id"]
        for p in outfit["selected_products"]
    ] == [
        "MOCK001",
        "MOCK014",
        "MOCK027",
    ]

    assert outfit["total_price"] == 1299.0 + 1399.0 + 1899.0


# ===========================================================================
# 2. Multiple candidates: the first (highest-ranked) one is selected
# ===========================================================================

def test_first_ranked_candidate_is_selected():
    cheaper_second = dict(
        SHIRT_PRODUCT,
        product_id="MOCK999",
        price=100.0,
    )

    outfit = select_outfit(
        [_entry(0, [SHIRT_PRODUCT, cheaper_second])]
    )

    assert outfit["selected_products"][0]["product_id"] == "MOCK001"
    assert outfit["total_price"] == 1299.0


def test_best_ranked_candidate_from_real_ranking_is_selected():
    # The navy shirt is returned first, but the request is for black:
    # the ranker moves the black shirt to the top.
    fake = CategoryAwareFakeClient(
        {"shirts": [NAVY_SHIRT_PRODUCT, SHIRT_PRODUCT]}
    )

    with _patched(fake):
        outfit = _run(
            ShoppingAgent().build_outfit(
                _plan(items=[BLACK_SHIRT])
            )
        )

    assert outfit["selected_products"][0]["product_id"] == "MOCK001"


# ===========================================================================
# 3. Empty candidates: nothing invented, explicitly incomplete
# ===========================================================================

def test_empty_candidates_make_outfit_incomplete():
    fake = CategoryAwareFakeClient(
        {"shirts": [SHIRT_PRODUCT]}
    )

    with _patched(fake):
        outfit = _run(
            ShoppingAgent().build_outfit(
                _plan(
                    items=[
                        BLACK_SHIRT,
                        BEIGE_CHINOS,
                    ]
                )
            )
        )

    assert outfit["status"] == "incomplete"

    assert [
        p["product_id"]
        for p in outfit["selected_products"]
    ] == ["MOCK001"]

    assert outfit["missing_items"][0]["status"] == "no_results"
    assert outfit["missing_items"][0]["index"] == 1

    assert outfit["total_price"] == 1299.0


# ===========================================================================
# 4. Unsupported category: nothing invented
# ===========================================================================

def test_unsupported_category_is_reported_and_not_invented():
    fake = CategoryAwareFakeClient(
        {"shirts": [SHIRT_PRODUCT]}
    )

    with _patched(fake):
        outfit = _run(
            ShoppingAgent().build_outfit(
                _plan(
                    items=[
                        BLACK_SHIRT,
                        BROWN_BELT,
                    ]
                )
            )
        )

    assert outfit["status"] == "incomplete"
    assert len(outfit["selected_products"]) == 1

    assert outfit["missing_items"][0]["status"] == "unsupported_category"
    assert outfit["missing_items"][0]["index"] == 1


# ===========================================================================
# 5. Accessories are treated as normal outfit items
# ===========================================================================

def test_accessories_are_included_in_selection():
    fake = CategoryAwareFakeClient(
        {
            "shirts": [SHIRT_PRODUCT],
            "watches": [WATCH_PRODUCT],
        }
    )

    plan = _plan(
        items=[BLACK_SHIRT],
        accessories=[SILVER_WATCH],
    )

    with _patched(fake):
        outfit = _run(
            ShoppingAgent().build_outfit(plan)
        )

    assert outfit["status"] == "complete"

    assert [
        p["category"]
        for p in outfit["selected_products"]
    ] == ["shirts", "watches"]

    assert outfit["total_price"] == 1299.0 + 1999.0


# ===========================================================================
# 6. total_price comes from the selected products' actual prices
# ===========================================================================

def test_total_price_is_sum_of_selected_prices():
    a = dict(SHIRT_PRODUCT, product_id="A", price=100.5)
    b = dict(PANTS_PRODUCT, product_id="B", price=200.25)

    outfit = select_outfit(
        [
            _entry(0, [a]),
            _entry(1, [b]),
        ]
    )

    assert outfit["total_price"] == 300.75
    assert isinstance(outfit["total_price"], float)


# ===========================================================================
# 7. Deterministic
# ===========================================================================

def test_build_outfit_is_deterministic():
    def run_once():
        fake = CategoryAwareFakeClient(
            {
                "shirts": [
                    SHIRT_PRODUCT,
                    NO_IMAGE_PRODUCT,
                ],
                "pants": [PANTS_PRODUCT],
            }
        )

        with _patched(fake):
            return _run(
                ShoppingAgent().build_outfit(
                    _plan(
                        items=[
                            BLACK_SHIRT,
                            BEIGE_CHINOS,
                        ]
                    )
                )
            )

    assert run_once() == run_once()


# ===========================================================================
# 8. Selected IDs and categories come straight from the candidates
# ===========================================================================

def test_selected_ids_and_categories_match_candidates():
    fake = CategoryAwareFakeClient(
        {
            "shirts": [SHIRT_PRODUCT],
            "pants": [PANTS_PRODUCT],
        }
    )

    with _patched(fake):
        outfit = _run(
            ShoppingAgent().build_outfit(
                _plan(
                    items=[
                        BLACK_SHIRT,
                        BEIGE_CHINOS,
                    ]
                )
            )
        )

    candidate_ids = {
        SHIRT_PRODUCT["product_id"],
        PANTS_PRODUCT["product_id"],
    }

    assert {
        p["product_id"]
        for p in outfit["selected_products"]
    } <= candidate_ids

    assert [
        p["category"]
        for p in outfit["selected_products"]
    ] == ["shirts", "pants"]

    assert [
        p["item_index"]
        for p in outfit["selected_products"]
    ] == [0, 1]


# ===========================================================================
# 9. No additional MCP search
# ===========================================================================

def test_build_outfit_makes_exactly_one_search_per_item():
    fake = CategoryAwareFakeClient(
        {
            "shirts": [SHIRT_PRODUCT],
            "pants": [PANTS_PRODUCT],
            "shoes": [SHOES_PRODUCT],
        }
    )

    with _patched(fake):
        _run(
            ShoppingAgent().build_outfit(
                _plan(
                    items=[
                        BLACK_SHIRT,
                        BEIGE_CHINOS,
                        BROWN_LOAFERS,
                    ]
                )
            )
        )

    assert len(fake.search_calls) == 3


def test_select_outfit_never_touches_mcp():
    fake = CategoryAwareFakeClient({})

    with _patched(fake) as mock_client_cls:
        select_outfit(
            [_entry(0, [SHIRT_PRODUCT])]
        )

    mock_client_cls.assert_not_called()
    assert fake.search_calls == []


# ===========================================================================
# Extra: an empty plan is not a complete outfit
# ===========================================================================

def test_empty_plan_is_incomplete():
    fake = CategoryAwareFakeClient({})

    with _patched(fake):
        outfit = _run(
            ShoppingAgent().build_outfit(_plan())
        )

    assert outfit["status"] == "incomplete"
    assert outfit["selected_products"] == []
    assert outfit["total_price"] == 0.0


# ===========================================================================
# Extra: MCP errors still propagate through build_outfit
# ===========================================================================

def test_build_outfit_propagates_mcp_errors():
    fake = CategoryAwareFakeClient(
        {},
        search_error=MCPToolError(
            "search_products",
            "boom",
        ),
    )

    with _patched(fake):
        with pytest.raises(MCPToolError):
            _run(
                ShoppingAgent().build_outfit(
                    _plan(items=[BLACK_SHIRT])
                )
            )