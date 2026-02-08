#!/usr/bin/env python3
"""Modern TUI for ATS-Mini CBOR-RPC client using Textual."""

import argparse
import asyncio
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, Input, Button, Label, DataTable, Log
from textual.reactive import reactive
from textual import on

from ats_sdk import AsyncSerialRpc, AsyncWebSocketRpc, AsyncBleRpc, Radio, RpcError


class StatusPanel(Static):
    """Live status panel showing radio state."""

    frequency = reactive("---")
    mode = reactive("---")
    band = reactive("---")
    volume = reactive("--")
    rssi = reactive("---")
    snr = reactive("---")
    step = reactive("---")
    bandwidth = reactive("---")

    def render(self) -> str:
        return f"""[bold cyan]Radio Status[/]

[yellow]Frequency:[/] {self.frequency} kHz    [yellow]Mode:[/] {self.mode}    [yellow]Band:[/] {self.band}
[yellow]Volume:[/] {self.volume}    [yellow]Step:[/] {self.step} kHz    [yellow]BW:[/] {self.bandwidth} kHz
[yellow]RSSI:[/] {self.rssi} dBµV    [yellow]SNR:[/] {self.snr} dB
"""


class ConnectionStatus(Static):
    """Connection status indicator."""

    connected = reactive(False)
    transport = reactive("None")

    def render(self) -> str:
        if self.connected:
            icon = "🟢"
            status = f"[green]Connected[/] via {self.transport}"
        else:
            icon = "🔴"
            status = "[red]Disconnected[/]"
        return f"{icon} {status}"


class EventLog(Log):
    """Event log showing real-time messages."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_focus = False

    def log_event(self, event: str, params: dict):
        """Log an event with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if event == "stats":
            freq = params.get("frequency", "?")
            mode = params.get("mode", "?")
            rssi = params.get("rssi", "?")
            snr = params.get("snr", "?")
            self.write_line(f"[dim]{timestamp}[/] [cyan]stats[/] {freq}kHz {mode} RSSI:{rssi} SNR:{snr}")
        else:
            self.write_line(f"[dim]{timestamp}[/] [yellow]{event}[/] {params}")


class ATSMiniTUI(App):
    """Modern TUI for ATS-Mini device control."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-container {
        height: 1fr;
        layout: vertical;
    }

    #status-panel {
        height: 6;
        border: solid green;
        padding: 1;
    }

    #content-area {
        height: 1fr;
        layout: horizontal;
    }

    #event-log-container {
        width: 2fr;
        height: 1fr;
        border: solid cyan;
    }

    #event-log {
        height: 1fr;
    }

    #controls {
        width: 1fr;
        height: 1fr;
        border: solid yellow;
        padding: 1;
    }

    #connection-status {
        padding: 1;
    }

    #command-area {
        height: 3;
        padding: 0 1;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+d", "disconnect", "Disconnect"),
        Binding("ctrl+s", "get_status", "Status"),
        Binding("up", "volume_up", "Vol+"),
        Binding("down", "volume_down", "Vol-"),
    ]

    def __init__(self):
        super().__init__()
        self.client: Optional[AsyncSerialRpc | AsyncWebSocketRpc | AsyncBleRpc] = None
        self.radio: Optional[Radio] = None
        self.event_monitor_task: Optional[asyncio.Task] = None
        self.connection_lost = False
        self.monitor_restart_count = 0
        self.rpc_timeout = 5.0  # Default RPC operation timeout

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header(show_clock=True)

        with Container(id="main-container"):
            yield ConnectionStatus(id="connection-status")
            yield StatusPanel(id="status-panel")

            with Horizontal(id="content-area"):
                with Vertical(id="event-log-container"):
                    yield Label("[bold]Event Log[/]")
                    yield EventLog(id="event-log", auto_scroll=True)

                with Vertical(id="controls"):
                    yield Label("[bold]Quick Controls[/]")
                    yield Button("Volume +", id="vol-up", variant="success")
                    yield Button("Volume -", id="vol-down", variant="primary")
                    yield Button("Band ↑", id="band-up")
                    yield Button("Band ↓", id="band-down")
                    yield Button("Mode ↑", id="mode-up")
                    yield Button("Mode ↓", id="mode-down")
                    yield Button("Refresh Status", id="refresh-status", variant="warning")

            with Container(id="command-area"):
                yield Label("[bold]Command:[/] (e.g., 'connect serial /dev/cu.usbmodem1101', 'connect ble', 'status', 'volume 12')")
                yield Input(placeholder="Enter command...", id="command-input")

        yield Footer()

    async def on_mount(self) -> None:
        """Set up the app when mounted."""
        self.query_one("#command-input", Input).focus()
        self.query_one("#event-log", EventLog).write_line("[dim]Ready. Type 'connect' command to begin.[/]")

    @on(Input.Submitted, "#command-input")
    async def handle_command(self, event: Input.Submitted) -> None:
        """Handle command input."""
        command = event.value.strip()
        if not command:
            return

        event.input.value = ""
        await self.execute_command(command)

    async def execute_command(self, command: str) -> None:
        """Execute a user command."""
        parts = command.split()
        if not parts:
            return

        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "connect":
                await self.cmd_connect(args)
            elif cmd == "disconnect":
                await self.cmd_disconnect()
            elif cmd == "status":
                await self.cmd_status()
            elif cmd == "volume" and args:
                await self.cmd_volume(args[0])
            elif cmd == "band" and args:
                await self.cmd_control("band", args[0])
            elif cmd == "mode" and args:
                await self.cmd_control("mode", args[0])
            elif cmd == "step" and args:
                await self.cmd_control("step", args[0])
            elif cmd == "bandwidth" and args:
                await self.cmd_control("bandwidth", args[0])
            elif cmd == "settings":
                await self.cmd_settings()
            elif cmd == "get" and args:
                await self.cmd_get(args[0])
            elif cmd == "set" and len(args) >= 2:
                await self.cmd_set(args[0], args[1])
            elif cmd == "help":
                self.cmd_help()
            else:
                self.log_message(f"[red]Unknown command: {cmd}[/]")
        except Exception as e:
            self.log_message(f"[red]Error: {e}[/]")

    async def cmd_connect(self, args: list) -> None:
        """Connect to device."""
        if not args:
            self.log_message("[yellow]Usage: connect serial <port> | connect ws <url> | connect ble [name][/]")
            return

        if self.client:
            self.log_message("[yellow]Already connected. Disconnect first.[/]")
            return

        transport = args[0].lower()

        try:
            if transport == "serial":
                if len(args) < 2:
                    self.log_message("[red]Usage: connect serial <port>[/]")
                    return
                port = args[1]
                self.log_message(f"Connecting to {port}...")
                self.client = AsyncSerialRpc(port)
                await asyncio.wait_for(self.client.connect(), timeout=5.0)
                await asyncio.wait_for(self.client.switch_mode(), timeout=2.0)
                transport_name = "Serial"

            elif transport == "ws":
                if len(args) < 2:
                    self.log_message("[red]Usage: connect ws <url>[/]")
                    return
                url = args[1]
                self.log_message(f"Connecting to {url}...")
                self.client = AsyncWebSocketRpc(url)
                await asyncio.wait_for(self.client.connect(), timeout=5.0)
                # WebSocket doesn't need switch_mode - already in CBOR-RPC mode
                transport_name = "WebSocket"

            elif transport == "ble":
                device_name = args[1] if len(args) > 1 else "ATS-Mini"
                self.log_message(f"Scanning for BLE device '{device_name}'...")
                self.client = AsyncBleRpc(device_name, scan_timeout=10.0)
                await asyncio.wait_for(self.client.connect(), timeout=15.0)
                await asyncio.wait_for(self.client.switch_mode(), timeout=2.0)
                transport_name = "BLE"

            else:
                self.log_message(f"[red]Unknown transport: {transport}[/]")
                return

            # Create high-level wrapper
            self.radio = Radio(self.client)

            # Reset connection state
            self.connection_lost = False
            self.monitor_restart_count = 0

            # Update connection status
            conn_status = self.query_one("#connection-status", ConnectionStatus)
            conn_status.connected = True
            conn_status.transport = transport_name

            # Get initial status with timeout
            try:
                await asyncio.wait_for(self.cmd_status(), timeout=self.rpc_timeout)
            except asyncio.TimeoutError:
                self.log_message("[yellow]⚠ Status request timed out (device may be slow)[/]")

            # Start event monitoring
            self.event_monitor_task = asyncio.create_task(self.monitor_events())

            self.log_message(f"[green]✓ Connected via {transport_name}[/]")

        except asyncio.TimeoutError:
            self.log_message(f"[red]✗ Connection timed out[/]")
            await self._cleanup_connection()
        except ConnectionError as e:
            self.log_message(f"[red]✗ Connection failed: {e}[/]")
            await self._cleanup_connection()
        except Exception as e:
            self.log_message(f"[red]✗ Unexpected error: {type(e).__name__}: {e}[/]")
            await self._cleanup_connection()

    async def _cleanup_connection(self) -> None:
        """Internal helper to clean up connection resources."""
        # Stop event monitoring
        if self.event_monitor_task:
            self.event_monitor_task.cancel()
            try:
                await self.event_monitor_task
            except asyncio.CancelledError:
                pass
            self.event_monitor_task = None

        # Close connection
        if self.client:
            try:
                await asyncio.wait_for(self.client.close(), timeout=2.0)
            except Exception as e:
                self.log_message(f"[dim]Cleanup warning: {e}[/]")
            self.client = None
            self.radio = None

        # Update UI
        conn_status = self.query_one("#connection-status", ConnectionStatus)
        conn_status.connected = False
        conn_status.transport = "None"

        self.connection_lost = True

    async def cmd_disconnect(self) -> None:
        """Disconnect from device."""
        if not self.client:
            self.log_message("[yellow]Not connected[/]")
            return

        await self._cleanup_connection()
        self.log_message("[green]✓ Disconnected[/]")

    async def cmd_status(self) -> None:
        """Get and display device status."""
        if not self.client or self.connection_lost:
            self.log_message("[red]Not connected[/]")
            return

        try:
            req_id = await self.client.request("status.get")
            resp = await asyncio.wait_for(
                self.client.read_response(req_id),
                timeout=self.rpc_timeout
            )

            if "result" in resp:
                r = resp["result"]
                status_panel = self.query_one("#status-panel", StatusPanel)
                status_panel.frequency = str(r.get("frequency", "---"))
                status_panel.mode = str(r.get("mode", "---"))
                status_panel.band = str(r.get("band", "---"))
                status_panel.volume = str(r.get("volume", "--"))
                status_panel.rssi = str(r.get("rssi", "---"))
                status_panel.snr = str(r.get("snr", "---"))
                status_panel.step = str(r.get("step", "---"))
                status_panel.bandwidth = str(r.get("bandwidth", "---"))
            elif "error" in resp:
                self.log_message(f"[red]RPC Error: {resp['error']}[/]")
        except asyncio.TimeoutError:
            self.log_message("[red]Status request timed out - device not responding[/]")
            await self._handle_connection_lost()
        except ConnectionError as e:
            self.log_message(f"[red]Connection error: {e}[/]")
            await self._handle_connection_lost()
        except Exception as e:
            self.log_message(f"[red]Unexpected error: {type(e).__name__}: {e}[/]")

    async def cmd_volume(self, value: str) -> None:
        """Set volume level."""
        if not self.client or self.connection_lost:
            self.log_message("[red]Not connected[/]")
            return

        try:
            vol = int(value)
            if not 0 <= vol <= 63:
                self.log_message("[red]Volume must be 0-63[/]")
                return

            req_id = await self.client.request("volume.set", {"value": vol})
            resp = await asyncio.wait_for(
                self.client.read_response(req_id),
                timeout=self.rpc_timeout
            )

            if "result" in resp:
                self.log_message(f"[green]✓ Volume set to {vol}[/]")
                await self.cmd_status()
            elif "error" in resp:
                self.log_message(f"[red]RPC Error: {resp['error']}[/]")
        except ValueError:
            self.log_message("[red]Invalid volume value (use 0-63)[/]")
        except asyncio.TimeoutError:
            self.log_message("[red]Volume command timed out[/]")
            await self._handle_connection_lost()
        except ConnectionError as e:
            self.log_message(f"[red]Connection error: {e}[/]")
            await self._handle_connection_lost()

    async def cmd_control(self, name: str, direction: str) -> None:
        """Execute up/down control commands."""
        if not self.client or self.connection_lost:
            self.log_message("[red]Not connected[/]")
            return

        if direction not in ["up", "down"]:
            self.log_message(f"[red]Invalid direction: {direction}[/]")
            return

        try:
            req_id = await self.client.request(f"{name}.{direction}")
            resp = await asyncio.wait_for(
                self.client.read_response(req_id),
                timeout=self.rpc_timeout
            )

            if "result" in resp:
                self.log_message(f"[green]✓ {name} {direction}[/]")
                await self.cmd_status()
            elif "error" in resp:
                self.log_message(f"[red]RPC Error: {resp['error']}[/]")
        except asyncio.TimeoutError:
            self.log_message(f"[red]Command {name}.{direction} timed out[/]")
            await self._handle_connection_lost()
        except ConnectionError as e:
            self.log_message(f"[red]Connection error: {e}[/]")
            await self._handle_connection_lost()

    # Mapping from CLI setting names to Radio getter/setter method suffixes
    SETTINGS_MAP = {
        "volume": "volume",
        "squelch": "squelch",
        "brightness": "brightness",
        "theme": "theme",
        "band": "band",
        "mode": "mode",
        "step": "step",
        "bandwidth": "bandwidth",
        "agc": "agc",
        "softmute": "softmute",
        "avc": "avc",
        "frequency": "frequency",
        "sleep_timeout": "sleep_timeout",
        "sleep_mode": "sleep_mode",
        "rds_mode": "rds_mode",
        "utc_offset": "utc_offset",
        "fm_region": "fm_region",
        "ui_layout": "ui_layout",
        "zoom_menu": "zoom_menu",
        "scroll_direction": "scroll_direction",
        "usb_mode": "usb_mode",
        "ble_mode": "ble_mode",
        "wifi_mode": "wifi_mode",
        "cal": "cal",
    }

    async def cmd_settings(self) -> None:
        """Get and display all settings."""
        if not self.radio or self.connection_lost:
            self.log_message("[red]Not connected[/]")
            return

        try:
            settings = await asyncio.wait_for(
                self.radio.get_all_settings(),
                timeout=self.rpc_timeout * 2  # Settings can take longer
            )
            lines = ["[bold cyan]Device Settings:[/]"]
            for key, val in settings.items():
                if isinstance(val, dict):
                    parts = ", ".join(f"{k}={v}" for k, v in val.items())
                    lines.append(f"  [yellow]{key}:[/] {parts}")
                else:
                    lines.append(f"  [yellow]{key}:[/] {val}")
            self.log_message("\n".join(lines))
        except RpcError as e:
            self.log_message(f"[red]RPC error: {e.message}[/]")
        except asyncio.TimeoutError:
            self.log_message("[red]Settings request timed out[/]")
            await self._handle_connection_lost()
        except ConnectionError as e:
            self.log_message(f"[red]Connection error: {e}[/]")
            await self._handle_connection_lost()

    async def cmd_get(self, setting: str) -> None:
        """Get a single setting value."""
        if not self.radio or self.connection_lost:
            self.log_message("[red]Not connected[/]")
            return

        name = self.SETTINGS_MAP.get(setting)
        if not name:
            self.log_message(f"[red]Unknown setting: {setting}[/]")
            self.log_message(f"[dim]Available: {', '.join(sorted(self.SETTINGS_MAP.keys()))}[/]")
            return

        getter = getattr(self.radio, f"get_{name}", None)
        if not getter:
            self.log_message(f"[red]No getter for: {setting}[/]")
            return

        try:
            result = await asyncio.wait_for(getter(), timeout=self.rpc_timeout)
            if isinstance(result, dict):
                parts = ", ".join(f"{k}={v}" for k, v in result.items())
                self.log_message(f"[green]{setting}:[/] {parts}")
            else:
                self.log_message(f"[green]{setting}:[/] {result}")
        except RpcError as e:
            self.log_message(f"[red]RPC error: {e.message}[/]")
        except asyncio.TimeoutError:
            self.log_message(f"[red]Get {setting} timed out[/]")
            await self._handle_connection_lost()
        except ConnectionError as e:
            self.log_message(f"[red]Connection error: {e}[/]")
            await self._handle_connection_lost()

    async def cmd_set(self, setting: str, value: str) -> None:
        """Set a single setting value."""
        if not self.radio or self.connection_lost:
            self.log_message("[red]Not connected[/]")
            return

        name = self.SETTINGS_MAP.get(setting)
        if not name:
            self.log_message(f"[red]Unknown setting: {setting}[/]")
            self.log_message(f"[dim]Available: {', '.join(sorted(self.SETTINGS_MAP.keys()))}[/]")
            return

        setter = getattr(self.radio, f"set_{name}", None)
        if not setter:
            self.log_message(f"[red]No setter for: {setting}[/]")
            return

        # Parse value
        if value.lower() in ("true", "on", "yes"):
            parsed = True
        elif value.lower() in ("false", "off", "no"):
            parsed = False
        else:
            try:
                parsed = int(value)
            except ValueError:
                self.log_message(f"[red]Invalid value: {value} (use number or true/false)[/]")
                return

        try:
            result = await asyncio.wait_for(setter(parsed), timeout=self.rpc_timeout)
            if isinstance(result, dict):
                parts = ", ".join(f"{k}={v}" for k, v in result.items())
                self.log_message(f"[green]✓ {setting} set:[/] {parts}")
            else:
                self.log_message(f"[green]✓ {setting} set to {result}[/]")
        except RpcError as e:
            self.log_message(f"[red]RPC error: {e.message}[/]")
        except asyncio.TimeoutError:
            self.log_message(f"[red]Set {setting} timed out[/]")
            await self._handle_connection_lost()
        except ConnectionError as e:
            self.log_message(f"[red]Connection error: {e}[/]")
            await self._handle_connection_lost()

    def cmd_help(self) -> None:
        """Show help message."""
        help_text = """[bold cyan]Available Commands:[/]

[yellow]Connection:[/]
  connect serial <port>  - Connect via serial
  connect ws <url>       - Connect via WebSocket
  connect ble [name]     - Connect via BLE (default: ATS-Mini)
  disconnect             - Disconnect from device

[yellow]Controls:[/]
  status                 - Get device status
  volume <0-63>          - Set volume
  band up|down           - Change band
  mode up|down           - Change mode
  step up|down           - Change step
  bandwidth up|down      - Change bandwidth

[yellow]Settings:[/]
  settings               - Show all device settings
  get <setting>          - Get a setting value
  set <setting> <value>  - Set a setting value

  Settings: volume, squelch, brightness, theme, band, mode, step,
    bandwidth, agc, softmute, avc, frequency, sleep_timeout,
    sleep_mode, rds_mode, utc_offset, fm_region, ui_layout,
    zoom_menu, scroll_direction, usb_mode, ble_mode, wifi_mode, cal

[yellow]Keyboard Shortcuts:[/]
  Ctrl+C  - Quit
  Ctrl+D  - Disconnect
  Ctrl+S  - Status
  ↑/↓     - Volume up/down
"""
        self.log_message(help_text)

    async def _handle_connection_lost(self) -> None:
        """Handle detected connection loss."""
        if self.connection_lost:
            return  # Already handled

        self.connection_lost = True
        self.log_message("[red]⚠ Connection lost - device not responding[/]")

        # Update UI to show disconnected state
        conn_status = self.query_one("#connection-status", ConnectionStatus)
        conn_status.connected = False
        conn_status.transport = "Lost"

    async def monitor_events(self) -> None:
        """Background task to monitor events with auto-restart on errors."""
        restart_delay = 1.0
        max_restarts = 5

        while not self.connection_lost:
            try:
                # Read message with timeout
                msg = await self.client.read_message(timeout=30.0)

                # Reset restart count on successful read
                if self.monitor_restart_count > 0:
                    self.monitor_restart_count = 0

                if msg.get("type") == "event":
                    event = msg.get("event")
                    params = msg.get("params", {})

                    # Log to event log
                    event_log = self.query_one("#event-log", EventLog)
                    event_log.log_event(event, params)

                    # Update status if stats event
                    if event == "stats":
                        status_panel = self.query_one("#status-panel", StatusPanel)
                        if "frequency" in params:
                            status_panel.frequency = str(params["frequency"])
                        if "mode" in params:
                            status_panel.mode = str(params["mode"])
                        if "rssi" in params:
                            status_panel.rssi = str(params["rssi"])
                        if "snr" in params:
                            status_panel.snr = str(params["snr"])

            except asyncio.CancelledError:
                # Normal shutdown
                break

            except asyncio.TimeoutError:
                # Timeout is normal if no events - continue monitoring
                continue

            except ConnectionError as e:
                self.log_message(f"[red]Event monitor: connection error: {e}[/]")
                await self._handle_connection_lost()
                break

            except Exception as e:
                self.monitor_restart_count += 1
                self.log_message(
                    f"[yellow]Event monitor error ({self.monitor_restart_count}/{max_restarts}): {e}[/]"
                )

                if self.monitor_restart_count >= max_restarts:
                    self.log_message("[red]Event monitor failed too many times - stopping[/]")
                    await self._handle_connection_lost()
                    break

                # Wait before restarting
                await asyncio.sleep(restart_delay)
                restart_delay = min(restart_delay * 2, 10.0)  # Exponential backoff

    def log_message(self, message: str) -> None:
        """Log a message to the event log."""
        event_log = self.query_one("#event-log", EventLog)
        event_log.write_line(message)

    # Button handlers
    @on(Button.Pressed, "#vol-up")
    async def volume_up(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_control("volume", "up")

    @on(Button.Pressed, "#vol-down")
    async def volume_down(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_control("volume", "down")

    @on(Button.Pressed, "#band-up")
    async def band_up(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_control("band", "up")

    @on(Button.Pressed, "#band-down")
    async def band_down(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_control("band", "down")

    @on(Button.Pressed, "#mode-up")
    async def mode_up(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_control("mode", "up")

    @on(Button.Pressed, "#mode-down")
    async def mode_down(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_control("mode", "down")

    @on(Button.Pressed, "#refresh-status")
    async def refresh_status(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_status()

    # Action handlers for keybindings
    async def action_disconnect(self) -> None:
        await self.cmd_disconnect()

    async def action_get_status(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_status()

    async def action_volume_up(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_control("volume", "up")

    async def action_volume_down(self) -> None:
        if self.client and not self.connection_lost:
            await self.cmd_control("volume", "down")


def main():
    """Entry point for TUI."""
    parser = argparse.ArgumentParser(description="ATS-Mini Modern TUI")
    parser.add_argument("--serial", help="Auto-connect to serial port")
    parser.add_argument("--ws", help="Auto-connect to WebSocket URL")
    parser.add_argument("--ble", nargs="?", const="ATS-Mini", help="Auto-connect to BLE device")
    args = parser.parse_args()

    app = ATSMiniTUI()

    # Schedule auto-connect if specified
    if args.serial:
        async def auto_connect():
            await asyncio.sleep(0.5)  # Wait for UI to initialize
            await app.execute_command(f"connect serial {args.serial}")
        app.call_later(auto_connect)
    elif args.ws:
        async def auto_connect():
            await asyncio.sleep(0.5)
            await app.execute_command(f"connect ws {args.ws}")
        app.call_later(auto_connect)
    elif args.ble:
        async def auto_connect():
            await asyncio.sleep(0.5)
            await app.execute_command(f"connect ble {args.ble}")
        app.call_later(auto_connect)

    app.run()


if __name__ == "__main__":
    main()
