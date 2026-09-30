"""
Shopping Agent.

Provides a clean, application-level interface for fashion product discovery.

Architecture:

    Caller
        |
        v
    ShoppingAgent
        |
        v
    MCPShoppingClient
        |
        v
    MCP shopping tools
        |
        v
    Product data source
        |
        v
    Product Ranker

This module's only shopping-data dependency is MCPShoppingClient.

The agent does not access product storage directly, does not read catalog
files, does not call MCP server internals, and does not call an LLM.

Product fields are passed through without fabrication. In particular,
image_url and product_url are preserved independently exactly as returned
by the MCP client.

Part 40: search_outfit() takes the Stylist Agent's OutfitPlan and searches
each outfit item independently through the same MCP client.

Part 41: select_outfit() / build_outfit() pick the top-ranked candidate for
each outfit item and return one complete outfit, without any extra search.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from backend.schemas.outfit import OutfitItem, OutfitPlan
from backend.shopping.mcp_client import MCPShoppingClient
from backend.shopping.product_normalizer import Product
from backend.shopping.product_ranker import rank_products


# ---------------------------------------------------------------------------
# Category / color vocabulary
# ---------------------------------------------------------------------------

# Every value on the right must be a category that exists in the catalog.
_CATEGORY_ALIASES: Dict[str, str] = {
    "t-shirt": "t-shirts",
    "tshirt": "t-shirts",
    "t-shirts": "t-shirts",
    "tee": "t-shirts",

    "shirt": "shirts",
    "shirts": "shirts",

    "top": "tops",
    "tops": "tops",

    "trouser": "pants",
    "trousers": "pants",
    "pant": "pants",
    "pants": "pants",

    "jean": "jeans",
    "jeans": "jeans",

    "skirt": "skirts",
    "skirts": "skirts",

    "dress": "dresses",
    "dresses": "dresses",

    "shoe": "shoes",
    "shoes": "shoes",

    "watch": "watches",
    "watches": "watches",

    "sunglass": "sunglasses",
    "sunglasses": "sunglasses",

    "bag": "bags",
    "bags": "bags",

    "accessory": "accessories",
    "accessories": "accessories",

    # Part 40 additions (each maps to an existing catalog category)
    "chino": "pants",
    "chinos": "pants",
    "sneaker": "shoes",
    "sneakers": "shoes",
    "loafer": "shoes",
    "loafers": "shoes",
    "sandal": "shoes",
    "sandals": "shoes",
    "heels": "shoes",
    "boots": "shoes",
    "footwear": "shoes",
    "blouse": "tops",
    "handbag": "bags",
    "clutch": "bags",
    "necklace": "accessories",
    "earring": "accessories",
    "earrings": "accessories",
}

# Broad buckets: when the stylist's category resolves to one of these, the
# item description may refine it (e.g. "accessory" + "silver watch" -> watches).
_GENERIC_CATEGORIES = frozenset({"tops", "accessories"})


_COLOR_VOCABULARY = (
    "black",
    "white",
    "navy",
    "cream",
    "brown",
    "teal",
    "maroon",
    "beige",
    "olive",
    "grey",
    "gray",
    "pink",
    "red",
    "gold",
    "silver",
    "blue",
)

# Spelling variants -> the catalog's spelling.
_COLOR_ALIASES: Dict[str, str] = {
    "gray": "grey",
    "navy blue": "navy",
}

_KNOWN_COLORS = frozenset(_COLOR_ALIASES.get(c, c) for c in _COLOR_VOCABULARY)

_WORD_PATTERN = re.compile(r"[a-z][a-z\-]*")


# ---------------------------------------------------------------------------
# Natural-language requirement extraction (existing behaviour)
# ---------------------------------------------------------------------------

# A budget is recognized when accompanied by a currency symbol or an
# explicit budget-related trigger word.
_BUDGET_PATTERN = re.compile(
    r"(?:under|below|within|less than|budget of|budget)\s*[₹$]?\s*(\d[\d,]*)"
    r"|[₹$]\s*(\d[\d,]*)",
    re.IGNORECASE,
)


_SIZE_PATTERN = re.compile(
    r"\bsize\s+([a-zA-Z0-9]+)\b",
    re.IGNORECASE,
)


def extract_requirements(request_text: str) -> Dict[str, Any]:
    """
    Deterministically extract shopping requirements from natural language.

    Example:

        "I need a black shirt under ₹1500, size M"

    Returns:

        {
            "query": "...",
            "category": "shirts",
            "color": "black",
            "budget": 1500.0,
            "size": "M",
        }

    Nothing is guessed when a signal is absent.
    """

    text = (request_text or "").strip()
    lowered = text.lower()

    category = next(
        (
            canonical
            for alias, canonical in _CATEGORY_ALIASES.items()
            if alias in lowered
        ),
        None,
    )

    color = next(
        (
            color_name
            for color_name in _COLOR_VOCABULARY
            if color_name in lowered
        ),
        None,
    )

    budget: Optional[float] = None

    budget_match = _BUDGET_PATTERN.search(lowered)

    if budget_match:
        raw_amount = budget_match.group(1) or budget_match.group(2)
        budget = float(raw_amount.replace(",", ""))

    size_match = _SIZE_PATTERN.search(lowered)

    size = size_match.group(1).upper() if size_match else None

    return {
        "query": text,
        "category": category,
        "color": color,
        "budget": budget,
        "size": size,
    }


# ---------------------------------------------------------------------------
# Stylist item -> shopping requirements (Part 40)
# ---------------------------------------------------------------------------


def _category_from_text(text: Optional[str]) -> Optional[str]:
    """
    Whole-word category lookup. When several words match, the LAST one wins
    (the head noun in English: "shirt dress" -> dresses).
    """
    if not text:
        return None

    lowered = re.sub(r"\bt\s+shirts?\b", "t-shirt", text.lower())

    match: Optional[str] = None
    for word in _WORD_PATTERN.findall(lowered):
        canonical = _CATEGORY_ALIASES.get(word.strip("-"))
        if canonical is not None:
            match = canonical

    return match


def resolve_item_category(item: OutfitItem) -> Optional[str]:
    """
    Map a stylist OutfitItem to a catalog category, or None if unsupported.

    The stylist's own category wins unless it is a broad bucket
    ("tops", "accessories") or unrecognised, in which case the item
    description is consulted. Nothing is guessed: no match -> None.
    """
    from_category = _category_from_text(item.category)

    if from_category is not None and from_category not in _GENERIC_CATEGORIES:
        return from_category

    from_item = _category_from_text(item.item)

    return from_item if from_item is not None else from_category


def normalize_color(color: Optional[str]) -> Optional[str]:
    """Return the catalog spelling of a known color, else None (no guessing)."""
    if not color:
        return None

    cleaned = " ".join(color.lower().split())
    cleaned = _COLOR_ALIASES.get(cleaned, cleaned)

    return cleaned if cleaned in _KNOWN_COLORS else None


# Per-item statuses returned by search_outfit()
STATUS_OK = "ok"
STATUS_NO_RESULTS = "no_results"
STATUS_UNSUPPORTED = "unsupported_category"


# ---------------------------------------------------------------------------
# Complete-outfit selection (Part 41)
# ---------------------------------------------------------------------------

# Overall outfit statuses returned by select_outfit() / build_outfit()
OUTFIT_COMPLETE = "complete"
OUTFIT_INCOMPLETE = "incomplete"


def select_outfit(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Select ONE product per outfit item from search_outfit() results.

    Pure function: no MCP call, no search. Every selected product is the
    first (highest-ranked) candidate of its own outfit item, in the same
    order as the input.

    Returns:

        {
            "status": "complete" | "incomplete",
            "selected_products": [
                {"product_id": "...", "category": "...", "item_index": 0},
            ],
            "total_price": 4597.0,       # sum of the selected products' real prices
            "missing_items": [           # empty when complete
                {"index": 2, "item": {...}, "status": "no_results"
                                                     | "unsupported_category"},
            ],
        }

    An outfit is "complete" only when EVERY outfit item has a selected
    product. Items with no candidates (no_results / unsupported_category)
    are reported in missing_items; nothing is invented for them, and
    total_price then covers only the products that were selected.
    An outfit with no items at all is "incomplete".
    """

    selected: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    total = 0.0

    for entry in candidates:

        products = entry.get("products") or []

        if not products:
            missing.append(
                {
                    "index": entry.get("index"),
                    "item": entry.get("item"),
                    "status": entry.get("status"),
                }
            )
            continue

        best = products[0]

        selected.append(
            {
                "product_id": best["product_id"],
                "category": best["category"],
                "item_index": entry.get("index"),
            }
        )

        total += float(best["price"])

    is_complete = bool(candidates) and not missing

    return {
        "status": OUTFIT_COMPLETE if is_complete else OUTFIT_INCOMPLETE,
        "selected_products": selected,
        "total_price": round(total, 2),
        "missing_items": missing,
    }


# ---------------------------------------------------------------------------
# Shopping Agent
# ---------------------------------------------------------------------------


class ShoppingAgent:
    """
    Application-level shopping agent.

    All shopping data is obtained through MCPShoppingClient.

    The agent:
      - forwards search requirements to the MCP client
      - optionally verifies size-specific availability
      - converts returned product dictionaries into Product models
      - uses the existing product ranker
      - preserves product metadata
      - never fabricates image or product URLs
      - propagates MCP infrastructure errors unchanged
    """

    async def _search_with_client(
        self,
        client: Any,
        *,
        query: str = "",
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        size: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search, size-filter and rank using an already-connected client.

        MCPConnectionError and MCPToolError are intentionally not caught.
        """

        raw_products = await client.search_products(
            query=query,
            budget=budget,
            category=category,
            color=color,
        )

        if not raw_products:
            return []

        products = [
            Product.model_validate(raw_product)
            for raw_product in raw_products
        ]

        # -------------------------------------------------------------------
        # Size-specific availability filtering
        # -------------------------------------------------------------------

        if size:
            requested_size = size.strip().lower()

            size_confirmed: List[Product] = []

            for product in products:

                has_size = any(
                    available_size.strip().lower() == requested_size
                    for available_size in product.sizes
                )

                # Do not call availability when the product does not
                # even advertise the requested size.
                if not has_size:
                    continue

                availability = await client.check_availability(
                    product.product_id,
                    size=size,
                )

                if availability.get("available") is True:
                    size_confirmed.append(product)

            products = size_confirmed

        # -------------------------------------------------------------------
        # Rank with the existing deterministic ranker.
        # -------------------------------------------------------------------

        requirements = {
            "category": category,
            "color": color,
            "budget": budget,
        }

        ranked = rank_products(
            products,
            requirements,
        )

        return [
            product.model_dump()
            for product in ranked
        ]

    async def search(
        self,
        query: str = "",
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        size: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for products matching the supplied requirements.

        When a specific size is requested, a product must:

        1. contain that size in its sizes list, and
        2. be confirmed available for that size through MCP.

        A missing requested size is rejected without making an unnecessary
        availability call.

        MCPConnectionError and MCPToolError are intentionally not caught.
        """

        async with MCPShoppingClient() as client:
            return await self._search_with_client(
                client,
                query=query,
                budget=budget,
                category=category,
                color=color,
                size=size,
            )

    async def search_outfit(
        self,
        outfit_plan: Union[OutfitPlan, Dict[str, Any]],
        sizes: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search products for every item in a Stylist Agent OutfitPlan.

        Both plan.items and plan.accessories are searched, in that order,
        each item independently (never combined into one query).

        Args:
            outfit_plan: An OutfitPlan, or its dict form (e.g. from agent
                state).
            sizes: Optional requested size per CATALOG category, e.g.
                {"shirts": "M", "shoes": "8"}. OutfitPlan carries no size,
                so no size filtering happens unless this is given.

        Returns one entry per outfit item, in order:

            {
                "index": 0,                  # stable position; labels may repeat
                "source": "items",           # or "accessories"
                "item": {...},               # the OutfitItem, unchanged
                "search_params": {...},      # what was sent, or None if unsupported
                "status": "ok" | "no_results" | "unsupported_category",
                "products": [...],           # ranked product dicts
            }

        Items whose category is not in the catalog are NOT searched (no
        unfiltered or color-only search); they come back as
        "unsupported_category" with no products.

        The plan's budget is applied to every item as an upper price bound.
        A budget of None or 0 means no budget.

        MCPConnectionError and MCPToolError are not caught. If one item's
        search fails, the exception propagates and the whole call fails.
        """

        plan = (
            outfit_plan
            if isinstance(outfit_plan, OutfitPlan)
            else OutfitPlan.model_validate(outfit_plan)
        )

        budget = plan.budget if plan.budget and plan.budget > 0 else None

        outfit_items = [("items", item) for item in plan.items] + [
            ("accessories", item) for item in plan.accessories
        ]

        entries: List[Dict[str, Any]] = []

        for index, (source, item) in enumerate(outfit_items):

            category = resolve_item_category(item)

            entry: Dict[str, Any] = {
                "index": index,
                "source": source,
                "item": item.model_dump(),
                "search_params": None,
                "status": STATUS_UNSUPPORTED,
                "products": [],
            }

            if category is not None:
                entry["search_params"] = {
                    "category": category,
                    "color": normalize_color(item.color),
                    "budget": budget,
                    "size": (sizes or {}).get(category),
                }

            entries.append(entry)

        searchable = [e for e in entries if e["search_params"] is not None]

        # Nothing to search: do not even open an MCP connection.
        if not searchable:
            return entries

        async with MCPShoppingClient() as client:

            for entry in searchable:

                params = entry["search_params"]

                products = await self._search_with_client(
                    client,
                    query="",
                    budget=params["budget"],
                    category=params["category"],
                    color=params["color"],
                    size=params["size"],
                )

                entry["products"] = products
                entry["status"] = STATUS_OK if products else STATUS_NO_RESULTS

        return entries

    async def build_outfit(
        self,
        outfit_plan: Union[OutfitPlan, Dict[str, Any]],
        sizes: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Part 41: one product per outfit item, as one outfit.

        Runs the Part 40 search once (search_outfit), then selects the
        top-ranked candidate of each item. No additional search is made.
        MCP errors propagate exactly as in search_outfit().
        """

        candidates = await self.search_outfit(outfit_plan, sizes=sizes)

        return select_outfit(candidates)

    async def find_products(
        self,
        request_text: str,
    ) -> List[Dict[str, Any]]:
        """
        Convenience entry point for natural-language shopping requests.

        Example:

            "I need a black shirt under ₹1500, size M"

        Requirements are extracted deterministically and forwarded to search.
        """

        requirements = extract_requirements(request_text)

        return await self.search(
            query=requirements["query"],
            budget=requirements["budget"],
            category=requirements["category"],
            color=requirements["color"],
            size=requirements["size"],
        )

    async def get_product(
        self,
        product_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Look up a single product through MCP.

        Returns None when the client reports that the product does not exist.
        """

        async with MCPShoppingClient() as client:
            result = await client.get_product(product_id)

        if not result:
            return None

        # MCPShoppingClient may return either:
        #
        #   {"found": True, "product": {...}}
        #
        # or directly a product dictionary depending on its implementation.
        #
        # Support the documented wrapped response without fabricating data.

        if "found" in result:
            if not result.get("found"):
                return None

            return result.get("product")

        return result

    async def get_variants(
        self,
        product_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Return variant products through MCP.
        """

        async with MCPShoppingClient() as client:
            variants = await client.get_variants(product_id)

        return variants or []

    async def get_alternatives(
        self,
        product_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Return alternative products through MCP.
        """

        async with MCPShoppingClient() as client:
            alternatives = await client.get_alternatives(
                product_id,
                limit=limit,
            )

        return alternatives or []