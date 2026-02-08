#!/usr/bin/env python3
"""Enable BLE mode on ATS-Mini device for testing.

Usage:
    python sdk/enable_ble.py [PORT]

Environment:
    ATSMINI_PORT - Serial port (default: /dev/ttyUSB0)
"""

import asyncio
import logging
import os
import sys

from ats_sdk import AsyncSerialRpc, Radio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("enable_ble")


async def enable_ble(port: str):
    """Enable BLE mode on the device."""
    log.info(f"Connecting to device on {port}")

    async with AsyncSerialRpc(port) as transport:
        log.info("Switching to CBOR-RPC mode")
        await transport.switch_mode()

        # Give device time to stabilize after mode switch
        await asyncio.sleep(0.5)

        radio = Radio(transport)

        # Get current BLE mode
        log.info("Getting current BLE mode")
        current_mode = await radio.get_ble_mode()
        log.info(f"Current BLE mode: {current_mode}")

        # Check if already enabled
        if current_mode.get("index") == 1:
            log.info("BLE is already enabled (Ad hoc mode)")
            return True

        # Enable BLE (value=1 for "Ad hoc")
        log.info("Enabling BLE (Ad hoc mode)")
        result = await radio.set_ble_mode(1)
        log.info(f"BLE mode set: {result}")

        # Verify
        if result.get("index") == 1:
            log.info("✓ BLE successfully enabled")
            return True
        else:
            log.error("✗ Failed to enable BLE")
            return False


async def main():
    # Get port from command line or environment
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = os.getenv("ATSMINI_PORT", "/dev/ttyUSB0")

    try:
        success = await enable_ble(port)
        sys.exit(0 if success else 1)
    except Exception as e:
        log.error(f"Error enabling BLE: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
