"""
Fitting Room Backend.

Part 42
-------

Builds a backend payload for the future fitting-room frontend.

Responsibilities:
    - receive the stylist's OutfitPlan
    - use ShoppingAgent to find the real products
    - select the complete outfit
    - attach the mannequin asset
    - expose selected product metadata
    - expose retailer/product URLs
    - optionally expose real product variants/colors
    - return a frontend-independent JSON-compatible structure

This module DOES NOT:
    - generate a human avatar
    - generate a face
    - perform VTON
    - generate a 3D model
    - modify mannequin images
    - render clothing onto the mannequin
    - call an LLM

The future Next.js frontend will consume this response.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from backend.agents.shopping_agent import ShoppingAgent
from backend.schemas.outfit import OutfitPlan


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FITTING_ROOM_ASSET_DIR = Path("assets") / "fitting-room"

MANNEQUIN_ASSETS = {
    "female": FITTING_ROOM_ASSET_DIR / "female-mannequin.png",
    "male": FITTING_ROOM_ASSET_DIR / "male-mannequin.png",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def mannequin_asset_path(mannequin: str) -> str:
    """
    Return the frontend-facing asset path for a mannequin.

    No gender is guessed.
    """

    normalized = (mannequin or "").strip().lower()

    if normalized not in MANNEQUIN_ASSETS:
        raise ValueError(
            "Unsupported mannequin. Expected 'female' or 'male'."
        )

    return f"/assets/fitting-room/{normalized}-mannequin.png"


def _product_payload(
    product: Dict[str, Any],
    *,
    item_index: Optional[int],
    category: Optional[str],
    color_variants: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Convert a product returned by ShoppingAgent into a frontend-safe
    fitting-room product payload.

    Product values are passed through from the shopping layer.
    Nothing is fabricated.
    """

    return {
        "item_index": item_index,
        "product_id": product.get("product_id"),
        "category": category or product.get("category"),
        "store": product.get("store"),
        "brand": product.get("brand"),
        "title": product.get("title"),
        "color": product.get("color"),
        "price": product.get("price"),
        "currency": product.get("currency"),
        "sizes": product.get("sizes") or [],
        "image_url": product.get("image_url"),
        "product_url": product.get("product_url"),
        "color_variants": color_variants or [],
    }


def _variant_payload(variant: Dict[str, Any]) -> Dict[str, Any]:
    """
    Preserve useful variant information without inventing fields.
    """

    return {
        "product_id": variant.get("product_id"),
        "store": variant.get("store"),
        "brand": variant.get("brand"),
        "title": variant.get("title"),
        "category": variant.get("category"),
        "color": variant.get("color"),
        "price": variant.get("price"),
        "currency": variant.get("currency"),
        "image_url": variant.get("image_url"),
        "product_url": variant.get("product_url"),
        "sizes": variant.get("sizes") or [],
        "availability": variant.get("availability"),
    }


# ---------------------------------------------------------------------------
# Fitting Room Service
# ---------------------------------------------------------------------------


class FittingRoomService:
    """
    Backend service responsible for preparing fitting-room data.

    The service is intentionally presentation-independent.

    The future frontend can use the returned payload for:

        - mannequin display
        - product cards
        - color selectors
        - price display
        - retailer links
        - animations
        - 3D transitions
        - camera rotation
        - outfit switching
    """

    def __init__(
        self,
        shopping_agent: Optional[ShoppingAgent] = None,
    ) -> None:
        self.shopping_agent = shopping_agent or ShoppingAgent()

    async def build(
        self,
        outfit_plan: Union[OutfitPlan, Dict[str, Any]],
        *,
        mannequin: str,
        sizes: Optional[Dict[str, str]] = None,
        include_variants: bool = True,
    ) -> Dict[str, Any]:
        """
        Build a complete fitting-room payload.

        Args:
            outfit_plan:
                OutfitPlan produced by the Stylist Agent.

            mannequin:
                "female" or "male".

            sizes:
                Optional category -> requested size mapping.

            include_variants:
                If True, retrieve variants for each selected product.

        Returns:
            JSON-compatible fitting-room payload.
        """

        mannequin_path = mannequin_asset_path(mannequin)

        # ---------------------------------------------------------------
        # Part 40: search each outfit item independently.
        # ---------------------------------------------------------------

        candidates = await self.shopping_agent.search_outfit(
            outfit_plan,
            sizes=sizes,
        )

        # ---------------------------------------------------------------
        # Part 41: select one product per outfit item.
        # ---------------------------------------------------------------

        selection = self.shopping_agent

        # We intentionally select from the already returned candidates.
        from backend.agents.shopping_agent import select_outfit

        selected = select_outfit(candidates)

        # ---------------------------------------------------------------
        # Build rich product payload.
        # ---------------------------------------------------------------

        products_by_index: Dict[int, Dict[str, Any]] = {}

        for entry in candidates:
            index = entry.get("index")
            products = entry.get("products") or []

            if products and index is not None:
                products_by_index[index] = products[0]

        fitting_items: List[Dict[str, Any]] = []

        for selected_product in selected["selected_products"]:
            item_index = selected_product.get("item_index")

            if item_index is None:
                continue

            product = products_by_index.get(item_index)

            if product is None:
                continue

            variants: List[Dict[str, Any]] = []

            if include_variants:
                raw_variants = await self.shopping_agent.get_variants(
                    product["product_id"]
                )

                variants = [
                    _variant_payload(variant)
                    for variant in raw_variants
                    if isinstance(variant, dict)
                ]

            fitting_items.append(
                _product_payload(
                    product,
                    item_index=item_index,
                    category=selected_product.get("category"),
                    color_variants=variants,
                )
            )

        # ---------------------------------------------------------------
        # Missing outfit items.
        # ---------------------------------------------------------------

        missing_items = selected.get("missing_items") or []

        return {
            "version": "42",
            "mannequin": {
                "type": mannequin.strip().lower(),
                "image_url": mannequin_path,
            },
            "outfit": {
                "status": selected["status"],
                "total_price": selected["total_price"],
                "currency": self._detect_currency(fitting_items),
                "selected_count": len(fitting_items),
                "expected_count": len(candidates),
            },
            "items": fitting_items,
            "missing_items": missing_items,
        }

    @staticmethod
    def _detect_currency(
        items: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Return the currency when available.

        If products have inconsistent or missing currencies,
        return None rather than guessing.
        """

        currencies = {
            item.get("currency")
            for item in items
            if item.get("currency")
        }

        if len(currencies) == 1:
            return next(iter(currencies))

        return None