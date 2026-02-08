#!/usr/bin/env python3
"""Test preparation script to enable BLE on the device."""
import asyncio
import logging
import os
import sys

# Add parent directory to path for local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ats_sdk import AsyncSerialRpc, Radio

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

PORT = os.getenv("ATSMINI_PORT", "/dev/ttyUSB0")


async def enable_ble():
    """Enable BLE mode on the device."""
    log.info(f"Connecting to device on {PORT}")
    async with AsyncSerialRpc(PORT) as client:
        await client.switch_mode()
        radio = Radio(client)

        # Get current BLE mode
        current = await radio.get_ble_mode()
        log.info(f"Current BLE mode: {current}")

        # Enable BLE (mode 1 = "Ad hoc")
        if current["index"] != 1:
            log.info("Enabling BLE (Ad hoc mode)...")
            result = await radio.set_ble_mode(1)
            log.info(f"BLE enabled: {result}")
        else:
            log.info("BLE is already enabled")

        # Verify
        final = await radio.get_ble_mode()
        log.info(f"Final BLE mode: {final}")

        if final["index"] == 1:
            log.info("✓ BLE successfully enabled")
            return True
        else:
            log.error("✗ Failed to enable BLE")
            return False


if __name__ == "__main__":
    success = asyncio.run(enable_ble())
    sys.exit(0 if success else 1)
