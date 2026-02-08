import asyncio
import logging
import os
import random

import pytest

from ats_sdk import AsyncSerialRpc, Radio, RpcError

# Test logger
log = logging.getLogger("test.rpc_serial")


PORT = os.getenv("ATSMINI_PORT", "/dev/ttyUSB0")
pytestmark = pytest.mark.skipif(not PORT, reason="ATSMINI_PORT not set")


async def _read_until(client: AsyncSerialRpc, predicate, timeout: float = 5.0):
    """Helper to read messages until predicate is satisfied."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        message = await client.read_message(timeout=remaining)
        if predicate(message):
            return message
    raise TimeoutError("Timed out waiting for message")


@pytest.mark.asyncio
async def test_volume_set():
    log.info("=== Starting test_volume_set ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        volume = random.randint(0, 16)
        log.info(f"Testing volume.set with value={volume}")
        req_id = await client.request("volume.set", {"value": volume})
        message = await client.read_response(req_id)
        assert message.get("id") == req_id
        assert message.get("result", {}).get("volume") == volume
        log.info("✓ test_volume_set passed")


@pytest.mark.asyncio
async def test_capabilities_get():
    log.info("=== Starting test_capabilities_get ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        log.info("Requesting capabilities.get")
        req_id = await client.request("capabilities.get")
        message = await client.read_response(req_id)
        assert message.get("id") == req_id
        result = message.get("result", {})
        assert result.get("rpc_version") == 1
        assert "formats" in result
        assert "transports" in result
        log.info(f"✓ test_capabilities_get passed (rpc_version={result.get('rpc_version')})")


@pytest.mark.asyncio
async def test_log_get_toggle():
    log.info("=== Starting test_log_get_toggle ===")
    async with AsyncSerialRpc(PORT) as client:
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
        log.info(f"✓ test_log_get_toggle passed (toggled to {not initial})")


@pytest.mark.asyncio
async def test_stats_event_subscription():
    log.info("=== Starting test_stats_event_subscription ===")
    async with AsyncSerialRpc(PORT) as client:
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
        log.info(f"✓ test_stats_event_subscription passed (received stats event)")


@pytest.mark.asyncio
async def test_screen_capture_rle():
    log.info("=== Starting test_screen_capture_rle ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        log.info("Requesting screen capture with RLE format")
        req_id = await client.request("screen.capture", {"format": "rle"})
        reply = await client.read_response(req_id, timeout=5.0)
        assert reply.get("id") == req_id
        stream_id = reply.get("result", {}).get("stream_id")
        assert stream_id is not None
        log.info(f"Screen capture started (stream_id={stream_id})")

        total_bytes = 0
        done = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10.0
        while loop.time() < deadline and not done:
            msg = await client.read_message(timeout=5.0)
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


@pytest.mark.asyncio
async def test_status_get():
    log.info("=== Starting test_status_get ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        log.info("Requesting status.get")
        req_id = await client.request("status.get")
        reply = await client.read_response(req_id)
        result = reply.get("result", {})
        assert "band" in result
        assert "mode" in result
        assert "frequency" in result
        log.info(f"✓ test_status_get passed (band={result.get('band')}, mode={result.get('mode')}, freq={result.get('frequency')})")


@pytest.mark.asyncio
async def test_basic_controls_roundtrip():
    log.info("=== Starting test_basic_controls_roundtrip ===")
    async with AsyncSerialRpc(PORT) as client:
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

        log.info(f"✓ test_basic_controls_roundtrip passed")


@pytest.mark.asyncio
async def test_memory_list():
    log.info("=== Starting test_memory_list ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        log.info("Requesting memory.list")
        req_id = await client.request("memory.list")
        reply = await client.read_response(req_id)
        memories = reply.get("result", {}).get("memories", [])
        assert isinstance(memories, list)
        log.info(f"✓ test_memory_list passed ({len(memories)} memories)")


# ---------------------------------------------------------------------------
# Settings tests (using Radio wrapper)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_get():
    log.info("=== Starting test_settings_get ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        radio = Radio(client)
        settings = await radio.get_all_settings()
        expected_keys = [
            "volume", "frequency", "band", "mode", "step", "bandwidth",
            "agc", "squelch", "theme", "brightness", "sleep_timeout",
            "sleep_mode", "rds_mode", "utc_offset", "fm_region",
            "ui_layout", "zoom_menu", "scroll_direction",
            "usb_mode", "ble_mode", "wifi_mode",
        ]
        for key in expected_keys:
            assert key in settings, f"missing key: {key}"
        assert isinstance(settings["band"], dict)
        assert "index" in settings["band"]
        assert "name" in settings["band"]
        log.info(f"✓ test_settings_get passed ({len(settings)} fields)")


@pytest.mark.asyncio
async def test_squelch_roundtrip():
    log.info("=== Starting test_squelch_roundtrip ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        radio = Radio(client)
        original = await radio.get_squelch()
        test_val = 10 if original != 10 else 20
        result = await radio.set_squelch(test_val)
        assert result == test_val
        readback = await radio.get_squelch()
        assert readback == test_val
        await radio.set_squelch(original)
        log.info(f"✓ test_squelch_roundtrip passed ({original} -> {test_val} -> {original})")


@pytest.mark.asyncio
async def test_theme_roundtrip():
    log.info("=== Starting test_theme_roundtrip ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        radio = Radio(client)
        theme = await radio.get_theme()
        assert "index" in theme
        assert "name" in theme
        assert "count" in theme
        original_idx = theme["index"]
        test_idx = 1 if original_idx != 1 else 0
        result = await radio.set_theme(test_idx)
        assert result["index"] == test_idx
        assert "name" in result
        await radio.set_theme(original_idx)
        log.info(f"✓ test_theme_roundtrip passed (idx {original_idx} -> {test_idx} -> {original_idx})")


@pytest.mark.asyncio
async def test_brightness_roundtrip():
    log.info("=== Starting test_brightness_roundtrip ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        radio = Radio(client)
        original = await radio.get_brightness()
        test_val = 100 if original != 100 else 150
        result = await radio.set_brightness(test_val)
        assert result == test_val
        await radio.set_brightness(original)
        log.info(f"✓ test_brightness_roundtrip passed ({original} -> {test_val} -> {original})")


@pytest.mark.asyncio
async def test_band_get_set():
    log.info("=== Starting test_band_get_set ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        radio = Radio(client)
        band = await radio.get_band()
        assert "index" in band
        assert "name" in band
        assert "count" in band
        original_idx = band["index"]
        log.info(f"Current band: {band['name']} (idx={original_idx})")
        test_idx = 1 if original_idx != 1 else 0
        result = await radio.set_band(test_idx)
        assert result["index"] == test_idx
        await radio.set_band(original_idx)
        log.info(f"✓ test_band_get_set passed")


@pytest.mark.asyncio
async def test_frequency_roundtrip():
    log.info("=== Starting test_frequency_roundtrip ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        radio = Radio(client)
        freq_info = await radio.get_frequency()
        assert "frequency" in freq_info
        original = freq_info["frequency"]
        log.info(f"Current freq: {original}")
        # Set to current frequency to avoid out-of-band errors on unknown band ranges
        result = await radio.set_frequency(original)
        assert result.get("frequency") == original
        log.info(f"✓ test_frequency_roundtrip passed")


@pytest.mark.asyncio
async def test_zoom_menu_roundtrip():
    log.info("=== Starting test_zoom_menu_roundtrip ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        radio = Radio(client)
        original = await radio.get_zoom_menu()
        toggled = not original
        result = await radio.set_zoom_menu(toggled)
        assert result == toggled
        readback = await radio.get_zoom_menu()
        assert readback == toggled
        await radio.set_zoom_menu(original)
        log.info(f"✓ test_zoom_menu_roundtrip passed ({original} -> {toggled} -> {original})")


@pytest.mark.asyncio
async def test_invalid_setting_value():
    log.info("=== Starting test_invalid_setting_value ===")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        radio = Radio(client)
        # Firmware returns error when theme index is out of bounds
        with pytest.raises((RpcError, ValueError)):  # ValueError if CBOR decode fails
            await radio.set_theme(255)
        log.info("✓ test_invalid_setting_value passed")
