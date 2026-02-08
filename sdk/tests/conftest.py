"""Pytest configuration for ATS-Mini SDK tests"""
import asyncio
import logging
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def pytest_configure(config):
    """Enable debug logging if ATSMINI_DEBUG is set"""
    if os.getenv("ATSMINI_DEBUG", "").lower() in ("1", "true", "yes"):
        # Enable log output to console during tests
        config.option.log_cli = True
        config.option.log_cli_level = "DEBUG"


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Setup test logging"""
    # Configure test logger - pytest will handle output via log_cli
    test_logger = logging.getLogger("test")

    # Set level based on environment
    debug_enabled = os.getenv("ATSMINI_DEBUG", "").lower() in ("1", "true", "yes")
    test_logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)

    # Also configure SDK logger level
    sdk_logger = logging.getLogger("ats_sdk")
    sdk_logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)

    if debug_enabled:
        test_logger.info("Debug logging enabled (ATSMINI_DEBUG=1)")

    yield test_logger


@pytest.fixture(scope="session", autouse=True)
def enable_ble_mode():
    """Enable BLE mode on device before running BLE tests."""
    port = os.getenv("ATSMINI_PORT")
    skip_ble = os.getenv("ATSMINI_SKIP_BLE", "").lower() in ("1", "true", "yes")

    # Only attempt to enable BLE if we have a port and BLE tests aren't skipped
    if not port or skip_ble:
        yield
        return

    logger = logging.getLogger("test.setup")

    async def _enable_ble():
        try:
            from ats_sdk import AsyncSerialRpc, Radio

            logger.info(f"Enabling BLE mode on device at {port}")
            async with AsyncSerialRpc(port) as transport:
                await transport.switch_mode()
                await asyncio.sleep(0.5)
                radio = Radio(transport)

                # Check current BLE mode
                current_mode = await radio.get_ble_mode()
                if current_mode.get("index") == 1:
                    logger.info("BLE already enabled (Ad hoc mode)")
                else:
                    # Enable BLE (value=1 for "Ad hoc")
                    logger.info("Enabling BLE (Ad hoc mode)")
                    await radio.set_ble_mode(1)
                    logger.info("BLE enabled successfully")
        except Exception as e:
            logger.warning(f"Could not enable BLE mode: {e}")
            logger.warning("BLE tests may fail if BLE is not already enabled")

    # Run async setup
    try:
        asyncio.run(_enable_ble())
    except Exception as e:
        logger = logging.getLogger("test.setup")
        logger.warning(f"Failed to enable BLE: {e}")

    yield
