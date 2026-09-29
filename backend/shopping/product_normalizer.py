"""
Common Product schema and normalizer.

Converts store-specific raw product dicts (Amazon-like, Myntra-like, etc.)
into one common Product model that the rest of the application (ranker,
fitting room, wardrobe, and the future frontend product cards) can rely on.

Architecture:

    Raw Store Product (dict)
           v
    normalize_product()        <-- this file
           v
    Product (common schema)
           v
    Product Ranker / Frontend product cards

This file does not call any store API, does not scrape, and does not
fabricate image or product URLs. It only reshapes data it is given.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field, field_validator


class Product(BaseModel):
    """
    Common product representation used everywhere downstream of the raw
    store data: ranking, the fitting room, the wardrobe, and the eventual
    frontend product card.

    image_url and product_url are deliberately separate fields:
        image_url    -> used by the frontend to DISPLAY the product image
        product_url  -> used when the user clicks "View Product" / "Buy"
    """

    product_id: str
    store: str
    brand: str
    title: str
    category: str
    color: Optional[str] = None
    price: float
    currency: str = "INR"
    sizes: List[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    product_url: str
    availability: bool = True

    @field_validator("price")
    @classmethod
    def _price_must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("price cannot be negative")
        return value


# ---------------------------------------------------------------------------
# Field-name variations accepted from raw store data
# ---------------------------------------------------------------------------

_ID_KEYS = ("product_id", "id", "sku", "asin")
_TITLE_KEYS = ("title", "name", "product_name")
_IMAGE_KEYS = ("image_url", "image", "thumbnail", "thumbnail_url")
_URL_KEYS = ("product_url", "url", "link")
_PRICE_KEYS = ("price", "sale_price", "current_price")
_SIZE_KEYS = ("sizes", "size", "available_sizes")

_TRUE_STRINGS = {"true", "yes", "in stock", "in_stock", "available"}
_FALSE_STRINGS = {"false", "no", "out of stock", "out_of_stock", "unavailable"}


class ProductNormalizationError(ValueError):
    """Raised when a raw product cannot be safely normalized."""


def _first_present(raw: Dict[str, Any], keys: Sequence[str]) -> Optional[Any]:
    """Return the first non-empty value found in `raw` for any key in `keys`."""
    for key in keys:
        if key in raw:
            value = raw[key]
            if value is not None and value != "":
                return value
    return None


def _parse_price(raw_value: Any) -> float:
    """Convert a raw price (number or string, possibly with symbols/commas) to float."""
    if raw_value is None:
        raise ProductNormalizationError(
            "normalize_product: missing a price (expected one of: "
            f"{', '.join(_PRICE_KEYS)})"
        )
    if isinstance(raw_value, bool):
        raise ProductNormalizationError("normalize_product: price cannot be a boolean")
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    if isinstance(raw_value, str):
        cleaned = re.sub(r"[^\d.]", "", raw_value)
        if not cleaned:
            raise ProductNormalizationError(f"normalize_product: could not parse price {raw_value!r}")
        return float(cleaned)
    raise ProductNormalizationError(f"normalize_product: could not parse price {raw_value!r}")


def _parse_sizes(raw_value: Any) -> List[str]:
    """Normalize sizes into a clean list of strings, regardless of input shape."""
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple, set)):
        return [str(size).strip() for size in raw_value if str(size).strip()]
    if isinstance(raw_value, str):
        return [part.strip() for part in raw_value.split(",") if part.strip()]
    return [str(raw_value).strip()]


def _parse_availability(raw_value: Any) -> bool:
    """Normalize availability into a bool. Defaults to True when unstated."""
    if raw_value is None:
        return True
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        lowered = raw_value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
    return bool(raw_value)


def normalize_product(raw_product: Dict[str, Any], store: str) -> Product:
    """
    Convert a store-specific raw product dict into the common Product model.

    Field-name variations are resolved by checking each of that field's
    known aliases in order and using the first value present -- nothing is
    guessed or invented.

    Args:
        raw_product: The raw product dict as returned by a store/API.
        store: The store name (e.g. "Amazon"), supplied by the caller since
            raw product payloads usually don't self-identify their store.

    Returns:
        A validated Product.

    Raises:
        ProductNormalizationError: if a required field (id, title, price,
            or product URL) is missing or cannot be parsed. image_url is
            NOT required -- it becomes None rather than raising or being
            fabricated.
    """
    if not isinstance(raw_product, dict):
        raise ProductNormalizationError("normalize_product: raw_product must be a dict")

    product_id = _first_present(raw_product, _ID_KEYS)
    if not product_id:
        raise ProductNormalizationError(
            f"normalize_product: missing a product id (expected one of: {', '.join(_ID_KEYS)})"
        )

    title = _first_present(raw_product, _TITLE_KEYS)
    if not title:
        raise ProductNormalizationError(
            f"normalize_product: missing a title (expected one of: {', '.join(_TITLE_KEYS)})"
        )

    product_url = _first_present(raw_product, _URL_KEYS)
    if not product_url:
        raise ProductNormalizationError(
            f"normalize_product: missing a product URL (expected one of: {', '.join(_URL_KEYS)})"
        )

    # image_url is intentionally optional: keep None rather than fabricate one.
    image_url = _first_present(raw_product, _IMAGE_KEYS)

    price = _parse_price(_first_present(raw_product, _PRICE_KEYS))
    sizes = _parse_sizes(_first_present(raw_product, _SIZE_KEYS))

    category = str(raw_product.get("category") or "").strip().lower() or "uncategorized"

    raw_color = raw_product.get("color")
    color = str(raw_color).strip().lower() if raw_color else None

    currency = str(raw_product.get("currency") or "INR").strip().upper() or "INR"
    brand = str(raw_product.get("brand") or "Unknown").strip() or "Unknown"
    availability = _parse_availability(raw_product.get("availability"))

    return Product(
        product_id=str(product_id),
        store=store,
        brand=brand,
        title=str(title),
        category=category,
        color=color,
        price=price,
        currency=currency,
        sizes=sizes,
        image_url=str(image_url) if image_url else None,
        product_url=str(product_url),
        availability=availability,
    )


if __name__ == "__main__":
    import json

    sample_amazon_like_product = {
        "asin": "AMZ123",
        "brand": "Brand",
        "title": "Black Shirt",
        "category": "shirt",
        "color": "black",
        "price": 899,
        "currency": "INR",
        "sizes": ["S", "M", "L"],
        "image": "https://example.com/black-shirt.jpg",
        "url": "https://example.com/product/AMZ123",
        "availability": True,
    }

    sample_no_image_product = {
        "id": "MYN456",
        "name": "Cream Trousers",
        "category": "pants",
        "color": "cream",
        "sale_price": "1,699",
        "size": "S,M,L,XL",
        "link": "https://example.com/product/MYN456",
        "availability": "in stock",
    }

    for label, raw in (
        ("Amazon-like (with image)", sample_amazon_like_product),
        ("Myntra-like (no image)", sample_no_image_product),
    ):
        product = normalize_product(raw, store="Amazon" if "asin" in raw else "Myntra")
        print(f"-- {label} --")
        print(json.dumps(product.model_dump(), indent=2))
        print()