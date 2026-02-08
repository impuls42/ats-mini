# ATS-Mini SDK Logging Guide

The ATS-Mini SDK includes optional verbose/debug logging to help diagnose communication issues, track RPC message flow, and understand device reset behavior.

## Quick Start

Enable debug logging by setting the `ATSMINI_DEBUG` environment variable:

```bash
# Run tests with debug logging
ATSMINI_DEBUG=1 ATSMINI_PORT=/dev/cu.usbmodem1101 pytest sdk/tests/

# Run specific test with debug output
ATSMINI_DEBUG=1 ATSMINI_PORT=/dev/cu.usbmodem1101 pytest sdk/tests/test_rpc_serial.py::test_volume_set -v
```

## What Gets Logged

### SDK Level (ats_sdk)

When `ATSMINI_DEBUG=1` is set, the SDK logs per-transport (e.g. `ats_sdk.AsyncSerialRpc`, `ats_sdk.AsyncBleRpc`):

**Connection Events:**
- Serial port opening/closing, DTR/RTS signal states
- BLE device discovery and connection
- WebSocket connection status
- Input buffer flushes
- CBOR-RPC mode activation

**Message Flow:**
- `→ REQUEST` - Outgoing RPC requests with ID, method, params, and size
- `← RESPONSE` - Incoming responses with ID, result, or error
- `← EVENT` - Incoming event notifications (stats, screen.chunk, etc.)

**Timing & Diagnostics:**
- Message timeouts with byte counts
- Skipped events while waiting for responses

### Test Level (test)

Test logs show:
- Test start markers (`=== Starting test_name ===`)
- Test-specific operations (e.g., "Subscribing to 'stats' events")
- Test results with context (e.g., "✓ test_volume_set passed")
- Data received (e.g., "Screen capture: 12345 bytes received")

## Example Output

```
23:15:42.123 [ats_sdk.AsyncSerialRpc] INFO: AsyncSerialRpc connected to /dev/cu.usbmodem1101
23:15:42.234 [ats_sdk.AsyncSerialRpc] DEBUG: Switching to CBOR-RPC mode (sending 0x1E)
23:15:42.345 [ats_sdk.AsyncSerialRpc] INFO: CBOR-RPC mode activated
23:15:42.456 [test] INFO: === Starting test_volume_set ===
23:15:42.567 [ats_sdk.AsyncSerialRpc] DEBUG: → REQUEST id=1 method=volume.set params={'value': 10} (42 bytes)
23:15:42.678 [ats_sdk.AsyncSerialRpc] DEBUG: Waiting for response to request id=1 (timeout=5.0s)
23:15:42.789 [ats_sdk.AsyncSerialRpc] DEBUG: Message length: 38 bytes
23:15:42.890 [ats_sdk.AsyncSerialRpc] DEBUG: ← RESPONSE id=1 result={'volume': 10} error=None
23:15:42.901 [test] INFO: ✓ test_volume_set passed
23:15:42.912 [ats_sdk.AsyncSerialRpc] INFO: AsyncSerialRpc disconnected
```

## Detecting Device Resets

If the device actually resets between tests, you'll see:

1. **Serial reconnection messages** - Port closed/reopened
2. **Firmware boot output** - `"ETS: Entering setup()"` in serial data
3. **Longer delays** - 2-3 second boot time vs. normal 100ms connection

If you DON'T see these, the device is not resetting - only the RPC state is being reinitialized.

## Using Logging in Your Code

### Python SDK Integration

The SDK uses Python's standard `logging` module. When using the SDK outside of pytest, you need to configure handlers yourself:

```python
import asyncio
import logging
from ats_sdk import AsyncSerialRpc, Radio

# Configure logging output (needed when NOT using pytest)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)

async def main():
    async with AsyncSerialRpc("/dev/cu.usbmodem1101") as transport:
        radio = Radio(transport)
        vol = await radio.get_volume()
        print(f"Volume: {vol}")

asyncio.run(main())
```

**Or configure just the SDK logger:**

```python
import logging

# Setup handler for ats_sdk logger
logger = logging.getLogger("ats_sdk")
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    "%(asctime)s.%(msecs)03d [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
))
logger.addHandler(handler)
```

**Note:** When running under pytest, handlers are configured automatically by pytest's `log_cli` feature - you don't need to add them yourself. The `ATSMINI_DEBUG=1` env var enables debug-level output automatically via `sdk/tests/conftest.py`.

### Custom Test Logging

```python
import logging
import pytest

log = logging.getLogger("test.my_test")

@pytest.mark.asyncio
async def test_my_feature():
    log.info("Starting my test")
    # ... test code
    log.debug("Intermediate step completed")
    # ... more test code
    log.info("✓ Test passed")
```

## Pytest Options

Additional pytest logging options:

```bash
# Show all logs (including DEBUG) to console
pytest --log-cli-level=DEBUG

# Show only test output, hide SDK debug logs
pytest --log-cli-level=INFO

# Capture logs to file
pytest --log-file=test.log --log-file-level=DEBUG

# Verbose test names + logs
pytest -v --log-cli-level=DEBUG
```

## Performance Note

Debug logging adds minimal overhead (~1-2ms per message). It's safe to use during normal testing but should be disabled for performance benchmarking.

## Troubleshooting

**No logs appearing?**
- Check `ATSMINI_DEBUG` is set correctly: `echo $ATSMINI_DEBUG`
- Verify pytest is using the correct environment
- Try `pytest -s` to disable output capturing

**Too much output?**
- Use `ATSMINI_DEBUG=0` or unset the variable
- Adjust `--log-cli-level=INFO` to show only high-level events
- Filter specific loggers: `--log-cli-level=DEBUG -k test_volume_set`

**Logs interleaved with test output?**
- This is normal with `pytest -s`
- Use `--log-file` to separate logs from test results
- Or run without `-s` flag for cleaner output

**Duplicate log messages?**
- This happens if you add handlers to loggers that pytest is already capturing
- Solution: Let pytest handle output via `log_cli`, don't add your own handlers in test code
- The SDK is configured to work with pytest automatically
