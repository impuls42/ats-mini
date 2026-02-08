# Development

```{include} ../../CONTRIBUTING.md
```

## Video tutorial

A short video tutorial on how to build a custom firmware version ([YouTube mirror](https://youtu.be/WrPj2_DdfjI)):

<iframe width="720" height="405" src="https://rutube.ru/play/embed/1ff6fc7246260b3d404acebd0435d785?p=faQjyf7QWhT3bff2GDrReQ" frameBorder="0" allow="clipboard-write; autoplay" webkitAllowFullScreen mozallowfullscreen allowFullScreen></iframe>

## Compiling the source code

This project uses [PlatformIO](https://platformio.org/) for building firmware. PlatformIO is available globally in the development environment.

### Quick build commands

```shell
# Build firmware (default profile: esp32s3-qspi from platformio.ini)
make build

# Build for OSPI variant (8MB PSRAM)
make build PROFILE=esp32s3-ospi

# Upload firmware to device
make upload PORT=/dev/cu.usbmodem1101

# Full flash (merged binary at 0x0, erases all settings)
make fullflash PORT=/dev/cu.usbmodem1101

# Monitor serial output
make monitor PORT=/dev/cu.usbmodem1101
```

### Using PlatformIO directly

`platformio.ini` lives at the repo root. No need to `cd firmware/`.

```shell
# Build for specific environment
pio run -e esp32s3-qspi

# Upload firmware
pio run -e esp32s3-qspi -t upload --upload-port /dev/cu.usbmodem1101

# Monitor serial output
pio device monitor --port /dev/cu.usbmodem1101
```

### Available build environments

Build profiles are defined in `platformio.ini`:

- `esp32s3-ospi` - Release build for 8MB OPI PSRAM (default variant)
- `esp32s3-qspi` - Release build for 2MB QSPI PSRAM (test device)
- `esp32s3-ospi-debug` - Debug build for OPI PSRAM
- `esp32s3-qspi-debug` - Debug build for QSPI PSRAM

The default environment is set in `platformio.ini` with `default_envs = esp32s3-qspi`.

## Compile-time options

The available options are:

* `HALF_STEP` - enable encoder half-steps (useful for EC11E encoder)
* `DEBUG` - enable debug logging (0=none, 1=verbose)

To set an option, use the Makefile variables or PlatformIO build flags:

```shell
# Using Makefile
make build PROFILE=esp32s3-qspi HALF_STEP=1
make build PROFILE=esp32s3-qspi DEBUG_LEVEL=1

# Using environment variable
PLATFORMIO_BUILD_FLAGS="-DHALF_STEP -DDEBUG=1" pio run -e esp32s3-qspi
```

Build flags can also be permanently set in `platformio.ini` in the `build_flags` section.

## Debugging with OpenOCD

The ESP32-S3 has built-in USB-JTAG support, allowing you to debug the firmware without an external debug probe.

### Prerequisites

- OpenOCD 0.12.0 or later (usually installed with PlatformIO)
- USB connection to the ESP32-S3 device

### Hardware Setup

The ESP32-S3 built-in USB-JTAG adapter uses the same USB port as the serial console. No additional wiring is required.

**IMPORTANT**: The ESP32-S3 has two USB ports:
- USB Native (built-in JTAG) - used for debugging
- USB Serial/JTAG Console - used for normal serial communication

For debugging, ensure you're connected to the correct USB port.

### Building Debug Firmware

Two debug profiles are available with debug symbols enabled:

```shell
# Build debug firmware for QSPI PSRAM device (test device)
make debug-build PROFILE=esp32s3-qspi

# Build debug firmware for OPI PSRAM device
make debug-build PROFILE=esp32s3-ospi

# Build and upload debug firmware
make debug-upload PROFILE=esp32s3-qspi PORT=/dev/cu.usbmodem1101
```

Debug builds include:
- Full debug symbols (`-g3 -ggdb`)
- No optimization (`-O0`)
- Debug-level logging enabled (`-DDEBUG=1`)

### Debugging in VSCode

**Important**: Due to USB communication limitations with ESP32-S3 built-in JTAG on macOS, use the "attach" workflow instead of full reset debugging.

#### Recommended Workflow

1. Install the PlatformIO extension for VSCode
2. Build and upload the debug firmware:
   ```shell
   make debug-upload PROFILE=esp32s3-qspi PORT=/dev/cu.usbmodem1101
   ```
3. Open the "Run and Debug" panel (Cmd+Shift+D)
4. Select **"PIO Debug (skip Pre-Debug)"** from the dropdown
5. Click "Start Debugging" (F5)

The debugger will attach to the running firmware. You can then:
- Press Ctrl+C (or click the pause button) to halt execution
- Set breakpoints in your code
- Use "Continue" (F5) to run until a breakpoint is hit
- Step through code with F10 (step over) and F11 (step into)
- Inspect variables in the Variables panel

#### Setting Breakpoints

Since the debugger attaches to running code rather than breaking at `setup()`:

1. Start the debugger
2. Pause execution (Ctrl+C or pause button)
3. Set breakpoints where you need them (click in the gutter next to line numbers)
4. Continue execution (F5) - it will break at your breakpoints

Example: To debug the main loop:
```cpp
void loop() {
  // Set breakpoint on next line
  int value = someFunction();  // <- Click here to set breakpoint
  ...
}
```

### Debugging from Command Line

For CLI-based debugging with GDB:

```shell
# Start debugging session
make debug PROFILE=esp32s3-qspi PORT=/dev/cu.usbmodem1101

# Or use PlatformIO directly
pio debug -e esp32s3-qspi-debug --interface=gdb
```

Common GDB commands:
- `break firmware/src/ats-mini.cpp:123` - Set breakpoint
- `continue` (or `c`) - Continue execution
- `next` (or `n`) - Step over
- `step` (or `s`) - Step into
- `print variable` (or `p variable`) - Print variable value
- `backtrace` (or `bt`) - Show call stack
- `info locals` - Show local variables
- `quit` - Exit debugger

### Debug Configuration

The debug configuration is defined in `platformio.ini`:

```ini
debug_tool = esp-builtin      # Use ESP32-S3 built-in USB-JTAG
debug_init_break =            # No initial break (attach to running code)
debug_speed = 5000            # JTAG speed in kHz
```

### Troubleshooting

**USB Communication Errors (`libusb_bulk_write error: LIBUSB_ERROR_OTHER`)**:
- This is a known issue with ESP32-S3 USB-JTAG on macOS
- **Solution**: Use "PIO Debug (skip Pre-Debug)" instead of "PIO Debug"
- This attaches to running firmware instead of performing a full reset
- Upload firmware separately with `make debug-upload` before debugging

**"Could not connect to target"**:
- Ensure the device is properly connected via USB
- Check that no other program is using the serial port: `lsof | grep usbmodem`
- Try resetting the device (press reset button)
- Verify OpenOCD is installed: `openocd --version`

**"target not halted" warnings**:
- Normal when attaching to running code
- Click the pause button or press Ctrl+C to halt execution
- Then set your breakpoints and continue

**"Symbol not found"**:
- Ensure you built with the debug profile (`-debug` suffix)
- Verify the correct `.elf` file is being loaded
- Rebuild with `make clean && make debug-build PROFILE=esp32s3-qspi`

**Serial communication during debugging**:
- The USB-JTAG interface may interfere with serial communication
- Consider using a separate USB-to-serial adapter for logging during debugging
- Or use network-based logging if WiFi is enabled

### Performance Notes

Debug builds have performance characteristics different from release builds:
- Much slower execution due to `-O0` (no optimization)
- Larger firmware size due to debug symbols
- More accurate variable inspection and stepping
- Better error messages and stack traces

For production/testing, always use release builds (`make build`).

## CBOR-RPC transport (optional)

CBOR-RPC is an opt-in, framed binary protocol. Legacy terminal commands stay the default.

### Serial/BLE activation

Send the switch byte `0x1E` to activate CBOR-RPC mode for the connection. After switching, send length-prefixed CBOR frames:

```text
[4-byte big-endian length][CBOR payload]
```

### WebSocket

When Wi-Fi is enabled, connect to `ws://atsmini.local/rpc` and send binary messages in the same length-prefixed format.

### SDK usage

The Python SDK is fully async. All transports extend `AsyncRpcTransport`. A high-level `Radio` class provides typed convenience methods.

```python
from ats_sdk import AsyncSerialRpc, Radio

async with AsyncSerialRpc("/dev/cu.usbmodem1101") as transport:
    await transport.switch_mode()
    radio = Radio(transport)
    vol = await radio.get_volume()
    await radio.set_volume(10)
```

### Available RPC methods

- `capabilities.get` / `status.get` / `settings.get`
- `volume.set` / `volume.get`
- `frequency.set` / `frequency.get`
- `band.set` / `band.get`
- `mode.set` / `mode.get`
- `step.set` / `step.get`
- `bandwidth.set` / `bandwidth.get`
- `agc.set` / `agc.get`
- `squelch.set` / `squelch.get`
- `softmute.set` / `softmute.get`
- `avc.set` / `avc.get`
- `theme.set` / `theme.get`
- `brightness.set` / `brightness.get`
- `sleep.timeout.set` / `sleep.timeout.get`
- `sleep.mode.set` / `sleep.mode.get`
- `sleep.on` / `sleep.off`
- `ble.mode.set` / `ble.mode.get`
- `wifi.mode.set` / `wifi.mode.get`
- `usb.mode.set` / `usb.mode.get`
- `memory.list`
- `events.subscribe` / `events.unsubscribe`
- `screen.capture` (`binary` or `rle`)

## Decoding stack traces

To decode a stack trace (printed via serial port) use the following tool: <https://esphome.github.io/esp-stacktrace-decoder/>

## Enabling the pre-commit hooks

1. Install `uv` <https://docs.astral.sh/uv/getting-started/installation/>
2. Run `uv sync`
3. run `uv run pre-commit install --install-hooks`

## Adding a changelog entry

1. Install `uv` <https://docs.astral.sh/uv/getting-started/installation/>
2. Run `uv sync`
3. Create an entry:
   ```
   uv run towncrier create --edit ID.CATEGORY.md
   ```
   `ID` is an issue or a PR number, or `+STRING` if there is no issue/PR. `CATEGORY` is one of `added`, `changed`, `fixed`, etc. see the `tool.towncrier.type` sections in the `pyproject.toml` for the full list.

## Improving the documentation

1. Install `uv` <https://docs.astral.sh/uv/getting-started/installation/>
2. Run `uv sync`
3. Run a local webserver `uv run sphinx-autobuild docs/source docs/build` and open the http://127.0.0.1:8000 in a browser
4. Edit the Markdown files in `docs/source` folder and immediately see your changes reflected in the browser

## Theme editor

A terminal command <kbd>T</kbd> toggles a special mode that helps you pick the right colors faster without recompiling and flashing the firmware each time. When the theme editor is enabled, some screen elements are always visible (and various status icons change their state every couple of seconds):

![](_static/theme-editor.png)

Press <kbd>@</kbd> to print the current color theme to the serial console:

```shell
Color theme Default: x0000xFFFFxD69AxF800xD69Ax07E0xF800xF800xFFFFxFFFFx07E0xF800x001FxFFE0xD69AxD69AxD69Ax0000xD69AxD69AxF800xBEDFx0000xF800xFFFFxBEDFx105BxBEDFxBEDFxFFFFxD69AxF800xFFE0xD69AxFFFFxF800xC638
```

Then copy the theme to your favorite text editor, change the colors as you see (here is a handy [565 color picker](https://chrishewett.com/blog/true-rgb565-colour-picker/)).

To preview the theme, paste it to the serial console with the <kbd>^</kbd> character appended:

```shell
^x0000xFFFFxD69AxF800xD69Ax07E0xF800xF800xFFFFxFFFFx07E0xF800x001FxFFE0xD69AxD69AxD69Ax0000xD69AxD69AxF800xBEDFx0000xF800xFFFFxBEDFx105BxBEDFxBEDFxFFFFxD69AxF800xFFE0xD69AxFFFFxF800xC638
```

Once you are happy, add the resulting colors to `Theme.cpp`.

## Release process

1. Bump the `VER_APP` constant in the `Common.h` file
2. If the new version has a different preferences layout, bump `VER_SETTINGS`, `VER_BANDS`, or `VER_MEMORIES` as well (it will force the corresponding preferences section reset)
3. Generate the CHANGELOG.md by running `uv run towncrier build --version X.XX`
4. Add and commit the changes with a message like "Release X.XX", then push them to the repository
5. Once the build is complete, download, flash and test it!
6. Tag the release and push the tag `git tag -a vX.XX -m 'Version X.XX' && git push --follow-tags` (the tag should start with `v`!)
