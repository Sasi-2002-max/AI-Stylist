"""Tests for the common Product schema and normalizer."""

import pytest

from backend.shopping.product_normalizer import (
    Product,
    ProductNormalizationError,
    normalize_product,
)


def test_product_schema_accepts_valid_data():
    """A valid Product can be created directly from the common schema."""
    product = Product(
        product_id="AMZ123",
        store="Amazon",
        brand="Example Brand",
        title="Black Slim Fit Shirt",
        category="shirt",
        color="black",
        price=899,
        currency="INR",
        sizes=["S", "M", "L"],
        image_url="https://example.com/product-image.jpg",
        product_url="https://example.com/product",
        availability=True,
    )
    assert product.product_id == "AMZ123"
    assert product.price == 899.0


def test_image_url_is_preserved_through_normalization():
    """image_url from the raw product survives normalization unchanged."""
    raw = {
        "asin": "AMZ123",
        "brand": "Brand",
        "title": "Black Shirt",
        "category": "shirt",
        "price": 899,
        "image": "https://example.com/black-shirt.jpg",
        "url": "https://example.com/product/AMZ123",
    }
    product = normalize_product(raw, store="Amazon")
    assert product.image_url == "https://example.com/black-shirt.jpg"


def test_product_url_is_preserved_separately_from_image_url():
    """product_url and image_url map from different raw fields and never collide."""
    raw = {
        "id": "AMZ999",
        "title": "Cream Trousers",
        "category": "pants",
        "price": 1699,
        "image_url": "https://example.com/image.jpg",
        "product_url": "https://example.com/page.html",
    }
    product = normalize_product(raw, store="Amazon")
    assert product.image_url == "https://example.com/image.jpg"
    assert product.product_url == "https://example.com/page.html"
    assert product.image_url != product.product_url


def test_normalize_amazon_like_product():
    """A full Amazon-like raw product maps to the expected common Product."""
    raw = {
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
    product = normalize_product(raw, store="Amazon")

    assert product == Product(
        product_id="AMZ123",
        store="Amazon",
        brand="Brand",
        title="Black Shirt",
        category="shirt",
        color="black",
        price=899,
        currency="INR",
        sizes=["S", "M", "L"],
        image_url="https://example.com/black-shirt.jpg",
        product_url="https://example.com/product/AMZ123",
        availability=True,
    )


def test_missing_image_becomes_none_not_fabricated():
    """A raw product with no image field at all results in image_url=None."""
    raw = {
        "id": "MYN456",
        "name": "Cream Trousers",
        "category": "pants",
        "price": 1699,
        "url": "https://example.com/product/MYN456",
    }
    product = normalize_product(raw, store="Myntra")
    assert product.image_url is None


def test_field_name_variations_are_supported():
    """Common alias keys (name, sku, link, sale_price, size string) all resolve correctly."""
    raw = {
        "sku": "HM789",
        "name": "White T-Shirt",
        "category": "shirt",
        "color": "white",
        "sale_price": "₹1,299",
        "size": "S,M,L",
        "link": "https://example.com/product/HM789",
        "availability": "in stock",
    }
    product = normalize_product(raw, store="H&M")

    assert product.product_id == "HM789"
    assert product.title == "White T-Shirt"
    assert product.price == 1299.0
    assert product.sizes == ["S", "M", "L"]
    assert product.product_url == "https://example.com/product/HM789"
    assert product.availability is True


def test_missing_product_url_raises_error_rather_than_fabricating():
    """A raw product with no URL field at all is a hard error, not a guess."""
    raw = {
        "id": "AMZ000",
        "title": "Brown Loafers",
        "category": "shoes",
        "price": 1499,
    }
    with pytest.raises(ProductNormalizationError):
        normalize_product(raw, store="Amazon")


def test_missing_price_raises_error():
    """A raw product with no parseable price is a hard error."""
    raw = {
        "id": "AMZ001",
        "title": "Brown Loafers",
        "category": "shoes",
        "url": "https://example.com/product/AMZ001",
    }
    with pytest.raises(ProductNormalizationError):
        normalize_product(raw, store="Amazon")