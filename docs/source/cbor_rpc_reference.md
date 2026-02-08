# CBOR RPC System Documentation

## Overview

The CBOR RPC system is a remote procedure call (RPC) framework implemented in the ATS-Mini firmware that enables bidirectional communication between the device and external clients over multiple transport layers. It uses CBOR (Concise Binary Object Representation) for efficient binary serialization and supports real-time control, monitoring, and screen capture functionality.

## Architecture

### Core Components

- **CborRpc.h/cpp**: Core RPC implementation with method dispatch and response handling
- **CborRpcWriter**: Transport-agnostic writer interface for sending responses
- **RemoteState**: Per-connection state management for RPC sessions
- **Transport Layers**: Serial, BLE, and WebSocket implementations

### Transport Layers

The RPC system supports three transport mechanisms:

1. **Serial (USB)**: Wired communication via USB serial port
2. **BLE (Bluetooth Low Energy)**: Wireless communication via Bluetooth
3. **WebSocket**: Web-based communication over WiFi

Each transport implements the `CborRpcWriter` interface with its own `send_frame` function.

## Protocol Specification

### Frame Format

```
[Switch Byte: 0x1E][Length: 4 bytes][CBOR Payload: Length bytes]
```

- **Switch Byte**: `0x1E` marks the beginning of a new frame
- **Length**: 32-bit big-endian length of CBOR payload
- **CBOR Payload**: JSON-like structure encoded in binary CBOR format

### Message Structure

#### Request
```cbor
{
  "method": "method.name",
  "id": 123,           // Optional request ID for responses
  "params": {          // Optional method parameters
    "key": "value"
  }
}
```

#### Response
```cbor
{
  "id": 123,           // Request ID
  "result": {          // Method result data
    "key": "value"
  }
}
```

#### Error
```cbor
{
  "id": 123,
  "error": {
    "code": -32601,
    "message": "method not found"
  }
}
```

#### Event
```cbor
{
  "type": "event",
  "event": "stats",
  "seq": 456,
  "params": {
    // Event data
  }
}
```

## Available Methods

### Radio Control

#### Frequency Management
- `frequency.get` - Get current frequency and BFO
- `frequency.set` - Set frequency (within band limits)
- `band.up` / `band.down` - Navigate bands
- `band.get` / `band.set` - Get/set band by index or name
- `mode.up` / `mode.down` - Navigate modes
- `mode.get` / `mode.set` - Get/set mode (AM/LSB/USB/FM)
- `step.up` / `step.down` - Navigate tuning steps
- `step.get` / `step.set` - Get/set step size

#### Audio Control
- `volume.up` / `volume.down` / `volume.get` / `volume.set` - Volume control (0-63)
- `squelch.get` / `squelch.set` - Squelch control (0-127)
- `agc.up` / `agc.down` / `agc.get` / `agc.set` - AGC control
- `brightness.get` / `brightness.set` - Screen brightness (10-255)

#### Advanced Settings
- `bandwidth.up` / `bandwidth.down` / `bandwidth.get` / `bandwidth.set` - Filter bandwidth
- `cal.up` / `cal.down` / `cal.get` / `cal.set` - SSB calibration (SSB only)
- `softmute.get` / `softmute.set` - Soft mute settings (AM/SSB only)
- `avc.get` / `avc.set` - Automatic volume control (AM/SSB only)

### System Configuration

#### Device Settings
- `settings.get` - Get all device settings in bulk
- `sleep.timeout.get` / `sleep.timeout.set` - Sleep timeout (0-255 seconds)
- `sleep.on` / `sleep.off` - Control sleep mode
- `sleep.mode.get` / `sleep.mode.set` - Sleep behavior mode

#### User Interface
- `theme.get` / `theme.set` - Visual theme selection
- `ui.layout.get` / `ui.layout.set` - UI layout configuration
- `zoom.menu.get` / `zoom.menu.set` - Menu zoom toggle
- `scroll.direction.get` / `scroll.direction.set` - Scroll direction (-1 or 1)

#### Connectivity
- `usb.mode.get` / `usb.mode.set` - USB operation mode
- `ble.mode.get` / `ble.mode.set` - Bluetooth operation mode
- `wifi.mode.get` / `wifi.mode.set` - WiFi operation mode
- `fm.region.get` / `fm.region.set` - FM broadcast region (FM only)
- `rds.mode.get` / `rds.mode.set` - RDS processing mode
- `utc.offset.get` / `utc.offset.set` - UTC time offset

### Memory Management

#### Memory Slots
- `memory.list` - List all stored memory slots
- `memory.set` - Store frequency in memory slot

**memory.set parameters:**
```json
{
  "slot": 1,           // Slot number (1-based)
  "freq_hz": 7100000,  // Frequency in Hz
  "mode": 2,           // Mode index
  "band": "40M"        // Band name or index
}
```

### Status and Information

#### Device Information
- `status.get` - Current radio status (band, mode, frequency, etc.)
- `capabilities.get` - Device capabilities and supported features

**Supported events:**
- `stats` - Real-time radio statistics (RSSI, SNR, voltage, etc.)

### Screen Capture

#### Display Capture
- `screen.capture` - Capture device screen

**screen.capture parameters:**
```json
{
  "format": "binary"   // "binary" or "rle" (run-length encoded)
}
```

**Response:**
```json
{
  "stream_id": 123,
  "format": "binary",
  "width": 320,
  "height": 170
}
```

Screen data is streamed as chunked events:
```json
{
  "type": "event",
  "event": "screen.chunk",
  "seq": 456,
  "params": {
    "stream_id": 123,
    "offset": 0,
    "data": "<base64>"
  }
}
```

## Error Codes

| Code | Description |
|------|-------------|
| -32600 | Invalid Request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error (e.g., out of memory) |

## Usage Examples

### Basic Radio Control

```python
# Set frequency to 7.1 MHz
request = {
    "method": "frequency.set",
    "id": 1,
    "params": {
        "value": 7100000
    }
}

# Get current status
request = {
    "method": "status.get",
    "id": 2
}
```

### Memory Management

```python
# Store current frequency in memory slot 1
request = {
    "method": "memory.set",
    "id": 3,
    "params": {
        "slot": 1,
        "freq_hz": 7100000,
        "mode": 2,
        "band": "40M"
    }
}
```

### Screen Capture

```python
# Capture screen in binary format
request = {
    "method": "screen.capture",
    "id": 4,
    "params": {
        "format": "binary"
    }
}
```

### Event Subscription

```python
# Subscribe to statistics events
request = {
    "method": "events.subscribe",
    "id": 5,
    "params": {
        "event": "stats"
    }
}
```

## Implementation Details

### Method Dispatch

The RPC system uses a centralized method dispatcher in `cborRpcHandleFrame()` that:

1. Parses incoming CBOR frames
2. Extracts method name, parameters, and request ID
3. Dispatches to appropriate handler function
4. Formats and sends response

### State Management

Each connection maintains a `RemoteState` struct containing:
- RPC mode flag and event subscription status
- Frame parsing buffers and state
- Sequence numbers for requests and events
- Timer for periodic statistics transmission

### Transport Abstraction

The `CborRpcWriter` interface provides transport-agnostic response sending:

```c
struct CborRpcWriter {
    void *ctx;
    bool (*send_frame)(void *ctx, const uint8_t *data, size_t len);
};
```

Each transport implements its own `send_frame` function:
- Serial: Writes to stream with length prefix
- BLE: Writes to BLE characteristic
- WebSocket: Sends via WebSocket client

## Performance Considerations

- **Frame Size**: Maximum 4096 bytes per frame
- **Buffer Management**: Dynamic allocation for large responses (e.g., settings.get)
- **Chunked Streaming**: Screen capture uses chunked transfer for large data
- **Event Throttling**: Statistics events sent every 500ms when subscribed

## Security Considerations

- Input validation for all parameters
- Range checking for numeric values
- Mode-specific restrictions (e.g., FM-only operations)
- Memory bounds checking for all operations

## Extensibility

Adding new RPC methods involves:

1. Adding method name check in `cborRpcHandleFrame()`
2. Implementing parameter parsing and validation
3. Calling appropriate device functions
4. Formatting response using helper functions
5. Updating documentation

The system is designed to be easily extended with new functionality while maintaining consistency with existing patterns.
