# ATS-Mini Project Guidelines

Firmware for ESP32-S3 SI4732 radio receiver + Python SDK/CLI communication tools.

## Project Structure

```
firmware/         ESP32-S3 C++ firmware (Arduino framework)
  src/           Main sources (CborRpc, Menu, Draw, Network, etc.)
  include/       Headers (Common.h, Themes.h, tft_setup.h)
sdk/             Python CBOR-RPC client library
  src/ats_sdk/   framing.py, rpc.py
  tests/         Integration tests (require hardware)
client/          Python CLI terminal
```

**Architecture**: Firmware ↔ CBOR-RPC (Serial/BLE/WebSocket) ↔ Python SDK ↔ CLI

## Build and Test

### Python Environment

All Python commands use `.venv`:
```bash
source .venv/bin/activate
pip install -e ".[test]"     # SDK + CLI dependencies
```

### Firmware Build

`pio` (PlatformIO) and `esptool` are available globally:

```bash
# Build firmware (default: esp32s3-ospi)
make build

# Build for QSPI 2MB PSRAM (test device variant)
make build PROFILE=esp32s3-qspi

# Upload to device
make upload PORT=/dev/cu.usbmodem1101

# Full flash (merges bootloader+partitions+firmware, uses --no-stub at 115200 baud)
make fullflash PORT=/dev/cu.usbmodem1101

# Monitor serial output
make monitor PORT=/dev/cu.usbmodem1101

# Check if device connected
lsusb
```

**Note**: Test device has **QSPI 2MB PSRAM** - always use `PROFILE=esp32s3-qspi` for this hardware.

**Upload uses `--no-stub`**: All uploads bypass the esptool stub flasher (`upload_flags = --no-stub` in platformio.ini) because the stub's baud rate change is unreliable over the native USB-JTAG interface. Use `fullflash` after `esptool erase-flash` or on empty flash - it writes a single merged binary at 0x0.

### Testing

```bash
# Run RPC integration tests (requires hardware)
ATSMINI_PORT=/dev/cu.usbmodem1101 pytest sdk/tests/

# Full test cycle with logging (from CONTRIBUTING.md)
PORT=/dev/cu.usbmodem1101 ATSMINI_PORT=/dev/cu.usbmodem1101 LOGFILE=logs/full-test.log make full-test
```

**No unit tests** - all tests are integration-style requiring physical device.

## Code Style

### Memory Management - CRITICAL

ESP32-S3 has **8MB PSRAM** (OPI) or **2MB PSRAM** (QSPI). **Always use PSRAM for large allocations**:

```cpp
// ✅ CORRECT: Use ps_malloc() for buffers >1KB
uint16_t *prevFrame = (uint16_t *)ps_malloc(count * sizeof(uint16_t));
if (!prevFrame) {
  // Handle allocation failure
}

// ❌ WRONG: Large arrays in main RAM
// uint8_t buffer[4096];  // Don't do this!

// Check PSRAM at startup (see firmware/src/ats-mini.cpp:216-223)
if (!ESP.getPsramSize()) {
  tft.println("PSRAM not detected");
}
```

**References**: [firmware/src/Compression.cpp](../firmware/src/Compression.cpp) lines 94, 328 for PSRAM usage patterns.

### Naming Conventions

- **Files**: `PascalCase.cpp` / `.h` (e.g., `CborRpc.cpp`, `Storage.h`)
- **Layout variants**: Prefix `Layout-` (e.g., `Layout-Default.cpp`)
- **Draw functions**: `draw*` prefix (e.g., `drawSaveIndicator()`, `drawMessage()`)

### Display (TFT_eSPI) Patterns

**Hardware**: ST7789 170×320 8-bit parallel display

```cpp
// Global instances (declared in ats-mini.cpp)
extern TFT_eSPI tft;
extern TFT_eSprite spr;

// ✅ ALWAYS use theme colors via TH macro
spr.fillRect(0, 0, 320, 170, TH.bg);
spr.setTextColor(TH.text, TH.bg);
spr.pushSprite(0, 0);  // Render sprite to display

// ❌ NEVER hardcode colors
// spr.fillRect(0, 0, 320, 170, TFT_BLACK);
```

**Theme structure**: See [firmware/include/Themes.h](../firmware/include/Themes.h) - 60+ color properties per theme.

### Radio Control (SI4735)

```cpp
extern SI4735_fixed rx;  // Custom class extending PU2CLR's SI4735

// Common operations
rx.setFrequency(frequency);
rx.setVolume(volume);
rssi = rx.getCurrentRSSI();
snr = rx.getCurrentSNR();
```

**SSB requires patch loading**: See [firmware/src/Utils.cpp](../firmware/src/Utils.cpp) line 76.

### Storage Patterns

**NVS (Non-Volatile Storage)** uses delayed writes to reduce flash wear:

```cpp
// Request save (waits 10s of inactivity before writing)
prefsRequestSave(SAVE_SETTINGS, false);  // Delayed
prefsRequestSave(SAVE_BANDS, true);      // Immediate

// Must call in loop()
void loop() {
  prefsTickTime();  // Processes delayed saves
}
```

**Partitions**: `settings`, `memories`, `bands`, `network` - see [firmware/include/Storage.h](../firmware/include/Storage.h).

### Data Structures

Use `__attribute__((packed))` for stored structures:

```cpp
typedef struct __attribute__((packed)) {
  uint32_t freq;
  uint8_t band;
  uint8_t mode;
  char name[10];
} Memory;
```

**Version tracking** ([firmware/include/Common.h](../firmware/include/Common.h) lines 16-19):
```cpp
#define VER_APP 233      // Firmware version
#define VER_SETTINGS 71  // Settings struct version
```

**Must increment versions** when changing stored data structures.

## Project Conventions

### PSRAM Configuration

Two build profiles in [platformio.ini](../platformio.ini):
- **esp32s3-ospi**: 8MB OPI PSRAM (default)
- **esp32s3-qspi**: 2MB QSPI PSRAM (test device)

**QSPI requires cache fix flag**: `-mfix-esp32-psram-cache-issue`

### USB CDC Always Enabled

```ini
board_build.arduino.usb_mode = 1     # hwcdc
board_build.arduino.usb_on_boot = 1  # CDC on boot
```

Serial is available immediately at startup.

### Build Flags

```bash
make build DEBUG_LEVEL=1        # Enable debug output
make build HALF_STEP=1          # Enable encoder half-steps
```

Flags in [platformio.ini](../platformio.ini): `-DDEBUG=0`, `-DUSER_SETUP_LOADED`, `-include firmware/include/tft_setup.h`

### Interrupt Safety

Rotary encoder ISR must be in IRAM:

```cpp
IRAM_ATTR void rotaryEncoder() {
  // Keep minimal - set flags only
}
```

## Integration Points

### CBOR-RPC Protocol

**Key files**:
- Firmware: [firmware/src/CborRpc.cpp](../firmware/src/CborRpc.cpp), [firmware/include/CborRpc.h](../firmware/include/CborRpc.h)
- SDK: [sdk/src/ats_sdk/](../sdk/src/ats_sdk/__init__.py)
- Tests: [sdk/tests/test_rpc_serial.py](../sdk/tests/test_rpc_serial.py)

**Method naming**: Namespace with dot (e.g., `volume.set`, `tuner.frequency.set`)

### Transports

- **Serial**: Primary interface (115200 baud), `/dev/cu.usbmodem1101` on macOS
- **BLE**: Optional wireless (same CBOR-RPC protocol)
- **WebSocket**: `ws://atsmini.local/rpc` when WiFi enabled

## Hardware

**Test device specifics**:
- **PSRAM**: QSPI 2MB (use `PROFILE=esp32s3-qspi`)
- **USB**: Check with `lsusb` before flashing
- **CPU**: 80MHz (power-optimized)
- **Display**: ST7789 170×320 8-bit parallel
- **Radio**: SI4735 on I2C (GPIO17/18)

**Pin assignments**: [firmware/include/Common.h](../firmware/include/Common.h) lines 41-58.

## Changelog

Use [Keep a Changelog](https://keepachangelog.com/) format with towncrier:

```bash
# Create changelog entry
echo "Fixed menu bounds checking" > changelog/287.fixed.md

# Types: .added .changed .fixed .removed .doc
```

**Filename format**: `+description.type.md` or `123.type.md` (issue number)

## Agent Workflow

**Always verify your changes.** After modifying firmware or SDK code:
- **Firmware**: Run `make build PROFILE=esp32s3-qspi` to confirm it compiles. If the device is connected (`lsusb`), upload and check serial output with `make monitor`.
- **Python/SDK**: Run the relevant tests or at minimum import the changed module to catch syntax errors.
- **Build scripts / platformio.ini**: Run `make build PROFILE=esp32s3-qspi` to confirm the build system still works.

Do not leave the user with untested changes. If a build or test fails, diagnose and fix the issue before reporting back.

## Contributing

- **Issues**: Bugs and planned work only
- **Discussions**: Feature requests and questions
- **PRs**: Not guaranteed unless beneficial to majority - propose in Discussions first

See [CONTRIBUTING.md](../CONTRIBUTING.md) for agent development workflow with logging.
