from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import patch

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

import lamp_mcp_server


class LampMcpServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_server_starts_and_lists_tools(self) -> None:
        server_path = Path(lamp_mcp_server.__file__).resolve()
        transport = StdioTransport(
            command=sys.executable,
            args=[str(server_path)],
            cwd=str(server_path.parent),
            env={"DEVICE_SERVICE_URL": "http://127.0.0.1:8000"},
        )
        async with Client(transport) as client:
            tools = await client.list_tools()

        self.assertIn("control_lamp", {tool.name for tool in tools})

    async def test_exposes_expected_tools_and_control_schema(self) -> None:
        async with Client(lamp_mcp_server.mcp) as client:
            tools = await client.list_tools()

        by_name = {tool.name: tool for tool in tools}
        self.assertEqual(
            set(by_name),
            {
                "get_lamp_gateway_health",
                "get_lamp_state",
                "control_lamp",
            },
        )
        properties = by_name["control_lamp"].inputSchema["properties"]
        self.assertIn("power", properties)
        self.assertIn("brightness", properties)
        self.assertIn("color_temperature", properties)

    async def test_control_sends_only_explicit_values(self) -> None:
        expected = {
            "ok": True,
            "operation": "control",
            "state": {"power": True},
        }
        with patch.object(
            lamp_mcp_server,
            "_request_json",
            return_value=expected,
        ) as request_json:
            async with Client(lamp_mcp_server.mcp) as client:
                result = await client.call_tool("control_lamp", {"power": True})

        request_json.assert_called_once_with(
            "control",
            "POST",
            "/api/device/control",
            payload={"power": True},
        )
        self.assertEqual(result.data, expected)

    async def test_control_rejects_empty_payload(self) -> None:
        async with Client(lamp_mcp_server.mcp) as client:
            result = await client.call_tool(
                "control_lamp",
                {},
                raise_on_error=False,
            )

        self.assertTrue(result.is_error)
        self.assertIn("至少需要", result.content[0].text)


if __name__ == "__main__":
    unittest.main()
