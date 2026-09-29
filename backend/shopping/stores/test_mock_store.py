"""Tests for the MockStore BaseStore implementation and its placeholder peers."""

import pytest

from backend.shopping.product_normalizer import Product
from backend.shopping.product_ranker import rank_products
from backend.shopping.stores.ajio import AjioStore
from backend.shopping.stores.amazon import AmazonStore
from backend.shopping.stores.hm import HMStore
from backend.shopping.stores.mock_store import MockStore
from backend.shopping.stores.myntra import MyntraStore


@pytest.fixture
def store() -> MockStore:
    return MockStore()


def test_mock_store_can_be_instantiated(store):
    assert isinstance(store, MockStore)


def test_search_products_returns_product_objects(store):
    results = store.search_products(query="", limit=10) if hasattr(
        store, "search_products"
    ) else []
    results = store.search_products(query="")
    assert len(results) > 0
    assert all(isinstance(product, Product) for product in results)


def test_search_products_filters_by_category(store):
    results = store.search_products(query="", category="dresses")
    assert len(results) > 0
    assert all(product.category == "dresses" for product in results)


def test_search_products_filters_by_color(store):
    results = store.search_products(query="", color="black")
    assert len(results) > 0
    assert all(product.color == "black" for product in results)


def test_search_products_respects_budget(store):
    results = store.search_products(query="", budget=5000)
    assert len(results) > 0
    assert all(product.price <= 5000 for product in results)


def test_search_products_query_matching(store):
    results = store.search_products(query="wedding dress")
    assert len(results) > 0
    for product in results:
        haystack = f"{product.title} {product.brand} {product.category} {product.color}".lower()
        assert "wedding" in haystack and "dress" in haystack


def test_get_product_returns_correct_product(store):
    product = store.get_product("MOCK001")
    assert product is not None
    assert product.product_id == "MOCK001"
    assert product.title == "Black Oxford Shirt"


def test_get_product_returns_none_for_unknown_id(store):
    assert store.get_product("DOES_NOT_EXIST") is None


def test_get_variants_returns_product_list(store):
    variants = store.get_variants("MOCK001")
    assert isinstance(variants, list)
    assert all(isinstance(product, Product) for product in variants)


def test_get_variants_for_unknown_id_returns_empty_list(store):
    assert store.get_variants("DOES_NOT_EXIST") == []


def test_check_availability_returns_boolean(store):
    assert store.check_availability("MOCK001") is True
    # MOCK004 (Maroon Checked Shirt) is marked unavailable in the catalog.
    assert store.check_availability("MOCK004") is False


def test_check_availability_for_unknown_id_returns_false(store):
    assert store.check_availability("DOES_NOT_EXIST") is False


def test_get_alternatives_returns_product_objects(store):
    alternatives = store.get_alternatives("MOCK001", limit=3)
    assert len(alternatives) > 0
    assert all(isinstance(product, Product) for product in alternatives)
    assert all(product.product_id != "MOCK001" for product in alternatives)
    assert all(product.category == "shirts" for product in alternatives)


def test_image_url_is_preserved(store):
    product = store.get_product("MOCK001")
    assert product.image_url == "https://cdn.mockfashionstore.test/images/mock001.jpg"


def test_missing_image_remains_none(store):
    product = store.get_product("MOCK003")  # Navy Casual Shirt, no image in catalog
    assert product.image_url is None


def test_product_url_is_never_fabricated_and_is_preserved(store):
    product = store.get_product("MOCK001")
    assert product.product_url == "https://www.mockfashionstore.test/product/MOCK001"


def test_mock_store_products_work_with_existing_ranker(store):
    products = store.search_products(query="", category="shirts")
    assert len(products) > 0

    ranked = rank_products(products, {"category": "shirts", "color": "black", "budget": 1500})

    assert len(ranked) == len(products)
    assert all(isinstance(product, Product) for product in ranked)
    assert {p.product_id for p in products} == {p.product_id for p in ranked}


@pytest.mark.parametrize(
    "store_class", [AmazonStore, MyntraStore, HMStore, AjioStore]
)
def test_placeholder_stores_delegate_to_mock_data(store_class):
    """Placeholder retailer adapters return real mock data via delegation, not errors."""
    placeholder_store = store_class()
    results = placeholder_store.search_products(query="", category="dresses")
    assert len(results) > 0
    assert all(isinstance(product, Product) for product in results)