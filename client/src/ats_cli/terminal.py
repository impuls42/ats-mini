#!/usr/bin/env python3
"""Interactive terminal for ATS-Mini CBOR-RPC client."""

import argparse
import asyncio
import cmd
import sys
import threading
import time
from typing import Optional

from ats_sdk import AsyncSerialRpc, AsyncWebSocketRpc, AsyncBleRpc


def run_async(coro):
    """Helper to run async coroutine in sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running (rare), create new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class ATSMiniTerminal(cmd.Cmd):
    """Interactive terminal for ATS-Mini device control via CBOR-RPC."""

    intro = "ATS-Mini Interactive Terminal\nType 'help' for commands, 'connect' to start.\n"
    prompt = "(ats-mini) "

    def __init__(self):
        super().__init__()
        self.client: Optional[AsyncSerialRpc | AsyncWebSocketRpc | AsyncBleRpc] = None
        self.event_thread: Optional[threading.Thread] = None
        self.event_running = False

    def do_connect(self, arg):
        """Connect to device: connect serial <port> OR connect ws <url> OR connect ble [device_name]"""
        args = arg.split()
        if len(args) < 1:
            print("Usage: connect serial <port> | connect ws <url> | connect ble [device_name]")
            return

        transport = args[0]

        try:
            if transport == "serial":
                if len(args) < 2:
                    print("Usage: connect serial <port>")
                    return
                port = args[1]
                print(f"Connecting to {port}...")

                self.client = AsyncSerialRpc(port)
                run_async(self.client.connect())
                run_async(self.client.switch_mode())
                print("✓ Connected via Serial")

            elif transport == "ws":
                if len(args) < 2:
                    print("Usage: connect ws <url>")
                    return
                url = args[1]
                print(f"Connecting to {url}...")

                self.client = AsyncWebSocketRpc(url)
                run_async(self.client.connect())
                print("✓ Connected via WebSocket")

            elif transport == "ble":
                device_name = args[1] if len(args) > 1 else "ATS-Mini"
                print(f"Scanning for BLE device '{device_name}'...")

                self.client = AsyncBleRpc(device_name, scan_timeout=10.0)
                run_async(self.client.connect())
                run_async(self.client.switch_mode())
                print("✓ Connected via BLE")

            else:
                print(f"Unknown transport: {transport}")
                print("Available: serial, ws, ble")
                return

            # Test connection with capabilities
            req_id = run_async(self.client.request("capabilities.get"))
            caps = run_async(self.client.read_response(req_id))
            if caps and isinstance(caps, dict) and "result" in caps:
                print(f"Device: {caps['result'].get('device', 'Unknown')}")
                print(f"Version: {caps['result'].get('version', 'Unknown')}")
                transports = caps['result'].get('transports', [])
                print(f"Transports: {', '.join(transports)}")
            elif caps and isinstance(caps, dict) and "error" in caps:
                print(f"Warning: {caps['error']}")
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            if self.client:
                try:
                    run_async(self.client.close())
                except:
                    pass
            self.client = None

    def do_disconnect(self, arg):
        """Disconnect from device"""
        self._stop_events()
        if self.client:
            try:
                run_async(self.client.close())
            except:
                pass
            self.client = None
            print("✓ Disconnected")

    def do_status(self, arg):
        """Get device status"""
        if not self._check_connected():
            return
        try:
            req_id = run_async(self.client.request("status.get"))
            resp = run_async(self.client.read_response(req_id))
            if "result" in resp:
                r = resp["result"]
                print(f"Frequency: {r.get('freq', 'N/A')} kHz")
                print(f"BFO: {r.get('bfo', 'N/A')} Hz")
                print(f"Band: {r.get('band', 'N/A')}")
                print(f"Mode: {r.get('mode', 'N/A')}")
                print(f"Step: {r.get('step', 'N/A')} kHz")
                print(f"Bandwidth: {r.get('bandwidth', 'N/A')} kHz")
                print(f"Volume: {r.get('volume', 'N/A')}")
                print(f"RSSI: {r.get('rssi', 'N/A')} dBµV")
                print(f"SNR: {r.get('snr', 'N/A')} dB")
            elif "error" in resp:
                print(f"✗ Error: {resp['error']}")
        except Exception as e:
            print(f"✗ Request failed: {e}")

    def do_capabilities(self, arg):
        """Get device capabilities"""
        if not self._check_connected():
            return
        try:
            req_id = run_async(self.client.request("capabilities.get"))
            resp = run_async(self.client.read_response(req_id))
            if "result" in resp:
                r = resp["result"]
                print(f"Device: {r.get('device', 'Unknown')}")
                print(f"Version: {r.get('version', 'Unknown')}")
                print(f"Features: {', '.join(r.get('features', []))}")
            elif "error" in resp:
                print(f"✗ Error: {resp['error']}")
        except Exception as e:
            print(f"✗ Request failed: {e}")

    def do_volume(self, arg):
        """Volume control: volume get|set <0-63>|up|down"""
        if not self._check_connected():
            return
        args = arg.split()
        if not args:
            print("Usage: volume get|set <0-63>|up|down")
            return

        try:
            cmd = args[0]
            if cmd == "get":
                req_id = self.client.request("volume.get")
            elif cmd == "set" and len(args) > 1:
                req_id = self.client.request("volume.set", {"level": int(args[1])})
            elif cmd == "up":
                req_id = self.client.request("volume.up")
            elif cmd == "down":
                req_id = self.client.request("volume.down")
            else:
                print("Usage: volume get|set <0-63>|up|down")
                return

            resp = self.client.read_response(req_id)

            if "result" in resp:
                if "level" in resp["result"]:
                    print(f"Volume: {resp['result']['level']}")
                else:
                    print("✓ OK")
            elif "error" in resp:
                print(f"✗ Error: {resp['error']}")
        except Exception as e:
            print(f"✗ Request failed: {e}")

    def do_band(self, arg):
        """Band control: band up|down"""
        self._simple_control("band", arg)

    def do_mode(self, arg):
        """Mode control: mode up|down"""
        self._simple_control("mode", arg)

    def do_step(self, arg):
        """Step control: step up|down"""
        self._simple_control("step", arg)

    def do_bandwidth(self, arg):
        """Bandwidth control: bandwidth up|down"""
        self._simple_control("bandwidth", arg)

    def do_agc(self, arg):
        """AGC control: agc up|down"""
        self._simple_control("agc", arg)

    def do_backlight(self, arg):
        """Backlight control: backlight up|down"""
        self._simple_control("backlight", arg)

    def do_cal(self, arg):
        """Calibration control: cal up|down"""
        self._simple_control("cal", arg)

    def do_sleep(self, arg):
        """Sleep control: sleep on|off"""
        if not self._check_connected():
            return
        if arg not in ["on", "off"]:
            print("Usage: sleep on|off")
            return
        try:
            req_id = self.client.request(f"sleep.{arg}")
            resp = self.client.read_response(req_id)
            if "result" in resp:
                print("✓ OK")
            elif "error" in resp:
                print(f"✗ Error: {resp['error']}")
        except Exception as e:
            print(f"✗ Request failed: {e}")

    def do_log(self, arg):
        """Log control: log get|toggle"""
        if not self._check_connected():
            return
        if arg not in ["get", "toggle"]:
            print("Usage: log get|toggle")
            return
        try:
            req_id = self.client.request(f"log.{arg}")
            resp = self.client.read_response(req_id)
            if "result" in resp:
                if "enabled" in resp["result"]:
                    print(f"Logging: {'enabled' if resp['result']['enabled'] else 'disabled'}")
                else:
                    print("✓ OK")
            elif "error" in resp:
                print(f"✗ Error: {resp['error']}")
        except Exception as e:
            print(f"✗ Request failed: {e}")

    def do_memory(self, arg):
        """Memory operations: memory list|set <slot> <freq> <mode> <band>"""
        if not self._check_connected():
            return
        args = arg.split()
        if not args:
            print("Usage: memory list|set <slot> <freq> <mode> <band>")
            return

        try:
            cmd = args[0]
            if cmd == "list":
                req_id = self.client.request("memory.list")
                resp = self.client.read_response(req_id)
                if "result" in resp and "stations" in resp["result"]:
                    stations = resp["result"]["stations"]
                    print(f"Memory stations ({len(stations)}):")
                    for s in stations:
                        print(f"  [{s['slot']}] {s['freq']} kHz - {s['mode']} ({s['band']})")
                elif "error" in resp:
                    print(f"✗ Error: {resp['error']}")
            elif cmd == "set" and len(args) >= 5:
                params = {
                    "slot": int(args[1]),
                    "freq": int(args[2]),
                    "mode": int(args[3]),
                    "band": int(args[4])
                }
                req_id = self.client.request("memory.set", params)
                resp = self.client.read_response(req_id)
                if "result" in resp:
                    print("✓ Memory updated")
                elif "error" in resp:
                    print(f"✗ Error: {resp['error']}")
            else:
                print("Usage: memory list|set <slot> <freq> <mode> <band>")
        except Exception as e:
            print(f"✗ Request failed: {e}")

    def do_screen(self, arg):
        """Screen capture: screen <bmp|rle> <filename>"""
        if not self._check_connected():
            return
        args = arg.split()
        if len(args) < 2:
            print("Usage: screen <bmp|rle> <filename>")
            return

        fmt = args[0]
        filename = args[1]

        if fmt not in ["bmp", "rle"]:
            print("Format must be 'bmp' or 'rle'")
            return

        try:
            print(f"Capturing screen as {fmt}...")
            req_id = self.client.request("screen.capture", {"format": fmt})
            resp = self.client.read_response(req_id)
            
            if "error" in resp:
                print(f"✗ Error: {resp['error']}")
                return

            # Collect chunks
            chunks = []
            while True:
                msg = self.client.read_message(timeout=5.0)
                if not msg:
                    print("✗ Timeout waiting for screen data")
                    return
                
                if msg.get("type") == "event":
                    if msg.get("event") == "screen.chunk":
                        chunk = msg.get("params", {}).get("data", b"")
                        chunks.append(chunk)
                        print(".", end="", flush=True)
                    elif msg.get("event") == "screen.done":
                        print()
                        break

            # Write to file
            data = b"".join(chunks)
            with open(filename, "wb") as f:
                f.write(data)
            print(f"✓ Saved {len(data)} bytes to {filename}")

        except Exception as e:
            print(f"✗ Capture failed: {e}")

    def do_events(self, arg):
        """Start/stop event monitoring: events start|stop"""
        if not self._check_connected():
            return

        if arg == "start":
            if self.event_running:
                print("Events already running")
                return
            try:
                # Subscribe to stats events
                req_id = self.client.request("stats.subscribe")
                resp = self.client.read_response(req_id)
                if "error" in resp:
                    print(f"✗ Error: {resp['error']}")
                    return
                
                self.event_running = True
                self.event_thread = threading.Thread(target=self._event_loop, daemon=True)
                self.event_thread.start()
                print("✓ Event monitoring started")
            except Exception as e:
                print(f"✗ Failed to start events: {e}")
        elif arg == "stop":
            self._stop_events()
        else:
            print("Usage: events start|stop")

    def do_quit(self, arg):
        """Exit the terminal"""
        self.do_disconnect(arg)
        print("Goodbye!")
        return True

    def do_exit(self, arg):
        """Exit the terminal"""
        return self.do_quit(arg)

    def do_EOF(self, arg):
        """Exit on Ctrl-D"""
        print()
        return self.do_quit(arg)

    def _check_connected(self):
        """Check if client is connected."""
        if not self.client:
            print("✗ Not connected. Use 'connect' first.")
            return False
        return True

    def _simple_control(self, name, arg):
        """Handle simple up/down controls."""
        if not self._check_connected():
            return
        if arg not in ["up", "down"]:
            print(f"Usage: {name} up|down")
            return
        try:
            req_id = self.client.request(f"{name}.{arg}")
            resp = self.client.read_response(req_id)
            if "result" in resp:
                print("✓ OK")
            elif "error" in resp:
                print(f"✗ Error: {resp['error']}")
        except Exception as e:
            print(f"✗ Request failed: {e}")

    def _event_loop(self):
        """Background thread to display events."""
        while self.event_running:
            try:
                msg = self.client.read_message(timeout=0.5)
                if msg and msg.get("type") == "event":
                    event = msg.get("event")
                    params = msg.get("params", {})
                    
                    if event == "stats":
                        # Compact stats display
                        freq = params.get("freq", "?")
                        mode = params.get("mode", "?")
                        rssi = params.get("rssi", "?")
                        snr = params.get("snr", "?")
                        print(f"\n[stats] {freq} kHz | {mode} | RSSI:{rssi} SNR:{snr}")
                        print(self.prompt, end="", flush=True)
                    else:
                        print(f"\n[{event}] {params}")
                        print(self.prompt, end="", flush=True)
            except Exception:
                pass
            time.sleep(0.1)

    def _stop_events(self):
        """Stop event monitoring."""
        if self.event_running:
            self.event_running = False
            if self.event_thread:
                self.event_thread.join(timeout=2.0)
            if self.client:
                try:
                    req_id = self.client.request("stats.unsubscribe")
                    self.client.read_response(req_id)
                except Exception:
                    pass
            print("✓ Event monitoring stopped")


def main():
    """Entry point for interactive terminal."""
    parser = argparse.ArgumentParser(description="ATS-Mini Interactive Terminal")
    parser.add_argument("--serial", help="Auto-connect to serial port")
    parser.add_argument("--ws", help="Auto-connect to WebSocket URL")
    args = parser.parse_args()

    terminal = ATSMiniTerminal()
    
    # Auto-connect if specified
    if args.serial:
        terminal.do_connect(f"serial {args.serial}")
    elif args.ws:
        terminal.do_connect(f"ws {args.ws}")

    try:
        terminal.cmdloop()
    except KeyboardInterrupt:
        print("\nInterrupted")
        terminal.do_disconnect("")


if __name__ == "__main__":
    main()
