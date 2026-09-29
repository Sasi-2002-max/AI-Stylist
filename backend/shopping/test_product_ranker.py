"""Tests for the deterministic Product ranker."""

from backend.shopping.product_normalizer import Product
from backend.shopping.product_ranker import rank_products


def _product(**overrides) -> Product:
    defaults = dict(
        product_id="P1",
        store="Amazon",
        brand="Brand",
        title="Shirt",
        category="shirt",
        color="black",
        price=1000,
        currency="INR",
        sizes=["M", "L"],
        image_url="https://example.com/image.jpg",
        product_url="https://example.com/product",
        availability=True,
    )
    defaults.update(overrides)
    return Product(**defaults)


def test_available_products_rank_above_unavailable():
    available = _product(product_id="AVAIL", availability=True)
    unavailable = _product(product_id="UNAVAIL", availability=False)

    ranked = rank_products([unavailable, available], {})

    assert [p.product_id for p in ranked] == ["AVAIL", "UNAVAIL"]


def test_category_match_affects_ranking():
    matching = _product(product_id="MATCH", category="shirt")
    non_matching = _product(product_id="OTHER", category="pants")

    ranked = rank_products([non_matching, matching], {"category": "shirt"})

    assert [p.product_id for p in ranked] == ["MATCH", "OTHER"]


def test_color_match_affects_ranking():
    matching = _product(product_id="MATCH", color="black")
    non_matching = _product(product_id="OTHER", color="white")

    ranked = rank_products([non_matching, matching], {"color": "black"})

    assert [p.product_id for p in ranked] == ["MATCH", "OTHER"]


def test_budget_affects_ranking():
    within_budget = _product(product_id="CHEAP", price=800)
    over_budget = _product(product_id="EXPENSIVE", price=5000)

    ranked = rank_products([over_budget, within_budget], {"budget": 1000})

    assert [p.product_id for p in ranked] == ["CHEAP", "EXPENSIVE"]


def test_ranking_preserves_complete_product_metadata():
    """Ranking must never strip image_url, product_url, or any other field."""
    product = _product(
        product_id="FULL",
        image_url="https://example.com/full-image.jpg",
        product_url="https://example.com/full-product",
    )

    ranked = rank_products([product], {"category": "shirt"})

    assert len(ranked) == 1
    result = ranked[0]
    assert isinstance(result, Product)
    assert result.image_url == "https://example.com/full-image.jpg"
    assert result.product_url == "https://example.com/full-product"
    assert result == product


def test_ranking_is_deterministic_and_stable_for_ties():
    """Products scoring identically keep their original relative order."""
    first = _product(product_id="A")
    second = _product(product_id="B")

    ranked_once = rank_products([first, second], {})
    ranked_again = rank_products([first, second], {})

    assert [p.product_id for p in ranked_once] == [p.product_id for p in ranked_again]
    assert [p.product_id for p in ranked_once] == ["A", "B"]


def test_ranking_with_no_requirements_does_not_crash():
    """rank_products must work with an empty or None requirements dict."""
    products = [_product(product_id="A"), _product(product_id="B")]

    assert len(rank_products(products, {})) == 2
    assert len(rank_products(products, None)) == 2