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
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from backend.shopping.mcp_client import MCPShoppingClient
from backend.shopping.product_normalizer import Product
from backend.shopping.product_ranker import rank_products


# ---------------------------------------------------------------------------
# Natural-language requirement extraction
# ---------------------------------------------------------------------------

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
}


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

            # ---------------------------------------------------------------
            # Size-specific availability filtering
            # ---------------------------------------------------------------

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

        # ---------------------------------------------------------------
        # Rank products after MCP operations are complete.
        # ---------------------------------------------------------------

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