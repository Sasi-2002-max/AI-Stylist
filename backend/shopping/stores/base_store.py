"""
Abstract base interface for product sources ("stores").

BaseStore defines the common operations every product source must support,
regardless of where its data actually comes from -- a local mock catalog
today, and later a real source such as SerpApi / Google Shopping.

Architecture:

    Shopping Agent
          v
    BaseStore (interface)      <-- this file
          v
    MockStore / AmazonStore / MyntraStore / ... / (future) SerpApiStore
          v
    Product Normalizer
          v
    Product Ranker

BaseStore itself makes no network or file-system calls -- it only defines
the contract. Concrete subclasses are responsible for their own product
source and must return the common Product model from product_normalizer.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from backend.shopping.product_normalizer import Product


class BaseStore(ABC):
    """
    Abstraction for any product source.

    A concrete store (mock, or a future real retailer/aggregator adapter)
    must implement all five operations below, and must always return the
    common Product model -- never a raw, store-specific dict.
    """

    @abstractmethod
    def search_products(
        self,
        query: str,
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
    ) -> List[Product]:
        """
        Search this store for products matching a free-text query and
        optional filters.

        Args:
            query: Free-text search terms.
            budget: Optional maximum price (inclusive).
            category: Optional exact category filter, e.g. "dresses".
            color: Optional exact color filter, e.g. "black".

        Returns:
            A list of matching Product objects (may be empty).
        """
        raise NotImplementedError

    @abstractmethod
    def get_product(self, product_id: str) -> Optional[Product]:
        """
        Look up a single product by its product_id.

        Returns:
            The matching Product, or None if no such product exists in
            this store.
        """
        raise NotImplementedError

    @abstractmethod
    def get_variants(self, product_id: str) -> List[Product]:
        """
        Return other products that represent variants of the given product
        (e.g. the same item in different colors/sizes, when the store's
        data models that relationship).

        Returns:
            A list of variant Product objects. Empty if the store has no
            variant information or the product does not exist.
        """
        raise NotImplementedError

    @abstractmethod
    def check_availability(self, product_id: str) -> bool:
        """
        Check whether a product is currently available.

        Returns:
            True if available, False if unavailable or the product does
            not exist in this store.
        """
        raise NotImplementedError

    @abstractmethod
    def get_alternatives(self, product_id: str, limit: int = 5) -> List[Product]:
        """
        Suggest alternative products to the given one (e.g. same category,
        different brand/color), for use when a user wants to "explore
        alternatives" or the Critic Agent requests a revision.

        Args:
            product_id: The reference product's id.
            limit: Maximum number of alternatives to return.

        Returns:
            A list of alternative Product objects (may be empty).
        """
        raise NotImplementedError