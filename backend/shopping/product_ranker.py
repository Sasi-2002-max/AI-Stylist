"""
Deterministic Product ranker.

Scores and sorts common Product objects against a set of outfit
requirements (category, color, budget, style). No LLM call, no ML model,
no product API, no MCP call happens here -- purely arithmetic scoring over
already-normalized Product objects.

Architecture:

    Product Normalizer
           v
    list[Product]
           v
    rank_products()         <-- this file
           v
    list[Product]  (sorted, all fields intact, including image_url/product_url)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.shopping.product_normalizer import Product

# Score contributions. Kept as named constants so the weighting is explicit
# and easy to tune later without hunting through the scoring logic.
UNAVAILABLE_PENALTY = 1000.0
CATEGORY_MATCH_SCORE = 40.0
COLOR_MATCH_SCORE = 30.0
BUDGET_WITHIN_SCORE = 20.0
BUDGET_OVER_MAX_PENALTY = 20.0
STYLE_MATCH_SCORE = 10.0


def _matches_category(product: Product, wanted_category: Optional[str]) -> bool:
    if not wanted_category:
        return False
    return product.category.strip().lower() == str(wanted_category).strip().lower()


def _matches_color(product: Product, wanted_color: Optional[str]) -> bool:
    if not wanted_color or not product.color:
        return False
    return product.color.strip().lower() == str(wanted_color).strip().lower()


def _budget_score(product: Product, budget: Optional[float]) -> float:
    """
    +BUDGET_WITHIN_SCORE when the product fits within budget.
    A capped penalty, scaled by how far over budget it is, otherwise.
    No opinion at all when no budget was given.
    """
    if budget is None:
        return 0.0
    if budget <= 0:
        return 0.0
    if product.price <= budget:
        return BUDGET_WITHIN_SCORE
    over_ratio = (product.price - budget) / budget
    return -min(BUDGET_OVER_MAX_PENALTY, over_ratio * BUDGET_OVER_MAX_PENALTY)


def _style_score(product: Product, outfit_requirements: Dict[str, Any]) -> float:
    """
    Light style-compatibility bonus when style information is available.
    Looks for any stated style term inside the product's title/color, since
    Product has no dedicated style field. Purely additive and optional.
    """
    style_terms = outfit_requirements.get("style") or outfit_requirements.get(
        "style_preferences"
    )
    if not style_terms:
        return 0.0

    if isinstance(style_terms, str):
        style_terms = [style_terms]

    haystack = f"{product.title} {product.color or ''}".lower()
    for term in style_terms:
        if str(term).strip().lower() in haystack:
            return STYLE_MATCH_SCORE
    return 0.0


def _score_product(product: Product, outfit_requirements: Dict[str, Any]) -> float:
    """Compute a single deterministic score for one product."""
    score = 0.0

    if not product.availability:
        score -= UNAVAILABLE_PENALTY

    if _matches_category(product, outfit_requirements.get("category")):
        score += CATEGORY_MATCH_SCORE

    if _matches_color(product, outfit_requirements.get("color")):
        score += COLOR_MATCH_SCORE

    score += _budget_score(product, outfit_requirements.get("budget"))
    score += _style_score(product, outfit_requirements)

    return score


def rank_products(
    products: List[Product],
    outfit_requirements: Optional[Dict[str, Any]] = None,
) -> List[Product]:
    """
    Score and sort products against outfit requirements.

    Args:
        products: Candidate Product objects to rank. Never mutated or
            reshaped -- every returned item is the same Product object with
            all fields (including image_url and product_url) intact.
        outfit_requirements: Optional dict that may contain any of:
            "category", "color", "budget", "style" / "style_preferences".
            Any missing key is simply not scored on.

    Returns:
        The same Product objects, sorted from highest score to lowest.
        Ties are broken by original input order (stable sort), so ranking
        is fully deterministic for the same input.
    """
    requirements = outfit_requirements or {}

    indexed_scores = [
        (_score_product(product, requirements), index, product)
        for index, product in enumerate(products)
    ]
    indexed_scores.sort(key=lambda entry: (-entry[0], entry[1]))

    return [product for _, _, product in indexed_scores]


if __name__ == "__main__":
    import json

    mock_products = [
        Product(
            product_id="AMZ1",
            store="Amazon",
            brand="BrandA",
            title="Black Regular Fit Shirt",
            category="shirt",
            color="black",
            price=899,
            sizes=["S", "M", "L"],
            image_url="https://example.com/amz1.jpg",
            product_url="https://example.com/product/AMZ1",
            availability=True,
        ),
        Product(
            product_id="AMZ2",
            store="Amazon",
            brand="BrandB",
            title="Navy Slim Fit Shirt",
            category="shirt",
            color="navy",
            price=1899,
            sizes=["M", "L"],
            image_url=None,
            product_url="https://example.com/product/AMZ2",
            availability=True,
        ),
        Product(
            product_id="MYN1",
            store="Myntra",
            brand="BrandC",
            title="Black Oversized Shirt",
            category="shirt",
            color="black",
            price=1200,
            sizes=["S", "M"],
            image_url="https://example.com/myn1.jpg",
            product_url="https://example.com/product/MYN1",
            availability=False,
        ),
    ]

    requirements = {"category": "shirt", "color": "black", "budget": 1500}

    ranked = rank_products(mock_products, requirements)

    print("Ranking requirements:", json.dumps(requirements, indent=2))
    print()
    for position, product in enumerate(ranked, start=1):
        print(
            f"{position}. {product.title} "
            f"(₹{product.price}, available={product.availability}, "
            f"image_url={'set' if product.image_url else 'None'})"
        )