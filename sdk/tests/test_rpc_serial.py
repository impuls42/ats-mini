import logging
import os
import random
import time

import pytest

from ats_sdk.rpc import SerialRpcClient

# Test logger
log = logging.getLogger("test.rpc_serial")


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
    log.info("=== Starting test_volume_set ===")
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        volume = random.randint(0, 16)
        log.info(f"Testing volume.set with value={volume}")
        req_id = client.request("volume.set", {"value": volume})
        message = client.read_response(req_id)
        assert message.get("id") == req_id
        assert message.get("result", {}).get("volume") == volume
        log.info("✓ test_volume_set passed")
    finally:
        client.close()


def test_capabilities_get():
    log.info("=== Starting test_capabilities_get ===")
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        log.info("Requesting capabilities.get")
        req_id = client.request("capabilities.get")
        message = client.read_response(req_id)
        assert message.get("id") == req_id
        result = message.get("result", {})
        assert result.get("rpc_version") == 1
        assert "formats" in result
        assert "transports" in result
        log.info(f"✓ test_capabilities_get passed (rpc_version={result.get('rpc_version')})")
    finally:
        client.close()


def test_log_get_toggle():
    log.info("=== Starting test_log_get_toggle ===")
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        log.info("Getting initial log state")
        get_id = client.request("log.get")
        reply = client.read_response(get_id)
        assert reply.get("id") == get_id
        initial = reply.get("result", {}).get("enabled")
        log.info(f"Initial log state: {initial}")

        log.info("Toggling log state")
        toggle_id = client.request("log.toggle")
        toggled = client.read_response(toggle_id)
        assert toggled.get("id") == toggle_id
        assert toggled.get("result", {}).get("enabled") == (not initial)
        log.info(f"✓ test_log_get_toggle passed (toggled to {not initial})")
    finally:
        client.close()


def test_stats_event_subscription():
    log.info("=== Starting test_stats_event_subscription ===")
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        log.info("Subscribing to 'stats' events")
        req_id = client.request("events.subscribe", {"event": "stats"})
        reply = client.read_message()
        assert reply.get("id") == req_id
        assert reply.get("result", {}).get("enabled") is True

        log.info("Waiting for stats event...")
        event = _read_until(
            client,
            lambda msg: msg.get("type") == "event" and msg.get("event") == "stats",
            timeout=5.0,
        )
        assert "params" in event
        log.info(f"✓ test_stats_event_subscription passed (received stats event)")
    finally:
        client.close()


def test_screen_capture_rle():
    log.info("=== Starting test_screen_capture_rle ===")
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        log.info("Requesting screen capture with RLE format")
        req_id = client.request("screen.capture", {"format": "rle"})
        reply = client.read_response(req_id, timeout=5.0)
        assert reply.get("id") == req_id
        stream_id = reply.get("result", {}).get("stream_id")
        assert stream_id is not None
        log.info(f"Screen capture started (stream_id={stream_id})")

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
        assert done, "Screen capture did not complete"
        assert total_bytes > 0, "No data received"
        log.info(f"✓ test_screen_capture_rle passed ({total_bytes} bytes received)")
    finally:
        client.close()


def test_status_get():
    log.info("=== Starting test_status_get ===")
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        log.info("Requesting status.get")
        req_id = client.request("status.get")
        reply = client.read_response(req_id)
        result = reply.get("result", {})
        assert "band" in result
        assert "mode" in result
        assert "frequency" in result
        log.info(f"✓ test_status_get passed (band={result.get('band')}, mode={result.get('mode')}, freq={result.get('frequency')})")
    finally:
        client.close()


def test_basic_controls_roundtrip():
    log.info("=== Starting test_basic_controls_roundtrip ===")
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()

        test_methods = [
            ("band.up", "band.down", "mode.up", "mode.down"),
            ("step.up", "step.down", "bandwidth.up", "bandwidth.down"),
            ("agc.up", "agc.down", "backlight.up", "backlight.down", "cal.up", "cal.down"),
            ("sleep.on", "sleep.off"),
        ]

        for methods in test_methods:
            log.info(f"Testing methods: {', '.join(methods)}")
            for method in methods:
                req_id = client.request(method)
                reply = client.read_response(req_id)
                assert reply.get("id") == req_id

        log.info(f"✓ test_basic_controls_roundtrip passed")
    finally:
        client.close()


def test_memory_list():
    log.info("=== Starting test_memory_list ===")
    client = SerialRpcClient(PORT)
    try:
        client.switch_mode()
        log.info("Requesting memory.list")
        req_id = client.request("memory.list")
        reply = client.read_response(req_id)
        memories = reply.get("result", {}).get("memories", [])
        assert isinstance(memories, list)
        log.info(f"✓ test_memory_list passed ({len(memories)} memories)")
    finally:
        client.close()
