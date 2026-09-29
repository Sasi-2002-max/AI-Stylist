"""
Mock product store.

A local, file-based product source used for development and testing only.
It stands in for a real product-discovery source (SerpApi / Google
Shopping, in this project's planned architecture) so the rest of the
pipeline -- Product Normalizer, Product Ranker, and the Shopping Agent --
can be built and tested without any external API.

Architecture:

    data/products/products.json
              v
    MockStore (implements BaseStore)     <-- this file
              v
    backend.shopping.product_normalizer.normalize_product()
              v
    list[Product]
              v
    backend.shopping.product_ranker.rank_products()   (called elsewhere, not here)

This module performs NO ranking and calls NO external API/LLM/MCP. It only
loads, filters, and normalizes the local mock catalog. It never fabricates
image_url or product_url -- values come straight from the catalog, and a
missing image stays None.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.shopping.product_normalizer import Product, normalize_product
from backend.shopping.stores.base_store import BaseStore

logger = logging.getLogger(__name__)

# data/products/products.json, resolved relative to the project root
# (four levels up from this file: stores -> shopping -> backend -> root).
_PRODUCTS_JSON_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "products" / "products.json"
)

DEFAULT_LIMIT = 20
DEFAULT_ALTERNATIVES_LIMIT = 5


class MockStoreError(Exception):
    """Raised when the mock product catalog cannot be loaded."""


def _load_raw_products(path: Path = _PRODUCTS_JSON_PATH) -> List[Dict[str, Any]]:
    """
    Load the raw mock product list from disk.

    Returns a fresh list on every call and never mutates the file or any
    cached copy of its contents.

    Raises:
        MockStoreError: if the file is missing or is not valid JSON.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise MockStoreError(f"Mock product catalog not found at {path}") from exc
    except json.JSONDecodeError as exc:
        raise MockStoreError(f"Mock product catalog at {path} is not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise MockStoreError(f"Mock product catalog at {path} must be a JSON list of products")

    return data


def _matches_category(raw_product: Dict[str, Any], category: Optional[str]) -> bool:
    if not category:
        return True
    return str(raw_product.get("category", "")).strip().lower() == category.strip().lower()


def _matches_color(raw_product: Dict[str, Any], color: Optional[str]) -> bool:
    if not color:
        return True
    product_color = raw_product.get("color")
    if not product_color:
        return False
    return str(product_color).strip().lower() == color.strip().lower()


def _matches_budget(raw_product: Dict[str, Any], budget: Optional[float]) -> bool:
    if budget is None:
        return True
    price = raw_product.get("price")
    if price is None:
        return False
    try:
        return float(price) <= float(budget)
    except (TypeError, ValueError):
        return False


def _matches_query(raw_product: Dict[str, Any], query: Optional[str]) -> bool:
    """Case-insensitive substring match against title/brand/category/color; every word must match."""
    if not query:
        return True

    terms = query.strip().lower().split()
    if not terms:
        return True

    haystack = " ".join(
        str(raw_product.get(field, ""))
        for field in ("title", "brand", "category", "color")
    ).lower()

    return all(term in haystack for term in terms)


class MockStore(BaseStore):
    """
    BaseStore implementation backed by the local data/products/products.json
    mock catalog.

    All lookups are deterministic and file-based -- no network calls, no
    LLM calls, no fabricated fields. `get_variants()` and
    `get_alternatives()` operate on approximations reasonable for mock
    data: since the catalog has no explicit SKU-variant grouping,
    "variants" are other products sharing the same brand and category, and
    "alternatives" are other products in the same category, ordered by how
    close their price is to the reference product.
    """

    def __init__(self, products_path: Path = _PRODUCTS_JSON_PATH) -> None:
        self._products_path = products_path

    def _raw_products(self) -> List[Dict[str, Any]]:
        return _load_raw_products(self._products_path)

    def _normalize(self, raw_product: Dict[str, Any]) -> Optional[Product]:
        store = raw_product.get("store", "Demo Fashion")
        try:
            return normalize_product(raw_product, store=store)
        except Exception:
            logger.exception(
                "Skipping unnormalizable mock product: %s", raw_product.get("product_id")
            )
            return None

    def search_products(
        self,
        query: str = "",
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        limit: int = DEFAULT_LIMIT,
    ) -> List[Product]:
        """
        Search the mock catalog. See BaseStore.search_products for the
        general contract; `limit` is a MockStore-specific extra.
        """
        if not isinstance(limit, int) or limit < 1:
            limit = DEFAULT_LIMIT

        matches: List[Product] = []
        for raw_product in self._raw_products():
            if not (
                _matches_category(raw_product, category)
                and _matches_color(raw_product, color)
                and _matches_budget(raw_product, budget)
                and _matches_query(raw_product, query)
            ):
                continue

            product = self._normalize(raw_product)
            if product is None:
                continue

            matches.append(product)
            if len(matches) >= limit:
                break

        return matches

    def get_product(self, product_id: str) -> Optional[Product]:
        """Look up a single mock product by id, or None if not found."""
        for raw_product in self._raw_products():
            if str(raw_product.get("product_id")) == str(product_id):
                return self._normalize(raw_product)
        return None

    def get_variants(self, product_id: str) -> List[Product]:
        """
        Return other mock products sharing the same brand and category as
        the given product (see class docstring for the approximation used).
        """
        raw_products = self._raw_products()
        reference = next(
            (p for p in raw_products if str(p.get("product_id")) == str(product_id)), None
        )
        if reference is None:
            return []

        variants: List[Product] = []
        for raw_product in raw_products:
            if str(raw_product.get("product_id")) == str(product_id):
                continue
            if (
                raw_product.get("brand") == reference.get("brand")
                and raw_product.get("category") == reference.get("category")
            ):
                product = self._normalize(raw_product)
                if product is not None:
                    variants.append(product)

        return variants

    def check_availability(self,product_id: str,size: str | None = None,) -> bool:
        product = self.get_product(product_id)

        if product is None:
            return False

        if not product.availability:
            return False

        if size is None:
            return True

        return size.strip().lower() in {
            available_size.strip().lower()
            for available_size in product.sizes
        }

    def get_alternatives(
        self, product_id: str, limit: int = DEFAULT_ALTERNATIVES_LIMIT
    ) -> List[Product]:
        """
        Return other mock products in the same category as the given
        product, ordered by closeness in price (see class docstring for
        the approximation used).
        """
        if not isinstance(limit, int) or limit < 1:
            limit = DEFAULT_ALTERNATIVES_LIMIT

        raw_products = self._raw_products()
        reference = next(
            (p for p in raw_products if str(p.get("product_id")) == str(product_id)), None
        )
        if reference is None:
            return []

        reference_price = reference.get("price", 0) or 0
        candidates = [
            raw_product
            for raw_product in raw_products
            if str(raw_product.get("product_id")) != str(product_id)
            and raw_product.get("category") == reference.get("category")
        ]
        candidates.sort(key=lambda p: abs((p.get("price", 0) or 0) - reference_price))

        alternatives: List[Product] = []
        for raw_product in candidates[:limit]:
            product = self._normalize(raw_product)
            if product is not None:
                alternatives.append(product)

        return alternatives


# ---------------------------------------------------------------------------
# Backward-compatible module-level function (Part 27 interface)
# ---------------------------------------------------------------------------

_default_store = MockStore()


def search_products(
    query: Optional[str] = None,
    category: Optional[str] = None,
    color: Optional[str] = None,
    max_price: Optional[float] = None,
    limit: int = DEFAULT_LIMIT,
) -> List[Product]:
    """
    Backward-compatible function wrapper around MockStore.search_products(),
    kept so existing callers written against the Part 27 functional
    interface continue to work unchanged.
    """
    return _default_store.search_products(
        query=query or "", budget=max_price, category=category, color=color, limit=limit
    )


if __name__ == "__main__":
    store = MockStore()

    print("Store Adapter: MockStore\n")

    print("Search:")
    print("query = dresses")
    print("budget = 5000\n")
    results = store.search_products(query="dresses", budget=5000)
    print(f"Results: {len(results)}\n")
    for position, product in enumerate(results, start=1):
        print(f"{position}. {product.title} (₹{product.price:.0f}, {product.store})")

    if results:
        sample_id = results[0].product_id
        print(f"\nget_product('{sample_id}'):")
        print(f"  {store.get_product(sample_id).title}")

        print(f"\nget_variants('{sample_id}'):")
        variants = store.get_variants(sample_id)
        print(f"  {len(variants)} variant(s) found")
        for variant in variants:
            print(f"  - {variant.title} ({variant.color})")

        print(f"\ncheck_availability('{sample_id}'):")
        print(f"  {store.check_availability(sample_id)}")

        print(f"\nget_alternatives('{sample_id}', limit=3):")
        for alt in store.get_alternatives(sample_id, limit=3):
            print(f"  - {alt.title} (₹{alt.price:.0f})")

    print("\nget_product('DOES_NOT_EXIST'):")
    print(f"  {store.get_product('DOES_NOT_EXIST')}")