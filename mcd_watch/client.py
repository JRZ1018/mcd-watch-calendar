"""Read-only access to the official McDonald's campaign calendar MCP tool."""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
import getpass
import json
import os
import sys
from typing import Any, AsyncIterator

from jsonschema import SchemaError, ValidationError, validators
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from referencing import Registry


SERVER_URL = "https://mcp.mcd.cn"
TOOL_NAME = "campaign-calendar"
TOKEN_ENV = "MCD_MCP_TOKEN"


class CalendarClientError(RuntimeError):
    """A safe, user-facing error that does not contain credentials or payloads."""


def _client_error_in_group(error: BaseException) -> CalendarClientError | None:
    """Recover our safe error if an SDK task group wraps it during shutdown."""
    if isinstance(error, CalendarClientError):
        return error
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            safe_error = _client_error_in_group(child)
            if safe_error is not None:
                return safe_error
    return None


def _get_token() -> str:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        if not sys.stdin.isatty():
            raise CalendarClientError(
                "MCD_MCP_TOKEN is missing. Set it before running, or use an "
                "interactive terminal to enter the token privately."
            )
        try:
            token = getpass.getpass("McDonald's MCP token (hidden): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise CalendarClientError("Token entry was cancelled.") from None
    if not token:
        raise CalendarClientError("A McDonald's MCP token is required.")
    if any(char.isspace() for char in token):
        raise CalendarClientError("The MCP token must not contain whitespace.")
    return token


@asynccontextmanager
async def _session() -> AsyncIterator[ClientSession]:
    token = _get_token()
    # The endpoint is deliberately fixed. No caller-supplied URL is accepted.
    try:
        async with streamablehttp_client(
            SERVER_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
            sse_read_timeout=60,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
    except CalendarClientError:
        raise
    except Exception as exc:
        safe_error = _client_error_in_group(exc)
        if safe_error is not None:
            raise safe_error from None
        # SDK/HTTP exceptions can embed headers, bodies, and tool arguments.
        # Keep those out of the CLI, application logs, and chained tracebacks.
        raise CalendarClientError(
            "The official MCP connection failed. Check your network and token, "
            "then retry. No account changes were requested."
        ) from None


async def _find_schema(session: ClientSession) -> dict[str, Any]:
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        response = await session.list_tools(cursor=cursor)
        for tool in response.tools:
            if tool.name == TOOL_NAME:
                schema = deepcopy(tool.inputSchema)
                if not isinstance(schema, dict):
                    raise CalendarClientError(
                        "The campaign-calendar input schema is invalid."
                    )
                return schema
        cursor = response.nextCursor
        if not cursor:
            raise CalendarClientError(
                "The official server did not expose campaign-calendar. "
                "No other tool was called."
            )
        if cursor in seen_cursors:
            raise CalendarClientError(
                "The official server returned a repeated tools/list cursor."
            )
        seen_cursors.add(cursor)


def _validate_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> None:
    if not isinstance(arguments, dict):
        raise CalendarClientError("Campaign arguments must be a JSON object.")
    try:
        json.dumps(arguments, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise CalendarClientError(
            "Campaign arguments must contain valid JSON values."
        ) from None
    try:
        validator_type = validators.validator_for(schema)
        validator_type.check_schema(schema)
        # An empty registry prevents schema references from causing extra HTTP
        # requests. Only the fixed official MCP endpoint may be contacted.
        validator = validator_type(schema, registry=Registry())
        validator.validate(arguments)
    except SchemaError:
        raise CalendarClientError(
            "The official campaign-calendar input schema is invalid."
        ) from None
    except ValidationError as exc:
        # ValidationError.message often includes the user's actual values.
        category = exc.validator
        safe_categories = {
            "required", "type", "enum", "const", "additionalProperties",
            "minLength", "maxLength", "minimum", "maximum", "pattern",
            "minItems", "maxItems", "oneOf", "anyOf", "allOf", "not",
            "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
            "uniqueItems", "minProperties", "maxProperties",
            "dependentRequired", "format",
        }
        detail = f" ({category})" if category in safe_categories else ""
        raise CalendarClientError(
            f"Campaign arguments do not match the server schema{detail}. "
            "Run discovery and provide the required fields with matching types."
        ) from None
    except Exception:
        raise CalendarClientError(
            "The campaign-calendar input schema could not be validated."
        ) from None


async def discover() -> dict[str, Any]:
    """Return only campaign-calendar's current inputSchema from tools/list."""
    async with _session() as session:
        return await _find_schema(session)


async def fetch_campaign(arguments: dict[str, Any]) -> dict[str, Any]:
    """Discover, validate, then call only the read-only campaign-calendar tool.

    Arguments are never inferred or filled in. They must match the schema
    returned by the same session's tools/list response.
    """
    async with _session() as session:
        schema = await _find_schema(session)
        _validate_arguments(arguments, schema)
        result = await session.call_tool(TOOL_NAME, arguments=arguments)
        if result.isError:
            raise CalendarClientError(
                "The campaign-calendar tool reported an error. "
                "Check its discovered schema and your token, then retry."
            )
        return {
            "schema": schema,
            "result": result.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "server": SERVER_URL,
        }


async def call_campaign(arguments: dict[str, Any]) -> dict[str, Any]:
    """Public alias for fetch_campaign, with the same discovery and validation."""
    return await fetch_campaign(arguments)
