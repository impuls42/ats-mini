import os
import time

import pytest

from ats_sdk.rpc import SerialRpcClient


PORT = os.getenv("ATSMINI_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="ATSMINI_PORT not set")


def _read_until(client: SerialRpcClient, predicate, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        message = client.read_message(timeout=timeout)
        if predicate(message):
            return message
    raise TimeoutError("Timed out waiting for message")


def test_volume_set():
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        req_id = client.request("volume.set", {"value": 10})
        message = client.read_response(req_id)
        assert message.get("id") == req_id
        assert message.get("result", {}).get("volume") == 10
    finally:
        client.close()


def test_capabilities_get():
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        req_id = client.request("capabilities.get")
        message = client.read_response(req_id)
        assert message.get("id") == req_id
        result = message.get("result", {})
        assert result.get("rpc_version") == 1
        assert "formats" in result
        assert "transports" in result
    finally:
        client.close()


def test_log_get_toggle():
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        get_id = client.request("log.get")
        reply = client.read_response(get_id)
        assert reply.get("id") == get_id
        initial = reply.get("result", {}).get("enabled")

        toggle_id = client.request("log.toggle")
        toggled = client.read_response(toggle_id)
        assert toggled.get("id") == toggle_id
        assert toggled.get("result", {}).get("enabled") == (not initial)
    finally:
        client.close()


def test_stats_event_subscription():
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        req_id = client.request("events.subscribe", {"event": "stats"})
        reply = client.read_message()
        assert reply.get("id") == req_id
        assert reply.get("result", {}).get("enabled") is True

        event = _read_until(
            client,
            lambda msg: msg.get("type") == "event" and msg.get("event") == "stats",
            timeout=5.0,
        )
        assert "params" in event
    finally:
        client.close()


def test_screen_capture_rle():
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        req_id = client.request("screen.capture", {"format": "rle"})
        reply = client.read_response(req_id, timeout=5.0)
        assert reply.get("id") == req_id
        stream_id = reply.get("result", {}).get("stream_id")
        assert stream_id is not None

        total_bytes = 0
        done = False
        deadline = time.time() + 10.0
        while time.time() < deadline and not done:
            msg = client.read_message(timeout=5.0)
            if msg.get("type") != "event":
                continue
            if msg.get("event") == "screen.chunk":
                params = msg.get("params", {})
                if params.get("stream_id") == stream_id:
                    data = params.get("data", b"")
                    total_bytes += len(data)
            elif msg.get("event") == "screen.done":
                params = msg.get("params", {})
                if params.get("stream_id") == stream_id:
                    done = True
        assert done
        assert total_bytes > 0
    finally:
        client.close()


def test_status_get():
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        req_id = client.request("status.get")
        reply = client.read_response(req_id)
        result = reply.get("result", {})
        assert "band" in result
        assert "mode" in result
        assert "frequency" in result
    finally:
        client.close()


def test_basic_controls_roundtrip():
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()

        for method in ("band.up", "band.down", "mode.up", "mode.down"):
            req_id = client.request(method)
            reply = client.read_response(req_id)
            assert reply.get("id") == req_id

        for method in ("step.up", "step.down", "bandwidth.up", "bandwidth.down"):
            req_id = client.request(method)
            reply = client.read_response(req_id)
            assert reply.get("id") == req_id

        for method in ("agc.up", "agc.down", "backlight.up", "backlight.down", "cal.up", "cal.down"):
            req_id = client.request(method)
            reply = client.read_response(req_id)
            assert reply.get("id") == req_id

        for method in ("sleep.on", "sleep.off"):
            req_id = client.request(method)
            reply = client.read_response(req_id)
            assert reply.get("id") == req_id
    finally:
        client.close()


def test_memory_list():
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        req_id = client.request("memory.list")
        reply = client.read_response(req_id)
        memories = reply.get("result", {}).get("memories", [])
        assert isinstance(memories, list)
    finally:
        client.close()
