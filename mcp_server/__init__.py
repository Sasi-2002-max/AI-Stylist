"""
MCP layer for StyleAI's shopping tools.

This package exposes the shopping tool boundary (search_products,
get_product, get_variants, check_availability, get_alternatives) over MCP.

For now, every tool is backed by backend.shopping.stores.mock_store.MockStore
for development and testing. Production will later back these same tools
with SerpApi / Google Shopping, without changing the tool names or the
Product schema they return.
"""