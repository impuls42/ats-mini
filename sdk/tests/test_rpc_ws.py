import os

import pytest

from ats_sdk import AsyncWebSocketRpc

WS_URL = os.getenv("ATSMINI_WS_URL")
pytestmark = pytest.mark.skipif(not WS_URL, reason="ATSMINI_WS_URL not set")


@pytest.mark.asyncio
async def test_ws_volume_set():
    assert WS_URL is not None
    async with AsyncWebSocketRpc(WS_URL) as client:
        req_id = await client.request("volume.set", {"value": 12})
        reply = await client.read_response(req_id)
        assert reply.get("id") == req_id
        assert reply.get("result", {}).get("volume") == 12


@pytest.mark.asyncio
async def test_ws_capabilities_get():
    assert WS_URL is not None
    async with AsyncWebSocketRpc(WS_URL) as client:
        req_id = await client.request("capabilities.get")
        reply = await client.read_response(req_id)
        assert reply.get("id") == req_id
        assert reply.get("result", {}).get("rpc_version") == 1


@pytest.mark.asyncio
async def test_ws_status_get():
    assert WS_URL is not None
    async with AsyncWebSocketRpc(WS_URL) as client:
        req_id = await client.request("status.get")
        reply = await client.read_response(req_id)
        result = reply.get("result", {})
        assert "band" in result
        assert "mode" in result
