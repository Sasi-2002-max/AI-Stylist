"""
MCP client for the StyleAI Shopping Agent.

Shopping Agent
      ↓
MCPShoppingClient
      ↓
mcp_server.server
      ↓
MCP shopping tools
      ↓
MockStore (development source)

The client communicates with the MCP server over STDIO.

It does not access MockStore directly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.shared.exceptions import MCPError


# backend/shopping/mcp_client.py
# Project root is two levels above backend/shopping/.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

SERVER_MODULE = "mcp_server.server"

EXPECTED_TOOLS = frozenset(
    {
        "search_products",
        "get_product",
        "get_variants",
        "check_availability",
        "get_alternatives",
    }
)


class MCPClientError(Exception):
    """Base class for MCP client errors."""


class MCPConnectionError(MCPClientError):
    """Raised when the MCP server cannot be started or connected."""


class MCPToolError(MCPClientError):
    """Raised when an MCP tool call fails."""

    def __init__(self, tool_name: str, message: str) -> None:
        super().__init__(f"MCP tool '{tool_name}' failed: {message}")
        self.tool_name = tool_name
        self.message = message


def _text_of(result: Any) -> str:
    """Extract text blocks from an MCP tool result."""

    parts = [
        block.text
        for block in (result.content or [])
        if getattr(block, "type", None) == "text"
    ]

    return "\n".join(parts)


def _extract(result: Any) -> Any:
    """
    Convert an MCP CallToolResult into normal Python data.

    Structured content is preferred.

    FastMCP may wrap primitive/list returns as:

        {"result": value}

    That wrapper is removed.

    If structured content is unavailable, JSON text is parsed.
    """

    structured = result.structured_content

    if structured is not None:
        if (
            isinstance(structured, dict)
            and set(structured.keys()) == {"result"}
        ):
            return structured["result"]

        return structured

    texts = [
        block.text
        for block in (result.content or [])
        if getattr(block, "type", None) == "text"
    ]

    if not texts:
        return None

    def parse_text(text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    if len(texts) == 1:
        return parse_text(texts[0])

    return [parse_text(text) for text in texts]


class MCPShoppingClient:
    """Thin async client for the StyleAI MCP shopping server."""

    def __init__(
        self,
        *,
        command: Optional[str] = None,
        args: Optional[Sequence[str]] = None,
        cwd: Optional[Path | str] = None,
        env: Optional[Dict[str, str]] = None,
        read_timeout_seconds: Optional[float] = None,
    ) -> None:

        # Use the same Python interpreter that runs the application.
        self._params = StdioServerParameters(
            command=command or sys.executable,
            args=(
                list(args)
                if args is not None
                else ["-m", SERVER_MODULE]
            ),
            cwd=cwd if cwd is not None else PROJECT_ROOT,
            env={
                "MCP_TRANSPORT": "stdio",
                **(env or {}),
            },
        )

        self._read_timeout_seconds = read_timeout_seconds
        self._client: Optional[Client] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> "MCPShoppingClient":

        if self._client is not None:
            return self

        client = Client(
            self._params,
            read_timeout_seconds=self._read_timeout_seconds,
        )

        try:
            await client.__aenter__()

        except Exception as exc:
            raise MCPConnectionError(
                "Could not start/connect to MCP server "
                f"'{self._params.command} "
                f"{' '.join(self._params.args)}': {exc}"
            ) from exc

        self._client = client

        return self

    async def close(self) -> None:

        client = self._client
        self._client = None

        if client is not None:
            await client.__aexit__(None, None, None)

    async def __aenter__(self) -> "MCPShoppingClient":
        return await self.connect()

    async def __aexit__(
        self,
        exc_type,
        exc,
        tb,
    ) -> None:
        await self.close()

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    def _require_client(self) -> Client:

        if self._client is None:
            raise MCPClientError(
                "MCPShoppingClient is not connected. "
                "Use 'async with MCPShoppingClient() as client:'."
            )

        return self._client

    # ------------------------------------------------------------------
    # Generic MCP operations
    # ------------------------------------------------------------------

    async def list_tools(self) -> List[str]:

        client = self._require_client()

        names: List[str] = []
        cursor: Optional[str] = None

        try:

            while True:

                page = await client.list_tools(cursor=cursor)

                names.extend(
                    tool.name
                    for tool in page.tools
                )

                cursor = page.next_cursor

                if not cursor:
                    return names

        except MCPError as exc:

            raise MCPClientError(
                f"Could not list MCP tools: {exc}"
            ) from exc

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> Any:

        client = self._require_client()

        try:

            result = await client.call_tool(
                name,
                arguments or {},
            )

        except MCPError as exc:

            raise MCPToolError(
                name,
                str(exc),
            ) from exc

        if result.is_error:

            raise MCPToolError(
                name,
                _text_of(result)
                or "tool returned an error",
            )

        return _extract(result)

    # ------------------------------------------------------------------
    # search_products
    # ------------------------------------------------------------------

    async def search_products(
        self,
        query: str = "",
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
    ) -> List[Dict[str, Any]]:

        arguments: Dict[str, Any] = {
            "query": query,
        }

        if budget is not None:
            arguments["budget"] = budget

        if category is not None:
            arguments["category"] = category

        if color is not None:
            arguments["color"] = color

        result = await self.call_tool(
            "search_products",
            arguments,
        )

        return result

    # ------------------------------------------------------------------
    # get_product
    # ------------------------------------------------------------------

    async def get_product(
        self,
        product_id: str,
    ) -> Optional[Dict[str, Any]]:

        result = await self.call_tool(
            "get_product",
            {
                "product_id": product_id,
            },
        )

        return result

    # ------------------------------------------------------------------
    # get_variants
    # ------------------------------------------------------------------

    async def get_variants(
        self,
        product_id: str,
    ) -> List[Dict[str, Any]]:

        result = await self.call_tool(
            "get_variants",
            {
                "product_id": product_id,
            },
        )

        return result

    # ------------------------------------------------------------------
    # check_availability
    # ------------------------------------------------------------------

    async def check_availability(
        self,
        product_id: str,
        size: Optional[str] = None,
    ) -> Dict[str, Any]:

        arguments: Dict[str, Any] = {
            "product_id": product_id,
        }

        if size is not None:
            arguments["size"] = size

        available = await self.call_tool(
            "check_availability",
            arguments,
        )

        # MockStore.check_availability() returns bool.
        #
        # The MCP tool contract returns:
        #
        # {
        #     "product_id": "...",
        #     "available": true/false
        # }
        #
        # Preserve that public MCP-client contract.

        if isinstance(available, dict):
            return available

        return {
            "product_id": product_id,
            "available": bool(available),
        }

    # ------------------------------------------------------------------
    # get_alternatives
    # ------------------------------------------------------------------

    async def get_alternatives(
        self,
        product_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:

        result = await self.call_tool(
            "get_alternatives",
            {
                "product_id": product_id,
                "limit": limit,
            },
        )

        return result