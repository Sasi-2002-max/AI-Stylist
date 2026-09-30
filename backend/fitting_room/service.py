"""
Fitting Room Service (Parts 42-43).

Resolves Part 41's already-selected outfit into frontend-friendly fitting-
room data: a mannequin reference plus each selected item's real product,
color variations, and alternatives.

Architecture:

    ShoppingAgent.build_outfit()   (Part 41 -- already run elsewhere)
              v
    FittingRoomService.prepare_fitting_room()      <-- this file
              v
    ShoppingAgent.get_product() / get_variants() / get_alternatives()
              v
    MCPShoppingClient
              v
    FittingRoomResponse

Part 43 -- product visual source:
    THE SELECTED RETAILER PRODUCT IS THE SOURCE OF TRUTH.
    The visual for each item is the real product's own image_url, exactly
    as returned by ShoppingAgent.get_product(). If the product has no
    image, image_url stays None -- no image is ever fabricated, and there
    is no separate visual/fashion catalog.

This service performs NO product search of its own: it never calls
ShoppingAgent.search(), search_outfit(), or find_products(). It only
resolves the product IDs Part 41 already selected, via get_product(),
optionally get_variants(), and optionally get_alternatives().

It never imports MockStore, any store adapter, or anything from
mcp_server -- its only shopping-data dependency is ShoppingAgent, which
itself talks only to MCPShoppingClient.

MCPConnectionError and MCPToolError raised while resolving a product are
never caught or converted into empty/fake data; they propagate to the
caller unchanged, exactly as in the existing ShoppingAgent conventions.
A product that MCP genuinely cannot find (not an infrastructure failure)
is reported per-item as {"error": "product_not_found"}, never invented.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from backend.agents.shopping_agent import ShoppingAgent
from backend.fitting_room.schemas import (
    ColorVariation,
    FittingRoomItem,
    FittingRoomMannequin,
    FittingRoomProduct,
    FittingRoomResponse,
    MannequinGender,
    OutfitSummary,
)

FITTING_ROOM_READY = "ready"
FITTING_ROOM_INCOMPLETE = "incomplete"

PRODUCT_NOT_FOUND_ERROR = "product_not_found"
VISUAL_SOURCE_PRODUCT_IMAGE = "product_image"

_MANNEQUIN_ASSETS: Dict[MannequinGender, str] = {
    MannequinGender.FEMALE: "assets/fitting-room/female-mannequin.png",
    MannequinGender.MALE: "assets/fitting-room/male-mannequin.png",
}


class FittingRoomError(Exception):
    """Base class for Fitting Room service errors."""


class InvalidMannequinGenderError(FittingRoomError):
    """Raised when an unsupported mannequin gender is requested."""


def resolve_mannequin(mannequin_gender: Union[str, MannequinGender]) -> FittingRoomMannequin:
    """
    Validate a mannequin gender and resolve it to its static asset path.

    Args:
        mannequin_gender: "female" or "male" (or the MannequinGender enum).

    Returns:
        The resolved FittingRoomMannequin.

    Raises:
        InvalidMannequinGenderError: for any other value. Nothing is
        assumed or defaulted -- the caller must specify a valid gender.
    """
    try:
        gender = MannequinGender(mannequin_gender)
    except ValueError as exc:
        valid = ", ".join(g.value for g in MannequinGender)
        raise InvalidMannequinGenderError(
            f"Invalid mannequin_gender: {mannequin_gender!r}. Must be one of: {valid}."
        ) from exc

    return FittingRoomMannequin(gender=gender, asset=_MANNEQUIN_ASSETS[gender])


class FittingRoomService:
    """
    Resolves a Part 41 outfit selection into fitting-room data.

    All product data comes from an injected ShoppingAgent (defaulting to a
    plain ShoppingAgent()), which itself only talks to MCPShoppingClient.
    """

    def __init__(self, shopping_agent: Optional[ShoppingAgent] = None) -> None:
        self._shopping_agent = shopping_agent or ShoppingAgent()

    async def prepare_fitting_room(
        self,
        outfit_result: Union[Dict[str, Any], OutfitSummary],
        mannequin_gender: Union[str, MannequinGender],
        include_variants: bool = True,
        include_alternatives: bool = True,
    ) -> FittingRoomResponse:
        """
        Build the fitting-room response for an already-selected outfit.

        Args:
            outfit_result: Part 41's build_outfit() output (dict or
                OutfitSummary). Only its selected_products are resolved
                here -- no new search is performed, regardless of
                include_variants/include_alternatives.
            mannequin_gender: "female" or "male".
            include_variants: When True, call get_variants() per selected
                item. When False, no variant calls are made at all.
            include_alternatives: When True, call get_alternatives() per
                selected item. When False, no alternative calls are made.

        Returns:
            A FittingRoomResponse. Its top-level status is "ready" only
            when the underlying outfit's own status is "complete";
            otherwise it is "incomplete" -- an incomplete outfit is never
            reported as ready, and missing_items/total_price are carried
            through from the outfit unchanged.

        Raises:
            InvalidMannequinGenderError: for an unsupported mannequin_gender.
            MCPConnectionError / MCPToolError: propagated unchanged from the
                underlying ShoppingAgent/MCP calls.
        """
        mannequin = resolve_mannequin(mannequin_gender)

        outfit = (
            outfit_result
            if isinstance(outfit_result, OutfitSummary)
            else OutfitSummary.model_validate(outfit_result)
        )

        items: List[FittingRoomItem] = [
            await self._resolve_item(
                selected.product_id,
                selected.category,
                selected.item_index,
                include_variants=include_variants,
                include_alternatives=include_alternatives,
            )
            for selected in outfit.selected_products
        ]

        overall_status = FITTING_ROOM_READY if outfit.status == "complete" else FITTING_ROOM_INCOMPLETE

        return FittingRoomResponse(
            status=overall_status,
            mannequin=mannequin,
            outfit=outfit,
            items=items,
        )

    async def _resolve_item(
        self,
        product_id: str,
        category: str,
        item_index: int,
        *,
        include_variants: bool,
        include_alternatives: bool,
    ) -> FittingRoomItem:
        """
        Resolve one already-selected product_id into a FittingRoomItem.

        Only get_product()/get_variants()/get_alternatives() are called --
        never search()/search_outfit()/find_products().

        The returned product is the real product exactly as MCP returned
        it. visual_source is "product_image" only when that real product
        has an image_url; otherwise it stays None (nothing is fabricated).
        """
        raw_product = await self._shopping_agent.get_product(product_id)

        if raw_product is None:
            return FittingRoomItem(
                item_index=item_index,
                category=category,
                product=None,
                visual_source=None,
                color_variations=[],
                alternatives=[],
                error=PRODUCT_NOT_FOUND_ERROR,
            )

        product = FittingRoomProduct.model_validate(raw_product)

        color_variations: List[ColorVariation] = []
        if include_variants:
            raw_variants = await self._shopping_agent.get_variants(product_id)
            color_variations = [
                ColorVariation.model_validate(variant) for variant in (raw_variants or [])
            ]

        alternatives: List[FittingRoomProduct] = []
        if include_alternatives:
            raw_alternatives = await self._shopping_agent.get_alternatives(product_id)
            alternatives = [
                FittingRoomProduct.model_validate(alt) for alt in (raw_alternatives or [])
            ]

        return FittingRoomItem(
            item_index=item_index,
            category=category,
            product=product,
            visual_source=VISUAL_SOURCE_PRODUCT_IMAGE if product.image_url else None,
            color_variations=color_variations,
            alternatives=alternatives,
            error=None,
        )