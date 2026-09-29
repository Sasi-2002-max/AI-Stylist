from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class WardrobeItemSchema(BaseModel):
    """
    A product the user has saved to their personal wardrobe.

    Holds the saved item's identifiers plus the product details needed to
    display it. The owning user is handled by the database/API layer.
    """

    wardrobe_item_id: Optional[str] = None
    product_id: Optional[str] = None
    category: Optional[str] = None
    product_name: str
    brand: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    currency: str = "INR"
    image_url: Optional[str] = None
    product_url: Optional[str] = None