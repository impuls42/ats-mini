# ATS-Mini Project Setup

This guide covers setting up the ATS-Mini project on your machine.

## Prerequisites

- **Python** 3.12+
- **Git**
- **PlatformIO IDE** VS Code extension (or PlatformIO Core CLI)
- **arduino-cli** (if using Make commands directly)

## Initial Setup

### 1. Clone and Enter Project

```bash
git clone https://github.com/esp32-si4732/ats-mini.git
cd ats-mini
```

### 2. Create Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS/Linux
# or
.venv\Scripts\activate          # Windows
```

### 3. Install Dependencies

**For firmware development only:**
```bash
pip install platformio
```

**For full development (firmware + SDK + client):**
```bash
pip install -e ".[dev]"       # Core tools
pip install -e sdk            # CBOR-RPC SDK
pip install -e client         # CLI terminal
```

**For documentation:**
```bash
pip install -e ".[docs]"
```

### 4. Open VS Code

Open the project root in VS Code:
```bash
code .
```

PlatformIO should detect the project and automatically regenerate VS Code configuration files:
- `.vscode/launch.json` (debug config)
- `.vscode/c_cpp_properties.json` (IntelliSense paths)

**Note:** These files contain machine-specific paths and are auto-generated. Do NOT commit them.

## Build Firmware

### Using Makefile (from repo root)

```bash
# Build (default: esp32s3-ospi)
make build

# Build with QSPI variant
make build PROFILE=esp32s3-qspi

# Upload to device
make upload PORT=/dev/cu.usbmodem1101

# Or upload to custom port
make upload PORT=/dev/ttyUSB0

# Monitor serial output
make monitor

# Clean build artifacts
make clean
```

### Using PlatformIO CLI (from firmware/ directory)

```bash
cd firmware

# Build
pio run -e esp32s3-ospi

# Upload
pio run -e esp32s3-ospi -t upload

# Monitor
pio device monitor -p /dev/cu.usbmodem1101

# Clean
pio run -t clean
```

## Develop SDK/Client

### SDK (Communication Library)

```bash
cd sdk
pip install -e ".[test]"
pytest                          # Run tests
```

### Client (CLI Terminal)

```bash
cd client
pip install -e .
atsmini-terminal                # Run CLI
```

## Project Structure

```
ats-mini/
├── firmware/                   # ESP32-S3 PlatformIO project
│   ├── platformio.ini         # Build configuration
│   ├── Makefile               # Build wrapper
│   ├── src/                   # C++ source files (.ino, .cpp)
│   ├── include/               # Header files (.h)
│   └── build/                 # Build artifacts
├── sdk/                        # CBOR-RPC communication library
│   ├── src/ats_sdk/           # SDK implementation
│   ├── tests/                 # SDK tests
│   └── pyproject.toml
├── client/                     # CLI terminal tool
│   ├── src/ats_cli/           # CLI implementation
│   └── pyproject.toml
├── docs/                       # Sphinx documentation
├── Makefile                    # Root build wrapper
└── pyproject.toml             # Root Python config (docs, CI tools)
```

## Troubleshooting

### **"platformio: command not found"**
Make sure `.venv` is activated:
```bash
source .venv/bin/activate
```

### **"No such option: -D" when running make**
This is expected with PlatformIO. To set build flags, edit `firmware/platformio.ini` instead:
```ini
[env:esp32s3-ospi]
board = esp32-s3-devkitc-1
build_flags =
  -DDEBUG=1
```

### **VS Code IntelliSense not working**
PlatformIO auto-generates these files on first open. If missing:
1. Open VS Code project root
2. Wait for PlatformIO to index (watch status bar)
3. Reload window: Cmd+Shift+P → "Developer: Reload Window"

## Development Workflow

1. **Firmware changes:** Edit `firmware/src/` or `firmware/include/`
2. **Test compile:** `make build`
3. **Upload to device:** `make upload`
4. **View output:** `make monitor`

## Further Documentation

- [Hardware Specs](docs/source/hardware.md)
- [Development Guide](docs/source/development.md)
- [Flash Instructions](docs/source/flash.md)
- [Manual](docs/source/manual.md)

---

**Need help?** Open an issue on [GitHub](https://github.com/esp32-si4732/ats-mini/issues)
