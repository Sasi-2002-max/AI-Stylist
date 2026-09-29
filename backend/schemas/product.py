from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProductSchema(BaseModel):
    """
    Normalized product data from any shopping/search source.

    Products from different stores (Amazon, Flipkart, Myntra, H&M, Zara, etc.)
    are converted into this one consistent structure. Provider-specific extras
    go in the flexible metadata dictionary.
    """

    product_id: Optional[str] = None
    store: str
    brand: Optional[str] = None
    title: str
    category: Optional[str] = None
    color: Optional[str] = None
    price: float = Field(ge=0)
    currency: str = "INR"
    sizes: List[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    availability: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)