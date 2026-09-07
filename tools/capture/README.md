# ATS-Mini Screenshot Capture Tools

Python utilities for capturing screenshots from ATS-Mini receiver over BLE or serial.

## Requirements

```bash
# For BLE capture
pip install bleak

# For serial capture
pip install pyserial

# For both
pip install bleak pyserial
```

## Tools

### atsmini_bleak_capture.py

Capture a single screenshot via BLE or serial.

**Usage:**

```bash
# BLE capture (binary mode, auto-detected for 'c' command)
./atsmini_bleak_capture.py --cmd c > screenshot.bmp

# BLE capture (hex mode, legacy)
./atsmini_bleak_capture.py --cmd C > screenshot.bmp

# Specify device explicitly
./atsmini_bleak_capture.py --device "12:34:56:78:90:AB" --cmd c > screenshot.bmp

# Verbose output for debugging
./atsmini_bleak_capture.py --cmd c -vv > screenshot.bmp
```

**Options:**
- `--device` - Device address/UUID (optional, will scan for ATS-Mini by name)
- `--name` - Device name to scan for (default: ATS-Mini)
- `--cmd` - Capture command: `C` (hex) or `c` (binary), default: C
- `--binary` - Force binary mode (auto-enabled for cmd `c`)
- `--scan-timeout` - BLE scan timeout in seconds (default: 30)
- `--idle-timeout` - Transfer idle timeout (default: 15)
- `--max-seconds` - Maximum transfer time (default: 180)
- `-v`, `-vv`, `-vvv` - Increase verbosity

### atsmini_benchmark.py

Benchmark screenshot capture performance across different transports and modes.

**Usage:**

```bash
# Benchmark all transports and modes
./atsmini_benchmark.py --serial-port /dev/cu.usbmodem1101

# Benchmark serial only
./atsmini_benchmark.py --transport serial --serial-port /dev/cu.usbmodem1101

# Benchmark BLE only
./atsmini_benchmark.py --transport ble

# Benchmark binary mode only
./atsmini_benchmark.py --mode binary --serial-port /dev/cu.usbmodem1101

# Run multiple iterations for averaging
./atsmini_benchmark.py --serial-port /dev/cu.usbmodem1101 --runs 5 --delay 3

# Custom baudrate (if different from default 115200)
./atsmini_benchmark.py --serial-port /dev/cu.usbmodem1101 --baudrate 9600
```

### atsmini_capture_debug.py

Debug tool for diagnosing screenshot capture issues with detailed logging.

**Usage:**

```bash
# Debug serial binary capture with detailed output
./atsmini_capture_debug.py --port /dev/cu.usbmodem1101

# Debug hex mode
./atsmini_capture_debug.py --port /dev/cu.usbmodem1101 --cmd C

# Custom baudrate
./atsmini_capture_debug.py --port /dev/cu.usbmodem1101 --baudrate 9600

# Longer timeout for slow transfers
./atsmini_capture_debug.py --port /dev/cu.usbmodem1101 --timeout 60
```

Shows:
- Chunk-by-chunk data reception with timestamps
- Bytes per chunk and cumulative totals
- Transfer rate in real-time
- Stall detection (warns if no data for 2s)
- Hex preview of first chunks
- Final summary statistics

Use this if transfers are hanging or you suspect data corruption.

**Options:**
- `--transport` - Transport to test: `serial`, `ble`, or `all` (default: all)
- `--mode` - Mode to test: `hex`, `binary`, or `all` (default: all)
- `--serial-port` - Serial port device (required for serial benchmarks)
- `--baudrate` - Serial baudrate (default: 115200)
- `--device-name` - BLE device name (default: ATS-Mini)
- `--scan-timeout` - BLE scan timeout (default: 10s)
- `--max-seconds` - Maximum transfer time per test (default: 60s)
- `--delay` - Delay between tests in seconds (default: 2s)
- `--runs` - Number of runs per configuration (default: 1)
- `--no-progress` - Disable real-time progress display during transfers

**Output:**

The benchmark displays:
- **Real-time progress** during each transfer showing:
  - Progress percentage (once header is received)
  - Bytes received / total bytes
  - Current transfer rate
  - Estimated time remaining (ETA)
- Individual test results with timing and throughput
- Comparison table across all modes
- Speedup analysis (binary vs hex, BLE vs serial)
- Average results when running multiple iterations

**Example output:**

```
============================================================
Benchmark 1/4: SERIAL / HEX
============================================================
  Progress:  78.5% | 86,234/109,866 bytes | 22.14 KiB/s | ETA: 1.07s

[1] SERIAL / HEX
------------------------------------------------------------
✅ SUCCESS
BMP size:        109,866 bytes
Transfer time:   4.23s
Total time:      4.35s
Raw bytes:       221,847 bytes
Overhead:        102.0%
Effective rate:  25.37 KiB/s
Raw rate:        51.36 KiB/s

============================================================
Benchmark 2/4: SERIAL / BINARY
============================================================
  Progress: 100.0% | 109,866/109,866 bytes | 51.64 KiB/s | ETA: 0ms

[2] SERIAL / BINARY
------------------------------------------------------------
✅ SUCCESS
BMP size:        109,866 bytes
Transfer time:   2.08s
Total time:      2.15s
Raw bytes:       109,886 bytes
Overhead:        0.0%
Effective rate:  51.64 KiB/s
Raw rate:        51.67 KiB/s

============================================================
COMPARISON TABLE
============================================================
Transport  Mode     Size         Time       Rate         Overhead  
------------------------------------------------------------
serial     hex      109,866B     4.23s      25.37 KiB/s   102.0%
serial     binary   109,866B     2.08s      51.64 KiB/s     0.0%

============================================================
SPEEDUP ANALYSIS
============================================================

SERIAL: Binary is 2.04x faster than Hex
  Time saved: 2.15s (50.8% faster)
  Overhead reduction: 102.0% → 0.0%
```

## Serial Capture (One-liner)

For quick serial captures without Python:

**Hex mode (legacy):**
```bash
echo -n C | socat stdio /dev/cu.usbmodem1101,echo=0,raw | xxd -r -p > screenshot.bmp
```

**Binary mode (faster):**
```bash
echo -n c | socat stdio /dev/cu.usbmodem1101,echo=0,raw > screenshot.bmp
```

## Notes

- **Binary mode** (`c` command) is ~2x faster than hex mode (`C` command)
- Binary mode has ~0% overhead, hex mode has ~100% overhead (2x the data)
- **BLE optimizations** (firmware v2.x+):
  - Buffered pixel writes (8KB buffer) reduces write calls by ~27,000x
  - Adaptive delays: 5ms for bulk transfers, 15ms for small packets
  - Expected binary BLE throughput: **8-15 KiB/s** (vs 200 B/s previously)
- Serial throughput depends on baudrate (default 115200)
- The ATS-Mini screen is 320x170 pixels @ RGB565 (16-bit color)
- Expected BMP size: ~109KB (including header)

## Troubleshooting

**Transfer stalls or hangs mid-way:**
- **Firmware issue**: Reflash with latest firmware (fixed buffer overflow in v2.x+)
- Use the debug tool to see exactly where it stops: `./atsmini_capture_debug.py --port /dev/cu.usbmodem1101`
- Check for watchdog resets in serial monitor
- Try reducing BLE range (move device closer)
- For serial: try different USB cable/port

**BLE not connecting:**
- Ensure Bluetooth is enabled
- Check device is powered on and in range
- Try specifying `--device` with the MAC address/UUID
- Increase `--scan-timeout`

**Serial not working:**
- Verify correct port name (use `ls -l /dev/cu.*` on macOS)
- Check baudrate matches device setting (default 115200)
- Ensure no other program is using the serial port
- Try different USB cable/port

**Transfer timeout:**
- Increase `--max-seconds` or `--idle-timeout`
- Check receiver is not in sleep mode
- Ensure display is active (not blank)

**Incomplete/corrupted BMP:**
- Check for interference (BLE only)
- Try reducing distance to device (BLE only)
- Verify baudrate is correct (serial only)
- Check if device is responding (send other commands like `t`)
