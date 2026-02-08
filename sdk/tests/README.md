# ATS-Mini SDK Tests

Integration tests for the ATS-Mini Python SDK requiring hardware connection.

## Test Setup

### Prerequisites

1. **Device connection**: Connect ATS-Mini device via USB
2. **Environment variables**:
   - `ATSMINI_PORT`: Serial port path (required)
     - Linux example: `/dev/ttyACM0`
     - macOS example: `/dev/cu.usbmodem1101`
   - `ATSMINI_DEBUG`: Enable debug logging (`1`, `true`, or `yes`)
   - `ATSMINI_SKIP_BLE`: Skip BLE tests (`1`, `true`, or `yes`)
   - `ATSMINI_BLE_DEVICE`: BLE device name (default: `ATS-Mini`)

### Automatic BLE Enablement

The test suite includes an **automatic BLE enablement fixture** (`enable_ble_mode` in `conftest.py`) that:

- Runs once per test session before any tests execute
- Connects to the device via serial (using `ATSMINI_PORT`)
- Checks if BLE mode is already enabled
- Enables BLE (Ad hoc mode) if not already active
- Gracefully handles failures (logs warning but continues)

This ensures BLE tests can run without manual device configuration.

### Running Tests

```bash
# Run all tests
ATSMINI_PORT=/dev/ttyACM0 pytest sdk/tests/

# Run only serial tests
ATSMINI_PORT=/dev/ttyACM0 pytest sdk/tests/test_rpc_serial.py

# Run only BLE tests (requires BLE adapter)
ATSMINI_PORT=/dev/ttyACM0 pytest sdk/tests/test_rpc_ble.py

# Skip BLE tests
ATSMINI_PORT=/dev/ttyACM0 ATSMINI_SKIP_BLE=1 pytest sdk/tests/

# Enable debug logging
ATSMINI_PORT=/dev/ttyACM0 ATSMINI_DEBUG=1 pytest sdk/tests/ -v
```


## Test Structure

- `test_rpc_serial.py` - Serial transport tests
- `test_rpc_ble.py` - Bluetooth (BLE) transport tests
- `test_rpc_ws.py` - WebSocket transport tests
- `conftest.py` - Pytest configuration and fixtures

## Notes

- All tests are **integration tests** requiring physical hardware
- Tests use the CBOR-RPC protocol (activated with `0x1E` switch byte)
- BLE tests require a Bluetooth adapter on the host machine
- Serial and BLE tests can run simultaneously as they use different transports
