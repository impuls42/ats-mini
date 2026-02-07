#!/usr/bin/env python3
"""Enable BLE over serial transport."""

import asyncio
import sys
import time
import serial
from ats_sdk import AsyncSerialRpc, Radio


async def main():
    # Try common serial ports
    ports = [
        "/dev/ttyUSB0",
        "/dev/ttyUSB1",
        "/dev/ttyACM0",
        "/dev/cu.usbmodem1101",  # macOS
    ]

    port = None
    ser = None

    # Try each port to find device
    for candidate in ports:
        try:
            print(f"Trying {candidate}...")
            ser = serial.Serial(candidate, 115200, timeout=1)
            time.sleep(0.5)  # Wait for connection to stabilize
            port = candidate
            print(f"✓ Connected on {port}")
            break
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            if ser:
                ser.close()
            ser = None
            continue

    if not ser:
        print("ERROR: Could not connect to device on any port")
        print("Available ports:", ports)
        sys.exit(1)

    # Switch to RPC mode by sending SWITCH_BYTE (0x1E)
    print("\nSwitching to CBOR-RPC mode...")
    ser.write(bytes([0x1E]))
    time.sleep(0.5)  # Wait for device to switch modes
    ser.close()

    # Now connect with async RPC client
    rpc = AsyncSerialRpc(port)

    try:
        print(f"Connecting RPC client on {port}...")
        await asyncio.wait_for(rpc.connect(), timeout=5.0)
        print("✓ RPC connected")

        # Create Radio object
        radio = Radio(rpc)

        # Get current BLE mode
        print("\nGetting current BLE mode...")
        current = await radio.get_ble_mode()
        print(f"Current mode: {current}")

        # Enable BLE (1 = "Ad hoc")
        print("\nEnabling BLE mode (Ad hoc)...")
        result = await radio.set_ble_mode(1)
        print(f"✓ BLE enabled: {result}")

    except asyncio.TimeoutError:
        print("ERROR: RPC connection timeout - device may not be responding")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
