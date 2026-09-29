"""Tests for the BaseStore abstract interface."""

import pytest

from backend.shopping.stores.ajio import AjioStore
from backend.shopping.stores.amazon import AmazonStore
from backend.shopping.stores.base_store import BaseStore
from backend.shopping.stores.hm import HMStore
from backend.shopping.stores.mock_store import MockStore
from backend.shopping.stores.myntra import MyntraStore


def test_base_store_cannot_be_instantiated_directly():
    """BaseStore is abstract and cannot be instantiated on its own."""
    with pytest.raises(TypeError):
        BaseStore()


def test_base_store_defines_all_five_required_operations():
    """BaseStore declares exactly the five required abstract operations."""
    expected = {
        "search_products",
        "get_product",
        "get_variants",
        "check_availability",
        "get_alternatives",
    }
    assert expected.issubset(BaseStore.__abstractmethods__)


@pytest.mark.parametrize(
    "store_class", [MockStore, AmazonStore, MyntraStore, HMStore, AjioStore]
)
def test_concrete_stores_can_be_instantiated_and_satisfy_base_store(store_class):
    """Every concrete store implements BaseStore fully and can be instantiated."""
    store = store_class()
    assert isinstance(store, BaseStore)