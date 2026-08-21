from fastmcp import Client

from project_otp_mcp.keychain import KeychainAccessError, KeychainNotConfiguredError
from project_otp_mcp.server import build_server

RFC_SHA1_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


async def test_server_exposes_only_no_argument_get_totp() -> None:
    server = build_server(seed_loader=lambda: RFC_SHA1_SECRET, clock=lambda: 59)
    async with Client(server) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools] == ["get_totp"]
        assert tools[0].inputSchema["properties"] == {}
        result = await client.call_tool("get_totp", {})
    assert result.structured_content == {"code": "287082", "valid_for_seconds": 1}


async def test_server_redacts_keychain_failures() -> None:
    marker = "private-marker"

    def fail() -> str:
        raise KeychainAccessError(marker)

    server = build_server(seed_loader=fail, clock=lambda: 59)
    async with Client(server) as client:
        result = await client.call_tool("get_totp", {}, raise_on_error=False)
    assert result.is_error is True
    assert marker not in str(result.content)


async def test_server_explains_missing_configuration() -> None:
    def fail() -> str:
        raise KeychainNotConfiguredError("hidden")

    server = build_server(seed_loader=fail, clock=lambda: 59)
    async with Client(server) as client:
        result = await client.call_tool("get_totp", {}, raise_on_error=False)
    assert result.is_error is True
    assert "otp-mcp setup" in str(result.content)
