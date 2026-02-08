# ats-cli

Command-line interface for the ATS-Mini radio receiver, built on [Click](https://click.palletsprojects.com/) with an interactive REPL.

## Install

```bash
pip install -e client/
```

## Usage

```bash
# One-shot commands
atsmini -p /dev/ttyUSB0 status
atsmini -p /dev/ttyUSB0 volume 20
atsmini -p /dev/ttyUSB0 band FM

# Interactive REPL (no command = enter REPL)
atsmini -p /dev/ttyUSB0

# Use environment variables instead of flags
export ATSMINI_PORT=/dev/ttyUSB0
atsmini status

# JSON output for scripting
atsmini --json -p /dev/ttyUSB0 settings

# WebSocket or BLE transport
atsmini --ws ws://atsmini.local/rpc status
atsmini --ble status
```

Run `atsmini --help` for the full command list.
