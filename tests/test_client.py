"""Offline tests; the official service is never contacted."""

from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from mcp.types import CallToolResult, TextContent, Tool

from mcd_watch import client


SCHEMA = {
    "type": "object",
    "properties": {"startDate": {"type": "string"}},
    "required": ["startDate"],
    "additionalProperties": False,
}


def make_session(*, tools=None, result=None):
    if tools is None:
        tools = [Tool(name=client.TOOL_NAME, inputSchema=SCHEMA)]
    if result is None:
        result = CallToolResult(
            content=[TextContent(type="text", text="Calendar result")],
            structuredContent={"campaigns": []},
        )
    return SimpleNamespace(
        list_tools=AsyncMock(
            return_value=SimpleNamespace(tools=tools, nextCursor=None)
        ),
        call_tool=AsyncMock(return_value=result),
    )


@asynccontextmanager
async def session_context(session):
    yield session


class CalendarClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_token_fails_without_connection(self):
        with (
            patch.dict(client.os.environ, {}, clear=True),
            patch.object(client.sys.stdin, "isatty", return_value=False),
            patch.object(client, "streamablehttp_client") as transport,
        ):
            with self.assertRaisesRegex(client.CalendarClientError, "missing"):
                await client.discover()
        transport.assert_not_called()

    async def test_discovery_returns_only_the_calendar_schema(self):
        session = make_session(tools=[
            Tool(name="account-update", inputSchema={"type": "object"}),
            Tool(name=client.TOOL_NAME, inputSchema=SCHEMA),
        ])
        with patch.object(client, "_session", lambda: session_context(session)):
            discovered = await client.discover()
        self.assertEqual(discovered, SCHEMA)
        self.assertIsNot(discovered, SCHEMA)
        session.call_tool.assert_not_awaited()

    async def test_missing_tool_never_calls_other_tools(self):
        session = make_session(tools=[
            Tool(name="account-update", inputSchema={"type": "object"})
        ])
        with patch.object(client, "_session", lambda: session_context(session)):
            with self.assertRaisesRegex(client.CalendarClientError, "did not expose"):
                await client.fetch_campaign({"startDate": "2026-10-23"})
        session.call_tool.assert_not_awaited()

    async def test_required_argument_is_validated(self):
        session = make_session()
        with patch.object(client, "_session", lambda: session_context(session)):
            with self.assertRaisesRegex(client.CalendarClientError, "required"):
                await client.fetch_campaign({})
        session.call_tool.assert_not_awaited()

    async def test_wrong_type_is_validated_without_disclosing_value(self):
        session = make_session()
        private_value = {"private": "do-not-print-this"}
        with patch.object(client, "_session", lambda: session_context(session)):
            with self.assertRaises(client.CalendarClientError) as caught:
                await client.fetch_campaign({"startDate": private_value})
        self.assertIn("type", str(caught.exception))
        self.assertNotIn("do-not-print-this", str(caught.exception))
        session.call_tool.assert_not_awaited()

    async def test_tool_error_does_not_return_or_disclose_raw_result(self):
        session = make_session(result=CallToolResult(
            content=[TextContent(type="text", text="secret-token-and-user-data")],
            isError=True,
        ))
        with patch.object(client, "_session", lambda: session_context(session)):
            with self.assertRaises(client.CalendarClientError) as caught:
                await client.fetch_campaign({"startDate": "2026-10-23"})
        self.assertIn("reported an error", str(caught.exception))
        self.assertNotIn("secret-token", str(caught.exception))

    async def test_success_preserves_schema_result_and_provenance(self):
        session = make_session()
        arguments = {"startDate": "2026-10-23"}
        with patch.object(client, "_session", lambda: session_context(session)):
            result = await client.call_campaign(arguments)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["server"], "https://mcp.mcd.cn")
        self.assertEqual(result["result"]["structuredContent"], {"campaigns": []})
        self.assertFalse(result["result"]["isError"])
        self.assertIsNotNone(datetime.fromisoformat(result["retrieved_at"]).tzinfo)
        session.call_tool.assert_awaited_once_with(
            "campaign-calendar", arguments=arguments
        )

    async def test_discovery_follows_tools_list_pagination(self):
        session = make_session()
        session.list_tools.side_effect = [
            SimpleNamespace(tools=[], nextCursor="next-page"),
            SimpleNamespace(
                tools=[Tool(name=client.TOOL_NAME, inputSchema=SCHEMA)],
                nextCursor=None,
            ),
        ]
        with patch.object(client, "_session", lambda: session_context(session)):
            self.assertEqual(await client.discover(), SCHEMA)
        self.assertEqual(session.list_tools.await_count, 2)
        self.assertEqual(session.list_tools.await_args.kwargs, {"cursor": "next-page"})

    async def test_sdk_error_is_sanitized(self):
        @asynccontextmanager
        async def broken_transport(*args, **kwargs):
            raise RuntimeError("Authorization: Bearer private-token")
            yield

        with (
            patch.dict(client.os.environ, {client.TOKEN_ENV: "private-token"}),
            patch.object(client, "streamablehttp_client", broken_transport),
        ):
            with self.assertRaises(client.CalendarClientError) as caught:
                await client.discover()
        self.assertNotIn("private-token", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    async def test_sdk_task_group_preserves_safe_tool_error(self):
        @asynccontextmanager
        async def grouped_transport(*args, **kwargs):
            raise ExceptionGroup("transport shutdown", [
                client.CalendarClientError("Safe campaign-calendar error.")
            ])
            yield

        with (
            patch.dict(client.os.environ, {client.TOKEN_ENV: "private-token"}),
            patch.object(client, "streamablehttp_client", grouped_transport),
        ):
            with self.assertRaisesRegex(
                client.CalendarClientError, "Safe campaign-calendar error"
            ):
                await client.discover()


if __name__ == "__main__":
    unittest.main()
