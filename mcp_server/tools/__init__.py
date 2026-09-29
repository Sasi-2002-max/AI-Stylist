"""
Individual MCP shopping tools.

Each module here defines:
    - a plain `<tool>_impl(...)` function containing the actual logic,
      callable directly (e.g. from tests) with no MCP transport involved.
    - a `register(mcp)` function that wraps that logic as an MCP tool on
      the given FastMCP server instance.

All tools currently delegate to backend.shopping.stores.mock_store.MockStore
and return the common Product model (as plain dicts, via Product.model_dump()).
No tool here ranks products, fabricates data, or scrapes any website.
"""