# ATS-Mini Communication SDK

Fully async CBOR-RPC communication library for ATS-Mini ESP32-S3 radio devices.

## Installation

```bash
pip install -e .
```

With testing dependencies:
```bash
pip install -e ".[test]"
```

## Quick Start

### Serial Connection

```python
import asyncio
from ats_sdk import AsyncSerialRpc

async def main():
    async with AsyncSerialRpc("/dev/cu.usbmodem1101") as client:
        # Switch to CBOR-RPC mode (required for Serial and BLE)
        await client.switch_mode()

        # Set volume
        req_id = await client.request("volume.set", {"value": 12})
        response = await client.read_response(req_id)
        print(f"Volume: {response['result']['volume']}")

        # Get status
        req_id = await client.request("status.get")
        status = await client.read_response(req_id)
        print(f"Frequency: {status['result']['frequency']} kHz")

asyncio.run(main())
```

### WebSocket Connection

```python
from ats_sdk import AsyncWebSocketRpc

async def main():
    async with AsyncWebSocketRpc("ws://atsmini.local/rpc") as client:
        # No switch_mode() needed for WebSocket

        req_id = await client.request("capabilities.get")
        caps = await client.read_response(req_id)
        print(f"Firmware version: {caps['result']['version']}")

asyncio.run(main())
```

### BLE Connection

```python
from ats_sdk import AsyncBleRpc

async def main():
    # Connect by device name (scans for up to 10 seconds)
    async with AsyncBleRpc("ATS-Mini", scan_timeout=10.0) as client:
        # Switch to CBOR-RPC mode (required)
        await client.switch_mode()

        req_id = await client.request("status.get")
        status = await client.read_response(req_id)
        print(f"Mode: {status['result']['mode']}")

asyncio.run(main())
```

## API Reference

### AsyncSerialRpc

```python
AsyncSerialRpc(port: str, baudrate: int = 115200, timeout: float = 1.0)
```

**Methods:**
- `async connect()` - Open serial port
- `async close()` - Close serial port
- `async switch_mode()` - Send 0x1E byte to activate CBOR-RPC protocol
- `async request(method: str, params: dict = None) -> int` - Send RPC request, returns request ID
- `async read_response(request_id: int, timeout: float = 5.0) -> dict` - Read response for specific request
- `async read_message(timeout: float = 5.0) -> dict` - Read any message (request, response, or event)

**Parameters:**
- `port` - Serial port path (e.g., `/dev/cu.usbmodem1101`, `COM3`)
- `baudrate` - Serial baud rate (default: 115200)
- `timeout` - Read timeout in seconds (default: 1.0)

### AsyncWebSocketRpc

```python
AsyncWebSocketRpc(url: str, timeout: float = 10.0)
```

**Methods:**
- `async connect()` - Connect to WebSocket server
- `async close()` - Close WebSocket connection
- `async request(method, params) -> int` - Send RPC request
- `async read_response(request_id, timeout) -> dict` - Read response
- `async read_message(timeout) -> dict` - Read any message

**Parameters:**
- `url` - WebSocket URL (e.g., `ws://atsmini.local/rpc`)
- `timeout` - Connection timeout in seconds (default: 10.0)

**Note:** WebSocket transport does not require `switch_mode()` - it's always in CBOR-RPC mode.

### AsyncBleRpc

```python
AsyncBleRpc(device_name: str = "ATS-Mini", scan_timeout: float = 10.0, timeout: float = 5.0)
```

**Methods:**
- `async connect()` - Scan for and connect to BLE device
- `async close()` - Disconnect from BLE device
- `async switch_mode()` - Send 0x1E byte to activate CBOR-RPC protocol
- `async request(method, params) -> int` - Send RPC request
- `async read_response(request_id, timeout) -> dict` - Read response
- `async read_message(timeout) -> dict` - Read any message

**Parameters:**
- `device_name` - BLE device name to search for (default: "ATS-Mini")
- `scan_timeout` - Maximum time to scan for device in seconds (default: 10.0)
- `timeout` - Read timeout in seconds (default: 5.0)

**Technical Details:**
- Uses Nordic UART Service (NUS) for communication
- Service UUID: `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- Automatically handles BLE MTU chunking for large frames
- Supports disconnection detection

### Common Methods

All transports inherit from `AsyncRpcTransport` and support:

**Context Manager:**
```python
async with AsyncSerialRpc(port) as client:
    # Connection opened automatically
    await client.request(...)
# Connection closed automatically
```

**Event Monitoring:**
```python
# Read all messages in a loop
while True:
    msg = await client.read_message(timeout=30.0)
    if msg.get("type") == "event":
        print(f"Event: {msg['event']}, params: {msg['params']}")
```

## RPC Methods

Common RPC methods supported by the firmware:

**Status and Control:**
- `status.get` - Get current radio status (frequency, mode, volume, RSSI, SNR, etc.)
- `volume.set` - Set volume level (params: `{"value": 0-63}`)
- `volume.up` / `volume.down` - Adjust volume

**Tuner:**
- `tuner.frequency.set` - Set frequency (params: `{"value": frequency_khz}`)
- `band.up` / `band.down` - Change band
- `mode.up` / `mode.down` - Change modulation mode
- `step.up` / `step.down` - Change tuning step
- `bandwidth.up` / `bandwidth.down` - Change filter bandwidth

**System:**
- `capabilities.get` - Get firmware capabilities and version
- `log.get` - Get debug logs (params: `{"toggle": true/false}`)
- `screen.capture` - Get screen buffer (RLE compressed)
- `memory.list` - List stored memory channels

**Events:**
The firmware sends periodic events:
- `stats` - Radio statistics (frequency, RSSI, SNR, mode)

## Testing

Run integration tests (requires connected hardware):

```bash
# Serial tests
ATSMINI_PORT=/dev/cu.usbmodem1101 pytest sdk/tests/test_rpc_serial.py -v

# WebSocket tests
ATSMINI_WS_URL=ws://atsmini.local/rpc pytest sdk/tests/test_rpc_ws.py -v

# BLE tests
ATSMINI_BLE_DEVICE=ATS-Mini pytest sdk/tests/test_rpc_ble.py -v

# All tests
ATSMINI_PORT=/dev/cu.usbmodem1101 \
ATSMINI_WS_URL=ws://atsmini.local/rpc \
ATSMINI_BLE_DEVICE=ATS-Mini \
pytest sdk/tests/ -v
```

**Environment Variables:**
- `ATSMINI_PORT` - Serial port path (required for serial tests)
- `ATSMINI_WS_URL` - WebSocket URL (required for WebSocket tests)
- `ATSMINI_BLE_DEVICE` - BLE device name (default: "ATS-Mini")
- `ATSMINI_SKIP_BLE` - Set to skip BLE tests (useful if no BLE hardware)
- `ATSMINI_DEBUG` - Enable debug logging (set to "1")

## Module Structure

```
ats_sdk/
├── __init__.py           # Main exports
├── base.py               # AsyncRpcTransport abstract base class
├── framing.py            # CBOR frame encoding/decoding
└── transports/
    ├── __init__.py       # Transport exports
    ├── serial.py         # AsyncSerialRpc
    ├── websocket.py      # AsyncWebSocketRpc
    └── ble.py            # AsyncBleRpc
```

## Dependencies

- **cbor2** >= 5.4.0 - CBOR encoding/decoding
- **pyserial** >= 3.5 - Serial port communication
- **websockets** >= 12.0 - WebSocket client
- **bleak** >= 0.21.0 - Bluetooth Low Energy (BLE) communication

**Python Version:** 3.11+

## Protocol Details

**Frame Format:**
- 4-byte big-endian length prefix
- CBOR-encoded payload

**Mode Switching:**
Serial and BLE transports require sending `0x1E` (SWITCH_BYTE) to activate CBOR-RPC mode. WebSocket is always in CBOR-RPC mode.

**Request Format:**
```python
{
    "jsonrpc": "2.0",
    "method": "volume.set",
    "params": {"value": 12},
    "id": 1
}
```

**Response Format:**
```python
{
    "jsonrpc": "2.0",
    "result": {"volume": 12},
    "id": 1
}
```

**Event Format:**
```python
{
    "type": "event",
    "event": "stats",
    "params": {"frequency": 9600, "rssi": 45, "snr": 12}
}
```
