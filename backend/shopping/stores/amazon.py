"""
Placeholder Amazon adapter.

This class does not call Amazon directly, and does not scrape Amazon.
Production product discovery for this project will use SerpApi / Google
Shopping, not direct retailer APIs. This class exists only so the Shopping
Agent's store-selection code can be exercised end-to-end during
development, by delegating to MockStore.
"""

from __future__ import annotations

from typing import List, Optional

from backend.shopping.product_normalizer import Product
from backend.shopping.stores.base_store import BaseStore
from backend.shopping.stores.mock_store import MockStore


class AmazonStore(BaseStore):
    """
    Placeholder Amazon adapter. NOT a real Amazon integration.

    Delegates every operation to MockStore so the rest of the application
    can be developed and tested as if a real Amazon adapter existed.
    """

    def __init__(self) -> None:
        self._delegate = MockStore()

    def search_products(
        self,
        query: str,
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
    ) -> List[Product]:
        return self._delegate.search_products(
            query=query, budget=budget, category=category, color=color
        )

    def get_product(self, product_id: str) -> Optional[Product]:
        return self._delegate.get_product(product_id)

    def get_variants(self, product_id: str) -> List[Product]:
        return self._delegate.get_variants(product_id)

    def check_availability(self, product_id: str) -> bool:
        return self._delegate.check_availability(product_id)

    def get_alternatives(self, product_id: str, limit: int = 5) -> List[Product]:
        return self._delegate.get_alternatives(product_id, limit=limit)