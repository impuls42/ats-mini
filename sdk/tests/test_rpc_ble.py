import asyncio
import logging
import os
import random

import pytest

from ats_sdk import AsyncBleRpc

# Test logger
log = logging.getLogger("test.rpc_ble")


DEVICE_NAME = os.getenv("ATSMINI_BLE_DEVICE", "ATS-Mini")
SKIP_BLE = os.getenv("ATSMINI_SKIP_BLE", "").lower() in ("1", "true", "yes")

pytestmark = pytest.mark.skipif(SKIP_BLE, reason="BLE tests disabled (set ATSMINI_BLE_DEVICE)")


async def _read_until(client: AsyncBleRpc, predicate, timeout: float = 5.0):
    """Helper to read messages until predicate is satisfied."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        message = await client.read_message(timeout=remaining)
        if predicate(message):
            return message
    raise TimeoutError("Timed out waiting for message")


@pytest.mark.asyncio
async def test_ble_volume_set():
    log.info("=== Starting test_ble_volume_set ===")
    async with AsyncBleRpc(DEVICE_NAME, scan_timeout=10.0) as client:
        await client.switch_mode()
        volume = random.randint(0, 16)
        log.info(f"Testing volume.set with value={volume}")
        req_id = await client.request("volume.set", {"value": volume})
        message = await client.read_response(req_id)
        assert message.get("id") == req_id
        assert message.get("result", {}).get("volume") == volume
        log.info("✓ test_ble_volume_set passed")


@pytest.mark.asyncio
async def test_ble_capabilities_get():
    log.info("=== Starting test_ble_capabilities_get ===")
    async with AsyncBleRpc(DEVICE_NAME, scan_timeout=10.0) as client:
        await client.switch_mode()
        log.info("Requesting capabilities.get")
        req_id = await client.request("capabilities.get")
        message = await client.read_response(req_id)
        assert message.get("id") == req_id
        result = message.get("result", {})
        assert result.get("rpc_version") == 1
        assert "formats" in result
        assert "transports" in result
        # Verify BLE is listed in transports
        assert "ble" in result.get("transports", [])
        log.info(f"✓ test_ble_capabilities_get passed (rpc_version={result.get('rpc_version')})")


@pytest.mark.asyncio
async def test_ble_log_get_toggle():
    log.info("=== Starting test_ble_log_get_toggle ===")
    async with AsyncBleRpc(DEVICE_NAME, scan_timeout=10.0) as client:
        await client.switch_mode()
        log.info("Getting initial log state")
        get_id = await client.request("log.get")
        reply = await client.read_response(get_id)
        assert reply.get("id") == get_id
        initial = reply.get("result", {}).get("enabled")
        log.info(f"Initial log state: {initial}")

        log.info("Toggling log state")
        toggle_id = await client.request("log.toggle")
        toggled = await client.read_response(toggle_id)
        assert toggled.get("id") == toggle_id
        assert toggled.get("result", {}).get("enabled") == (not initial)
        log.info(f"✓ test_ble_log_get_toggle passed (toggled to {not initial})")


@pytest.mark.asyncio
async def test_ble_stats_event_subscription():
    log.info("=== Starting test_ble_stats_event_subscription ===")
    async with AsyncBleRpc(DEVICE_NAME, scan_timeout=10.0) as client:
        await client.switch_mode()
        log.info("Subscribing to 'stats' events")
        req_id = await client.request("events.subscribe", {"event": "stats"})
        reply = await client.read_message()
        assert reply.get("id") == req_id
        assert reply.get("result", {}).get("enabled") is True

        log.info("Waiting for stats event...")
        event = await _read_until(
            client,
            lambda msg: msg.get("type") == "event" and msg.get("event") == "stats",
            timeout=5.0,
        )
        assert "params" in event
        log.info(f"✓ test_ble_stats_event_subscription passed (received stats event)")


@pytest.mark.asyncio
async def test_ble_screen_capture_rle():
    """Test screen capture over BLE - validates chunking and reassembly."""
    log.info("=== Starting test_ble_screen_capture_rle ===")
    async with AsyncBleRpc(DEVICE_NAME, scan_timeout=10.0) as client:
        await client.switch_mode()
        log.info("Requesting screen capture with RLE format")
        req_id = await client.request("screen.capture", {"format": "rle"})
        reply = await client.read_response(req_id, timeout=5.0)
        assert reply.get("id") == req_id
        stream_id = reply.get("result", {}).get("stream_id")
        assert stream_id is not None
        log.info(f"Screen capture started (stream_id={stream_id})")

        total_bytes = 0
        chunks_received = 0
        done = False
        deadline = asyncio.get_event_loop().time() + 15.0  # Longer timeout for BLE
        while asyncio.get_event_loop().time() < deadline and not done:
            msg = await client.read_message(timeout=5.0)
            if msg.get("type") != "event":
                continue
            if msg.get("event") == "screen.chunk":
                params = msg.get("params", {})
                if params.get("stream_id") == stream_id:
                    data = params.get("data", b"")
                    total_bytes += len(data)
                    chunks_received += 1
            elif msg.get("event") == "screen.done":
                params = msg.get("params", {})
                if params.get("stream_id") == stream_id:
                    done = True
        assert done, "Screen capture did not complete"
        assert total_bytes > 0, "No data received"
        log.info(f"✓ test_ble_screen_capture_rle passed ({total_bytes} bytes in {chunks_received} chunks)")


@pytest.mark.asyncio
async def test_ble_status_get():
    log.info("=== Starting test_ble_status_get ===")
    async with AsyncBleRpc(DEVICE_NAME, scan_timeout=10.0) as client:
        await client.switch_mode()
        log.info("Requesting status.get")
        req_id = await client.request("status.get")
        reply = await client.read_response(req_id)
        result = reply.get("result", {})
        assert "band" in result
        assert "mode" in result
        assert "frequency" in result
        log.info(f"✓ test_ble_status_get passed (band={result.get('band')}, mode={result.get('mode')}, freq={result.get('frequency')})")


@pytest.mark.asyncio
async def test_ble_basic_controls_roundtrip():
    log.info("=== Starting test_ble_basic_controls_roundtrip ===")
    async with AsyncBleRpc(DEVICE_NAME, scan_timeout=10.0) as client:
        await client.switch_mode()

        test_methods = [
            ("band.up", "band.down", "mode.up", "mode.down"),
            ("step.up", "step.down", "bandwidth.up", "bandwidth.down"),
            ("agc.up", "agc.down", "backlight.up", "backlight.down", "cal.up", "cal.down"),
            ("sleep.on", "sleep.off"),
        ]

        for methods in test_methods:
            log.info(f"Testing methods: {', '.join(methods)}")
            for method in methods:
                req_id = await client.request(method)
                reply = await client.read_response(req_id)
                assert reply.get("id") == req_id

        log.info(f"✓ test_ble_basic_controls_roundtrip passed")


@pytest.mark.asyncio
async def test_ble_memory_list():
    log.info("=== Starting test_ble_memory_list ===")
    async with AsyncBleRpc(DEVICE_NAME, scan_timeout=10.0) as client:
        await client.switch_mode()
        log.info("Requesting memory.list")
        req_id = await client.request("memory.list")
        reply = await client.read_response(req_id)
        memories = reply.get("result", {}).get("memories", [])
        assert isinstance(memories, list)
        log.info(f"✓ test_ble_memory_list passed ({len(memories)} memories)")


@pytest.mark.asyncio
async def test_ble_connection_error():
    """Test BLE connection error handling when device is not found."""
    log.info("=== Starting test_ble_connection_error ===")

    # Try to connect to non-existent device
    client = AsyncBleRpc("NonExistent-Device-12345", scan_timeout=2.0)

    with pytest.raises(ConnectionError) as exc_info:
        await client.connect()

    assert "not found" in str(exc_info.value).lower()
    log.info("✓ test_ble_connection_error passed (correctly raised ConnectionError)")
