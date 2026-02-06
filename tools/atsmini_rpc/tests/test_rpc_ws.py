import os

import pytest

from atsmini_rpc.client import WebSocketRpcClient


WS_URL = os.getenv("ATSMINI_WS_URL")
pytestmark = pytest.mark.skipif(not WS_URL, reason="ATSMINI_WS_URL not set")


def test_ws_volume_set():
    client = WebSocketRpcClient(WS_URL)
    try:
        req_id = client.request("volume.set", {"value": 12})
        reply = client.read_response(req_id)
        assert reply.get("id") == req_id
        assert reply.get("result", {}).get("volume") == 12
    finally:
        client.close()


def test_ws_capabilities_get():
    client = WebSocketRpcClient(WS_URL)
    try:
        req_id = client.request("capabilities.get")
        reply = client.read_response(req_id)
        assert reply.get("id") == req_id
        assert reply.get("result", {}).get("rpc_version") == 1
    finally:
        client.close()


def test_ws_status_get():
    client = WebSocketRpcClient(WS_URL)
    try:
        req_id = client.request("status.get")
        reply = client.read_response(req_id)
        result = reply.get("result", {})
        assert "band" in result
        assert "mode" in result
    finally:
        client.close()
