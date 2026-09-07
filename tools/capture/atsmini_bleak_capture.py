#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import binascii
import re
import sys
import time
from dataclasses import dataclass
from typing import Optional

from bleak import BleakClient, BleakScanner

NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # write to device
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # notify from device

HEX_RE = re.compile(rb"[0-9a-fA-F]+")
SIG = b"424d"  # "BM" in ASCII hex


def fmt_rate(bps: float) -> str:
    if bps >= 1024 * 1024:
        return f"{bps / (1024 * 1024):.2f} MiB/s"
    if bps >= 1024:
        return f"{bps / 1024:.2f} KiB/s"
    return f"{bps:.1f} B/s"


def hexdump_prefix(b: bytes, n: int = 32) -> str:
    b = b[:n]
    return " ".join(f"{x:02x}" for x in b)


@dataclass
class Stats:
    notif_calls: int = 0
    notif_bytes_raw: int = 0           # raw notification bytes received (before filtering)
    hex_digits_accepted: int = 0        # only hex digits appended to hexbuf (after tokenization)
    last_notif_time: float = 0.0
    start_notif_time: Optional[float] = None
    last_report: float = 0.0


class CaptureState:
    def __init__(self, debug: int = 0, binary: bool = False):
        self.debug = debug
        self.binary = binary
        self.hexbuf = bytearray()
        self.binbuf = bytearray()
        self.bmp_size: Optional[int] = None
        self.need_total_hex: Optional[int] = None
        self.need_total_bytes: Optional[int] = None
        self.sync_time: Optional[float] = None
        self.last_data_time: float = time.time()
        self.done_event = asyncio.Event()
        self.stats = Stats()

    def log(self, level: int, msg: str) -> None:
        if self.debug >= level:
            print(msg, file=sys.stderr, flush=True)

    def handle_notify(self, sender: int, data: bytearray) -> None:
        now = time.time()
        self.stats.notif_calls += 1
        self.stats.notif_bytes_raw += len(data)
        self.stats.last_notif_time = now
        if self.stats.start_notif_time is None:
            self.stats.start_notif_time = now

        raw = bytes(data)
        if self.debug >= 3 and self.stats.notif_calls <= 5:
            self.log(3, f"[notify #{self.stats.notif_calls}] len={len(raw)} raw_prefix={hexdump_prefix(raw)}")

        if self.binary:
            self.binbuf.extend(raw)
            self.last_data_time = now

            # Only sync to signature if we haven't found the header yet
            # Once found, don't search again (pixel data can contain "BM" bytes!)
            if self.bmp_size is None:
                pos = self.binbuf.find(b"BM")
                if pos > 0:
                    if self.debug >= 2:
                        self.log(2, f"[sync] discarding {pos} bytes before BMP signature")
                    del self.binbuf[:pos]
                    if self.sync_time is None:
                        self.sync_time = now

                # If we haven't parsed header yet, try when enough data
                if len(self.binbuf) >= 6:
                    if self.binbuf[0:2] == b"BM":
                        self.bmp_size = int.from_bytes(self.binbuf[2:6], "little")
                        self.need_total_bytes = self.bmp_size
                        if self.sync_time is None:
                            self.sync_time = now
                        self.log(1, f"[header] BMP size={self.bmp_size} bytes; need_total_bytes={self.need_total_bytes}")

            # Completion check
            if self.need_total_bytes is not None and len(self.binbuf) >= self.need_total_bytes:
                self.log(1, f"[done] received enough bytes: {len(self.binbuf)}/{self.need_total_bytes}")
                self.done_event.set()
            return

        # Extract hex-only tokens and append
        added_hex_digits = 0
        for m in HEX_RE.finditer(raw):
            tok = m.group(0)
            self.hexbuf.extend(tok)
            added_hex_digits += len(tok)
        self.stats.hex_digits_accepted += added_hex_digits
        self.last_data_time = now

        # Sync to signature
        pos = self.hexbuf.find(SIG)
        if pos > 0:
            if self.debug >= 2:
                self.log(2, f"[sync] discarding {pos} hex chars before BMP signature")
            del self.hexbuf[:pos]
            if self.sync_time is None:
                self.sync_time = now

        # If we haven't parsed header yet, try when enough data
        if self.bmp_size is None and len(self.hexbuf) >= 28:
            try:
                header = binascii.unhexlify(self.hexbuf[:28])
            except binascii.Error:
                # Not enough even-length hex etc; keep accumulating
                return

            if header[0:2] == b"BM":
                self.bmp_size = int.from_bytes(header[2:6], "little")
                self.need_total_hex = self.bmp_size * 2
                if self.sync_time is None:
                    self.sync_time = now
                self.log(1, f"[header] BMP size={self.bmp_size} bytes; need_total_hex={self.need_total_hex}")

        # Completion check
        if self.need_total_hex is not None and len(self.hexbuf) >= self.need_total_hex:
            self.log(1, f"[done] received enough hex: {len(self.hexbuf)}/{self.need_total_hex} hex chars")
            self.done_event.set()

    def progress_report(self) -> None:
        if not self.bmp_size:
            return
        if self.binary:
            if not self.need_total_bytes:
                return
            got_bytes = min(len(self.binbuf), self.bmp_size)
        else:
            if not self.need_total_hex:
                return
            got_bytes = min(len(self.hexbuf) // 2, self.bmp_size)
        pct = 100.0 * got_bytes / self.bmp_size
        self.log(1, f"[progress] {got_bytes}/{self.bmp_size} bytes ({pct:.1f}%)")

    def speed_report(self) -> None:
        if self.stats.start_notif_time is None:
            return
        elapsed = max(time.time() - self.stats.start_notif_time, 1e-6)
        raw_rate = self.stats.notif_bytes_raw / elapsed
        hex_rate = (self.stats.hex_digits_accepted / 2) / elapsed  # decoded bytes/sec equivalent
        self.log(
            1,
            f"[rate] raw_notif={fmt_rate(raw_rate)}; decoded_est={fmt_rate(hex_rate)}; "
            f"notif_calls={self.stats.notif_calls}",
        )


async def find_device_by_name(name: str, timeout: float, debug: int) -> Optional[object]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        found = await BleakScanner.discover(timeout=3.0)
        for d in found:
            if d.name == name:
                if debug:
                    print(f"[scan] found {d.address} name={d.name} rssi={getattr(d, 'rssi', None)}", file=sys.stderr)
                return d
    return None


async def async_main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", help="Device address/UUID (CoreBluetooth UUID on macOS) to connect to")
    ap.add_argument("--name", default="ATS-Mini", help="Device name to scan for (default: ATS-Mini)")
    ap.add_argument("--scan-timeout", type=float, default=30.0, help="Scan timeout seconds (default: 30)")
    ap.add_argument("--idle-timeout", type=float, default=15.0, help="No-data timeout during transfer (default: 15)")
    ap.add_argument("--max-seconds", type=float, default=180.0, help="Hard cap transfer time (default: 180)")
    ap.add_argument("--cmd", default="c", help="Capture command (default: c)")
    ap.add_argument("--binary", action="store_true", help="Treat incoming capture as binary BMP (default for cmd 'c')")
    ap.add_argument("-v", "--verbose", action="count", default=0, help="Increase debug verbosity (-v, -vv, -vvv)")
    ap.add_argument("--no-write", action="store_true", help="Do not send cmd; just listen (debug)")
    args = ap.parse_args()

    if len(args.cmd) != 1:
        die("--cmd must be one byte")

    debug = args.verbose
    binary = args.binary or args.cmd == "c"
    state = CaptureState(debug=debug, binary=binary)

    if debug:
        state.log(1, f"[config] nus_service={NUS_SERVICE}")
        state.log(1, f"[config] rx={NUS_RX} tx={NUS_TX}")
        state.log(1, f"[config] idle_timeout={args.idle_timeout}s max_seconds={args.max_seconds}s")
        state.log(1, f"[config] mode={'binary' if binary else 'hex'}")

    device = None
    if args.device:
        state.log(1, f"[scan] find_device_by_address/uuid: {args.device}")
        device = await BleakScanner.find_device_by_address(args.device, timeout=args.scan_timeout)
        if not device:
            die(f"Could not find device by address/uuid: {args.device}")
    else:
        state.log(1, f"[scan] scanning for name={args.name!r} (timeout={args.scan_timeout}s)")
        device = await find_device_by_name(args.name, args.scan_timeout, debug)
        if not device:
            die(f"Could not find device named {args.name}")

    state.log(1, f"[device] address={device.address} name={device.name!r} rssi={getattr(device, 'rssi', None)}")

    t0 = time.time()
    async with BleakClient(device) as client:
        state.log(1, "[gatt] connecting...")
        # BleakClient context manager connects automatically

        state.log(1, "[gatt] connected")
        if debug >= 2:
            try:
                services = await client.get_services()
                state.log(2, f"[gatt] services discovered: {len(list(services))}")
                # Print NUS service + characteristics if found
                for s in services:
                    if str(s.uuid).lower() == NUS_SERVICE:
                        state.log(2, f"[gatt] found NUS service {s.uuid}")
                        for c in s.characteristics:
                            props = ",".join(c.properties)
                            state.log(2, f"  char {c.uuid} props=[{props}]")
            except Exception as e:
                state.log(2, f"[gatt] get_services failed: {e!r}")

        state.log(1, "[notify] starting notify on TX...")
        await client.start_notify(NUS_TX, state.handle_notify)
        state.log(1, "[notify] notify started")

        if not args.no_write:
            state.log(1, f"[write] sending cmd {args.cmd!r} to RX (response=True)")
            await client.write_gatt_char(NUS_RX, args.cmd.encode("ascii"), response=True)
            state.log(1, "[write] cmd sent")

        # Wait loop
        while True:
            now = time.time()
            if state.done_event.is_set():
                break
            if now - t0 > args.max_seconds:
                state.progress_report()
                state.speed_report()
                die("Hard timeout waiting for full BMP")
            if now - state.last_data_time > args.idle_timeout:
                state.progress_report()
                state.speed_report()
                die("Idle timeout (no notifications arriving)")

            if debug and (now - state.stats.last_report) > 1.0:
                state.stats.last_report = now
                state.progress_report()
                state.speed_report()

            await asyncio.sleep(0.05)

        # Decode and output BMP
        assert state.bmp_size is not None
        if state.binary:
            assert state.need_total_bytes is not None
            bmp = bytes(state.binbuf[: state.need_total_bytes])
        else:
            assert state.need_total_hex is not None
            bmp = binascii.unhexlify(state.hexbuf[: state.need_total_hex])
        sys.stdout.buffer.write(bmp)
        sys.stdout.buffer.flush()

        # Final stats
        if state.sync_time is not None:
            elapsed = max(time.time() - state.sync_time, 1e-6)
            state.log(1, f"[final] decoded {state.bmp_size} bytes in {elapsed:.2f}s => {fmt_rate(state.bmp_size/elapsed)}")

    return 0


def die(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
    raise SystemExit(2)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
