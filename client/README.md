# ATS-Mini TUI Client

Modern terminal user interface (TUI) for controlling ATS-Mini ESP32-S3 radio devices. Built with [Textual](https://textual.textualize.io/) for a beautiful, responsive terminal experience.

## Features

- **Live Status Panel** - Real-time display of frequency, mode, volume, RSSI, SNR, and more
- **Connection Status** - Visual indicator showing connection state and transport type
- **Event Log** - Scrollable log with timestamps for all RPC events and system messages
- **Quick Controls** - Buttons for volume, band, mode adjustments
- **Multiple Transports** - Connect via Serial, WebSocket, or BLE
- **Keyboard Shortcuts** - Fast access to common operations
- **Async Architecture** - Non-blocking UI that stays responsive

## Installation

Requires Python 3.11+ and the ATS-Mini SDK:

```bash
# Install SDK first
pip install -e ../sdk

# Install TUI client
pip install -e .
```

## Usage

### Basic Launch

```bash
atsmini
```

Once running, use the command input at the bottom to control the app:

```
connect serial /dev/cu.usbmodem1101
```

### Auto-Connect on Launch

```bash
# Serial connection
atsmini --serial /dev/cu.usbmodem1101

# WebSocket connection
atsmini --ws ws://atsmini.local/rpc

# BLE connection (default device name: ATS-Mini)
atsmini --ble

# BLE with custom device name
atsmini --ble MyRadio
```

## UI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ ATS-Mini TUI                                      01:23:45 PM    │ ← Header
├─────────────────────────────────────────────────────────────────┤
│ 🟢 Connected via Serial                                         │ ← Connection Status
├─────────────────────────────────────────────────────────────────┤
│ Radio Status                                                     │
│                                                                  │
│ Frequency: 9600 kHz    Mode: AM    Band: MW                     │ ← Live Status Panel
│ Volume: 12    Step: 5 kHz    BW: 4 kHz                          │
│ RSSI: 45 dBµV    SNR: 12 dB                                     │
├──────────────────────────────────┬──────────────────────────────┤
│ Event Log                        │ Quick Controls               │
│                                  │                              │
│ 01:23:40.123 stats 9600kHz ...   │ [ Volume + ]                │
│ 01:23:41.456 Connected via ...   │ [ Volume - ]                │
│ 01:23:42.789 Volume set to 12    │ [ Band ↑ ]                  │ ← Controls
│ ...                              │ [ Band ↓ ]                  │
│                                  │ [ Mode ↑ ]                  │
│                                  │ [ Mode ↓ ]                  │
│                                  │ [ Refresh Status ]          │
├──────────────────────────────────┴──────────────────────────────┤
│ Command: (e.g., 'connect serial /dev/cu.usbmodem1101', ...)    │
│ [_________________________________________________]              │ ← Command Input
├─────────────────────────────────────────────────────────────────┤
│ ^C Quit ^D Disconnect ^S Status  ↑/↓ Vol+/-                     │ ← Footer/Shortcuts
└─────────────────────────────────────────────────────────────────┘
```

## Available Commands

Type these commands in the command input area at the bottom:

### Connection Commands

```
connect serial <port>       Connect via serial port
                           Example: connect serial /dev/cu.usbmodem1101

connect ws <url>           Connect via WebSocket
                           Example: connect ws ws://atsmini.local/rpc

connect ble [name]         Connect via Bluetooth Low Energy
                           Example: connect ble ATS-Mini
                           Example: connect ble (defaults to "ATS-Mini")

disconnect                 Disconnect from device
```

### Radio Control Commands

```
status                     Get current device status

volume <0-63>             Set volume to specific level
                          Example: volume 12

band up                   Move to next band
band down                 Move to previous band

mode up                   Change to next modulation mode
mode down                 Change to previous modulation mode

step up                   Increase tuning step
step down                 Decrease tuning step

bandwidth up              Increase filter bandwidth
bandwidth down            Decrease filter bandwidth
```

### Help

```
help                      Show help message with all commands
```

## Keyboard Shortcuts

- **Ctrl+C** - Quit application
- **Ctrl+D** - Disconnect from device
- **Ctrl+S** - Get device status
- **↑ / ↓** - Volume up/down

## Transport Details

### Serial

Most common connection method using USB cable:

```
connect serial /dev/cu.usbmodem1101    # macOS
connect serial /dev/ttyACM0            # Linux
connect serial COM3                    # Windows
```

**Technical:** 115200 baud, switches to CBOR-RPC mode with 0x1E byte

### WebSocket

Wireless connection when device is on same network:

```
connect ws ws://atsmini.local/rpc      # mDNS hostname
connect ws ws://192.168.1.100/rpc      # Direct IP
```

**Technical:** Always in CBOR-RPC mode, no mode switch needed

### Bluetooth Low Energy (BLE)

Wireless connection using Nordic UART Service:

```
connect ble                            # Default: "ATS-Mini"
connect ble MyRadio                    # Custom device name
```

**Technical:** Scans for BLE device by name (10s timeout), switches to CBOR-RPC mode

## Event Monitoring

The TUI automatically monitors for events sent by the firmware:

- **stats** - Periodic radio statistics (frequency, RSSI, SNR)
- Updates appear in the Event Log with timestamps
- Status panel updates automatically when stats events arrive

## Examples

### Basic Serial Workflow

```bash
# Launch TUI
atsmini

# In TUI command input:
> connect serial /dev/cu.usbmodem1101
> volume 12
> band up
> mode up
> status
```

### Auto-Connect and Control via BLE

```bash
# Launch with auto-connect
atsmini --ble

# Device connects automatically, then use buttons or commands
# Click "Volume +" button or press ↑ key
```

### Multi-Device Testing

```bash
# Terminal 1: Serial connection
atsmini --serial /dev/cu.usbmodem1101

# Terminal 2: WebSocket connection (if firmware has WiFi)
atsmini --ws ws://atsmini.local/rpc

# Both can control the same device simultaneously
```

## Troubleshooting

**"Connection failed: [Errno 2] could not open port"**
- Check device is connected: `lsusb` (Linux/macOS) or Device Manager (Windows)
- Verify port path is correct
- Ensure no other program is using the serial port

**"BLE device not found"**
- Check device is powered on
- Ensure BLE is enabled in firmware
- Try longer scan timeout: modify `scan_timeout` in code (default: 10.0s)
- Verify device name matches (case-sensitive)

**"Not connected"**
- Type `connect` command before attempting control commands
- Check connection status indicator at top (🟢 = connected, 🔴 = disconnected)

## Dependencies

- **ats-sdk** >= 0.2.0 - Async CBOR-RPC SDK
- **textual** >= 0.47.0 - Modern TUI framework

Python 3.11+ required.

## Architecture

The TUI uses fully async architecture:
- All I/O operations are non-blocking
- Background task monitors events from device
- Reactive properties update UI automatically
- Multiple transports share common interface (AsyncRpcTransport)

See [../sdk/README.md](../sdk/README.md) for SDK documentation.
