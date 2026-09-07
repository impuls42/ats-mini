#!/usr/bin/env python3
"""
Universal ATS-Mini Screenshot Capture Script

Captures screenshots from ATS-Mini device via serial or BLE with hex or binary modes.
Supports multiple transports and modes with extensible architecture.
Supports streaming to external viewers (e.g., catimg, fbi, etc).
"""

from __future__ import annotations

import argparse
import asyncio
import binascii
import re
import subprocess
import sys
import tempfile
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

try:
    from bleak import BleakClient, BleakScanner
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False

try:
    import serial
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False


# BLE Nordic UART Service UUIDs
NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Pattern matching for hex data
HEX_RE = re.compile(rb"[0-9a-fA-F]+")
SIG_HEX = b"424d"  # "BM" in ASCII hex
SIG_BIN = b"BM"
MAGIC_ZR = b"ZR"
MAGIC_DR = b"DR"
COMP_HEADER_LEN = 16


def fmt_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} MiB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.2f} KiB"
    return f"{num_bytes} B"


def parse_bmp_header(bmp_data: bytes) -> Optional[dict]:
    if len(bmp_data) < 54 or bmp_data[0:2] != b"BM":
        return None

    file_size = int.from_bytes(bmp_data[2:6], "little", signed=False)
    data_offset = int.from_bytes(bmp_data[10:14], "little", signed=False)
    dib_header_size = int.from_bytes(bmp_data[14:18], "little", signed=False)
    width = int.from_bytes(bmp_data[18:22], "little", signed=True)
    height = int.from_bytes(bmp_data[22:26], "little", signed=True)
    planes = int.from_bytes(bmp_data[26:28], "little", signed=False)
    bpp = int.from_bytes(bmp_data[28:30], "little", signed=False)

    return {
        "file_size": file_size,
        "data_offset": data_offset,
        "dib_header_size": dib_header_size,
        "width": width,
        "height": height,
        "planes": planes,
        "bpp": bpp,
    }


def extract_rgb565_pixels(bmp_data: bytes) -> Optional[bytes]:
    header = parse_bmp_header(bmp_data)
    if not header:
        return None

    width = header["width"]
    height = header["height"]
    bpp = header["bpp"]
    data_offset = header["data_offset"]

    if bpp != 16 or width <= 0 or height == 0:
        return None

    abs_height = abs(height)
    bytes_per_pixel = 2
    row_bytes_unpadded = width * bytes_per_pixel
    row_bytes = (row_bytes_unpadded + 3) & ~3
    needed = data_offset + row_bytes * abs_height
    if len(bmp_data) < needed:
        return None

    pixels = bytearray()
    for row in range(abs_height):
        row_start = data_offset + row * row_bytes
        pixels.extend(bmp_data[row_start:row_start + row_bytes_unpadded])

    return bytes(pixels)


def estimate_rle_rgb565_size(pixel_bytes: bytes) -> int:
    if not pixel_bytes or len(pixel_bytes) % 2 != 0:
        return 0

    total = 0
    count = len(pixel_bytes) // 2
    i = 0
    while i < count:
        val = pixel_bytes[2 * i:2 * i + 2]
        run = 1
        while i + run < count and run < 255:
            if pixel_bytes[2 * (i + run):2 * (i + run) + 2] != val:
                break
            run += 1
        total += 1 + 2
        i += run
    return total


def estimate_delta_rle_size(prev_bytes: bytes, curr_bytes: bytes) -> Optional[int]:
    if not prev_bytes or not curr_bytes:
        return None
    if len(prev_bytes) != len(curr_bytes) or len(curr_bytes) % 2 != 0:
        return None

    total = 0
    count = len(curr_bytes) // 2
    i = 0
    while i < count:
        same = curr_bytes[2 * i:2 * i + 2] == prev_bytes[2 * i:2 * i + 2]
        run = 1
        while i + run < count and run < 127:
            cur_same = curr_bytes[2 * (i + run):2 * (i + run) + 2] == prev_bytes[2 * (i + run):2 * (i + run) + 2]
            if cur_same != same:
                break
            run += 1

        if same:
            total += 1
        else:
            total += 1 + run * 2
        i += run

    return total


def analyze_bmp_compression(bmp_data: bytes, prev_bmp: Optional[bytes] = None) -> None:
    header = parse_bmp_header(bmp_data)
    if not header:
        print("Analyze: invalid or unsupported BMP", file=sys.stderr)
        return

    pixel_bytes = extract_rgb565_pixels(bmp_data)
    if not pixel_bytes:
        print("Analyze: unsupported BMP format (expected 16bpp RGB565)", file=sys.stderr)
        return

    width = header["width"]
    height = header["height"]
    bpp = header["bpp"]
    raw_size = len(pixel_bytes)
    bmp_size = len(bmp_data)
    zlib_pixels = len(zlib.compress(pixel_bytes))
    zlib_bmp = len(zlib.compress(bmp_data))
    rle_size = estimate_rle_rgb565_size(pixel_bytes)

    print("\nCompression analysis:")
    print(f"  Resolution: {width}x{abs(height)} @ {bpp}bpp")
    print(f"  Raw RGB565: {fmt_size(raw_size)}")
    print(f"  BMP size:   {fmt_size(bmp_size)}")
    print(f"  RLE565:     {fmt_size(rle_size)} (x{raw_size / max(rle_size, 1):.2f})")
    print(f"  zlib(raw):  {fmt_size(zlib_pixels)} (x{raw_size / max(zlib_pixels, 1):.2f})")
    print(f"  zlib(BMP):  {fmt_size(zlib_bmp)} (x{bmp_size / max(zlib_bmp, 1):.2f})")

    if prev_bmp:
        prev_pixels = extract_rgb565_pixels(prev_bmp)
        delta_size = estimate_delta_rle_size(prev_pixels, pixel_bytes) if prev_pixels else None
        if delta_size is not None:
            print(f"  Delta+RLE:  {fmt_size(delta_size)} (x{raw_size / max(delta_size, 1):.2f})")


def build_bmp_from_raw(raw_bytes: bytes, width: int, height: int) -> bytes:
    image_size = 14 + 40 + 12 + len(raw_bytes)
    pixel_offset = 14 + 40 + 12

    header = bytearray(66)
    p = 0
    header[p:p + 2] = b"BM"; p += 2
    header[p:p + 4] = image_size.to_bytes(4, "little"); p += 4
    header[p:p + 4] = (0).to_bytes(4, "little"); p += 4
    header[p:p + 4] = pixel_offset.to_bytes(4, "little"); p += 4

    header[p:p + 4] = (40).to_bytes(4, "little"); p += 4
    header[p:p + 4] = int(width).to_bytes(4, "little", signed=True); p += 4
    header[p:p + 4] = int(height).to_bytes(4, "little", signed=True); p += 4
    header[p:p + 2] = (1).to_bytes(2, "little"); p += 2
    header[p:p + 2] = (16).to_bytes(2, "little"); p += 2
    header[p:p + 4] = (3).to_bytes(4, "little"); p += 4
    header[p:p + 4] = (0).to_bytes(4, "little"); p += 4
    header[p:p + 4] = (0).to_bytes(4, "little"); p += 4
    header[p:p + 4] = (0).to_bytes(4, "little"); p += 4
    header[p:p + 4] = (0).to_bytes(4, "little"); p += 4
    header[p:p + 4] = (0).to_bytes(4, "little"); p += 4
    header[p:p + 4] = (0x00F80000).to_bytes(4, "little"); p += 4
    header[p:p + 4] = (0x0007E000).to_bytes(4, "little"); p += 4
    header[p:p + 4] = (0x0000001F).to_bytes(4, "little"); p += 4

    return bytes(header) + raw_bytes


def parse_comp_header(buf: bytes) -> Optional[dict]:
    if len(buf) < COMP_HEADER_LEN:
        return None
    magic = buf[0:2]
    version = buf[2]
    flags = buf[3]
    width = int.from_bytes(buf[4:6], "little")
    height = int.from_bytes(buf[6:8], "little")
    raw_size = int.from_bytes(buf[8:12], "little")
    payload_size = int.from_bytes(buf[12:16], "little")
    return {
        "magic": magic,
        "version": version,
        "flags": flags,
        "width": width,
        "height": height,
        "raw_size": raw_size,
        "payload_size": payload_size,
    }


def rle_decode_rgb565(payload: bytes, expected_pixels: int) -> Optional[bytes]:
    out = bytearray()
    i = 0
    while i + 3 <= len(payload) and len(out) // 2 < expected_pixels:
        run = payload[i]
        val = payload[i + 1:i + 3]
        out.extend(val * run)
        i += 3
    if len(out) // 2 != expected_pixels:
        return None
    return bytes(out)


def delta_rle_apply(prev_raw: bytes, payload: bytes) -> Optional[bytes]:
    if not prev_raw or len(prev_raw) % 2 != 0:
        return None
    out = bytearray()
    i = 0
    prev_idx = 0
    total_pixels = len(prev_raw) // 2
    while i < len(payload) and prev_idx < total_pixels:
        token = payload[i]
        i += 1
        same = (token & 0x80) != 0
        run = token & 0x7F
        if run == 0:
            return None
        if same:
            out.extend(prev_raw[prev_idx * 2:(prev_idx + run) * 2])
            prev_idx += run
        else:
            needed = run * 2
            if i + needed > len(payload):
                return None
            out.extend(payload[i:i + needed])
            i += needed
            prev_idx += run
    if len(out) != len(prev_raw):
        return None
    return bytes(out)


def decode_compressed_frame(header: dict, payload: bytes, prev_raw: Optional[bytes]) -> tuple[Optional[bytes], Optional[bytes]]:
    width = header["width"]
    height = header["height"]
    raw_size = header["raw_size"]
    flags = header["flags"]

    if header["magic"] == MAGIC_ZR:
        raw = zlib.decompress(payload)
        if len(raw) != raw_size:
            return None, None
        return build_bmp_from_raw(raw, width, height), raw

    if header["magic"] == MAGIC_DR:
        is_delta = (flags & 0x01) != 0
        pixel_count = raw_size // 2
        if is_delta:
            if not prev_raw:
                return None, None
            raw = delta_rle_apply(prev_raw, payload)
        else:
            raw = rle_decode_rgb565(payload, pixel_count)
        if not raw or len(raw) != raw_size:
            return None, None
        return build_bmp_from_raw(raw, width, height), raw

    return None, None


@dataclass
class CaptureConfig:
    """Configuration for a capture operation."""
    transport: str          # "serial" or "ble"
    mode: str               # "hex" or "binary"
    timeout: float = 60.0   # Max time to wait for transfer
    show_progress: bool = True
    stream: bool = False    # Continuous capture mode
    stream_fps: int = 1     # Frames per second in stream mode
    viewer: Optional[str] = None  # External viewer command (e.g., "catimg")
    
    # Serial options
    serial_port: Optional[str] = None
    baudrate: int = 115200
    
    # BLE options
    ble_device_name: str = "ATS-Mini"
    ble_scan_timeout: float = 10.0
    
    # Output options
    output_file: Optional[str] = None
    verbose: bool = False


class CaptureState:
    """State tracking for ongoing capture."""
    
    def __init__(self, mode: str, show_progress: bool = True):
        self.mode = mode
        self.show_progress = show_progress
        self.hexbuf = bytearray()
        self.binbuf = bytearray()
        self.bmp_size: Optional[int] = None
        self.need_total_hex: Optional[int] = None
        self.need_total_bytes: Optional[int] = None
        self.first_byte_time: Optional[float] = None
        self.last_byte_time: Optional[float] = None
        self.last_progress_time: float = 0.0
        self.raw_bytes_received = 0
        self.done = False
    
    def handle_data(self, data: bytes) -> None:
        """Process incoming data chunk."""
        now = time.time()
        if self.first_byte_time is None:
            self.first_byte_time = now
        self.last_byte_time = now
        self.raw_bytes_received += len(data)
        
        if self.mode == "binary":
            self._handle_binary(data)
        elif self.mode == "hex":
            self._handle_hex(data)
        
        # Show progress every 0.5 seconds
        if self.show_progress and now - self.last_progress_time >= 0.5:
            self._print_progress(now)
            self.last_progress_time = now
    
    def _handle_binary(self, data: bytes) -> None:
        """Process binary BMP data."""
        self.binbuf.extend(data)
        
        # Find and sync to header
        if self.bmp_size is None:
            pos = self.binbuf.find(SIG_BIN)
            if pos > 0:
                del self.binbuf[:pos]
            
            # Parse BMP header (size is at bytes 2-6, little-endian)
            if len(self.binbuf) >= 6:
                if self.binbuf[0:2] == SIG_BIN:
                    self.bmp_size = int.from_bytes(self.binbuf[2:6], "little")
                    self.need_total_bytes = self.bmp_size
        
        # Check if complete
        if self.need_total_bytes is not None and len(self.binbuf) >= self.need_total_bytes:
            self.done = True
    
    def _handle_hex(self, data: bytes) -> None:
        """Process hex-encoded BMP data."""
        # Extract hex tokens
        for m in HEX_RE.finditer(data):
            self.hexbuf.extend(m.group(0))
        
        # Sync to header
        pos = self.hexbuf.find(SIG_HEX)
        if pos > 0:
            del self.hexbuf[:pos]
        
        # Parse header
        if self.bmp_size is None and len(self.hexbuf) >= 28:
            try:
                header = binascii.unhexlify(self.hexbuf[:28])
                if header[0:2] == SIG_BIN:
                    self.bmp_size = int.from_bytes(header[2:6], "little")
                    self.need_total_hex = self.bmp_size * 2
            except binascii.Error:
                pass
        
        # Check if complete
        if self.need_total_hex is not None and len(self.hexbuf) >= self.need_total_hex:
            self.done = True
    
    def _print_progress(self, now: float) -> None:
        """Print real-time progress."""
        if not self.first_byte_time:
            return
        
        elapsed = max(now - self.first_byte_time, 0.01)
        
        if self.bmp_size:
            # Know target size
            if self.mode == "binary":
                received = len(self.binbuf)
            else:
                received = len(self.hexbuf) // 2
            
            progress = min(100.0 * received / self.bmp_size, 100.0)
            rate = received / elapsed if elapsed > 0 else 0
            remaining = max(self.bmp_size - received, 0)
            eta = remaining / rate if rate > 0 else 0
            
            rate_str = self._fmt_rate(rate)
            eta_str = self._fmt_time(eta)
            
            print(f"  Progress: {progress:5.1f}% | {received:,}/{self.bmp_size:,} bytes | {rate_str} | ETA: {eta_str}", end="\r")
        else:
            # Don't know size yet
            rate = self.raw_bytes_received / elapsed if elapsed > 0 else 0
            rate_str = self._fmt_rate(rate)
            print(f"  Received: {self.raw_bytes_received:,} bytes | {rate_str} | Waiting for header...", end="\r")
    
    def get_bmp(self) -> Optional[bytes]:
        """Extract final BMP image."""
        if self.mode == "binary":
            if self.need_total_bytes and len(self.binbuf) >= self.need_total_bytes:
                return bytes(self.binbuf[:self.need_total_bytes])
        elif self.mode == "hex":
            if self.need_total_hex and len(self.hexbuf) >= self.need_total_hex:
                try:
                    return binascii.unhexlify(self.hexbuf[:self.need_total_hex])
                except binascii.Error:
                    return None
        return None
    
    @staticmethod
    def _fmt_rate(bps: float) -> str:
        """Format bytes per second."""
        if bps >= 1024 * 1024:
            return f"{bps / (1024 * 1024):.2f} MiB/s"
        if bps >= 1024:
            return f"{bps / 1024:.2f} KiB/s"
        return f"{bps:.1f} B/s"
    
    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Format time duration."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = seconds / 60
        return f"{minutes:.1f}m"


async def capture_serial(config: CaptureConfig) -> tuple[Optional[bytes], dict]:
    """Capture via serial connection."""
    if not PYSERIAL_AVAILABLE:
        return None, {"error": "pyserial not available"}
    
    if not config.serial_port:
        return None, {"error": "serial_port required"}
    
    # Determine command
    if config.mode == "binary":
        cmd = 'c'
    elif config.mode == "hex":
        cmd = 'C'
    elif config.mode == "zlib":
        cmd = 'z'
    elif config.mode == "delta":
        cmd = 'd'
    else:
        return None, {"error": f"Unsupported mode: {config.mode}"}

    if config.mode in ("zlib", "delta"):
        return await capture_serial_compressed(config, cmd)
    state = CaptureState(config.mode, config.show_progress)
    
    start_time = time.time()
    
    try:
        with serial.Serial(config.serial_port, config.baudrate, timeout=1) as ser:
            # Clear buffer
            ser.reset_input_buffer()
            
            # Send command
            ser.write(cmd.encode("ascii"))
            ser.flush()
            
            # Read with timeout
            deadline = time.time() + config.timeout
            last_data_time = time.time()
            stall_timeout = 3.0
            
            while time.time() < deadline:
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting)
                    state.handle_data(data)
                    last_data_time = time.time()
                    
                    if state.done:
                        break
                else:
                    if state.done:
                        break
                    
                    if time.time() - last_data_time > stall_timeout:
                        if config.show_progress:
                            print(f"\n  Warning: No data for {stall_timeout}s")
                        break
                
                time.sleep(0.01)
            
            if config.show_progress:
                print()
            
            # Get result
            bmp = state.get_bmp()
            elapsed = time.time() - start_time
            
            if not bmp:
                return None, {
                    "error": "Failed to capture image",
                    "bytes_received": state.raw_bytes_received,
                    "elapsed": elapsed
                }
            
            # Calculate metrics
            transfer_time = state.last_byte_time - state.first_byte_time if state.first_byte_time else elapsed
            rate = len(bmp) / transfer_time if transfer_time > 0 else 0
            
            return bmp, {
                "bmp_size": len(bmp),
                "transfer_time": transfer_time,
                "elapsed": elapsed,
                "raw_bytes": state.raw_bytes_received,
                "rate": rate,
            }
    
    except Exception as e:
        return None, {"error": str(e)}


async def capture_ble(config: CaptureConfig) -> tuple[Optional[bytes], dict]:
    """Capture via BLE connection."""
    if not BLEAK_AVAILABLE:
        return None, {"error": "bleak not available"}
    
    # Determine command
    if config.mode == "binary":
        cmd = 'c'
    elif config.mode == "hex":
        cmd = 'C'
    elif config.mode == "zlib":
        cmd = 'z'
    elif config.mode == "delta":
        cmd = 'd'
    else:
        return None, {"error": f"Unsupported mode: {config.mode}"}

    if config.mode in ("zlib", "delta"):
        return await capture_ble_compressed(config, cmd)
    state = CaptureState(config.mode, config.show_progress)
    
    start_time = time.time()
    
    try:
        # Find device
        if config.show_progress:
            print("  Scanning for BLE device...")
        
        device = None
        t0 = time.time()
        while time.time() - t0 < config.ble_scan_timeout:
            found = await BleakScanner.discover(timeout=3.0)
            for d in found:
                if d.name == config.ble_device_name:
                    device = d
                    break
            if device:
                break
        
        if not device:
            return None, {"error": f"Device {config.ble_device_name} not found"}
        
        if config.show_progress:
            print(f"  Connecting to {config.ble_device_name}...")
        
        # Connect and capture
        async with BleakClient(device) as client:
            # Start notifications
            await client.start_notify(
                NUS_TX,
                lambda sender, data: state.handle_data(bytes(data))
            )
            
            # Send command
            await client.write_gatt_char(NUS_RX, cmd.encode("ascii"), response=True)
            
            if config.show_progress:
                print(f"  Capturing ({config.mode} mode)...")
            
            # Monitor with timeout
            deadline = time.time() + config.timeout
            last_data_time = time.time()
            stall_timeout = 20.0
            
            while time.time() < deadline:
                if state.done:
                    break
                
                if state.last_byte_time:
                    idle = time.time() - state.last_byte_time
                    if idle > stall_timeout:
                        if config.show_progress:
                            print(f"\n  Warning: No data for {idle:.1f}s")
                        break
                
                await asyncio.sleep(0.1)
            
            if config.show_progress:
                print()
            
            # Get result
            bmp = state.get_bmp()
            elapsed = time.time() - start_time
            
            if not bmp:
                return None, {
                    "error": "Failed to capture image",
                    "bytes_received": state.raw_bytes_received,
                    "elapsed": elapsed
                }
            
            # Calculate metrics
            transfer_time = state.last_byte_time - state.first_byte_time if state.first_byte_time else elapsed
            rate = len(bmp) / transfer_time if transfer_time > 0 else 0
            
            return bmp, {
                "bmp_size": len(bmp),
                "transfer_time": transfer_time,
                "elapsed": elapsed,
                "raw_bytes": state.raw_bytes_received,
                "rate": rate,
            }
    
    except Exception as e:
        return None, {"error": str(e)}


async def capture(config: CaptureConfig) -> tuple[Optional[bytes], dict]:
    """Universal capture function - routes to appropriate transport."""
    if config.transport == "serial":
        return await capture_serial(config)
    elif config.transport == "ble":
        return await capture_ble(config)
    else:
        return None, {"error": f"Unknown transport: {config.transport}"}


def serial_read_exact(ser: "serial.Serial", size: int, deadline: float) -> Optional[bytes]:
    buf = bytearray()
    while len(buf) < size and time.time() < deadline:
        if ser.in_waiting > 0:
            buf.extend(ser.read(min(ser.in_waiting, size - len(buf))))
        else:
            time.sleep(0.005)
    return bytes(buf) if len(buf) == size else None


async def capture_serial_compressed(config: CaptureConfig, cmd: str) -> tuple[Optional[bytes], dict]:
    if not PYSERIAL_AVAILABLE:
        return None, {"error": "pyserial not available"}

    start_time = time.time()
    prev_raw = None
    if config.mode == "delta":
        prev_raw = getattr(config, "_prev_raw", None)

    try:
        with serial.Serial(config.serial_port, config.baudrate, timeout=1) as ser:
            # Aggressive buffer clearing
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            time.sleep(0.2)
            ser.reset_input_buffer()
            
            # Send command
            ser.write(cmd.encode("ascii"))
            ser.flush()
            
            # Add delay for device to process command
            time.sleep(0.15)
            
            # Drain any extra bytes that might have come through
            for _ in range(5):
                if ser.in_waiting > 0:
                    ser.read(ser.in_waiting)
                time.sleep(0.01)

            deadline = time.time() + config.timeout
            header = serial_read_exact(ser, COMP_HEADER_LEN, deadline)
            if not header:
                return None, {"error": "Timeout waiting for header"}

            # Check if device fell back to binary mode (firmware doesn't have zlib)
            if header[:2] == b"BM":
                # Device sent uncompressed BMP - this happens when firmware has no zlib support
                # We need to read the rest of the BMP data
                bmp_header = header
                # Read the rest of the BMP (header indicates it's a BM signature)
                # For a 320x170 RGB565 BMP, total size should be ~108,866 bytes
                # BMP header is 54 bytes + color table (if needed) + pixel data
                deadline = time.time() + config.timeout
                remaining_data = bytearray()
                while time.time() < deadline:
                    if ser.in_waiting > 0:
                        remaining_data.extend(ser.read(min(ser.in_waiting, 4096)))
                    else:
                        time.sleep(0.01)
                    # Check if we have a complete BMP
                    full_bmp = bmp_header + remaining_data
                    if len(full_bmp) >= 108800:  # Reasonable minimum for our resolution
                        break
                
                bmp = bytes(bmp_header + remaining_data) if remaining_data else bmp_header
                transfer_time = time.time() - start_time
                return bmp, {
                    "bmp_size": len(bmp),
                    "transfer_time": transfer_time,
                    "elapsed": transfer_time,
                    "raw_bytes": len(bmp),
                    "rate": len(bmp) / max(transfer_time, 0.001),
                    "note": "Device fell back to uncompressed BMP (zlib not available)",
                }

            # Validate header magic
            if header[:2] not in (b"DR", b"ZR"):
                return None, {"error": f"Corrupted/invalid header: {header[:2].hex()}. Try --mode binary"}

            header_info = parse_comp_header(header)
            if not header_info:
                return None, {"error": "Invalid compressed header"}

            payload = serial_read_exact(ser, header_info["payload_size"], deadline)
            if payload is None:
                return None, {"error": "Timeout waiting for payload"}

            bmp, raw = decode_compressed_frame(header_info, payload, prev_raw)
            if not bmp or not raw:
                return None, {"error": "Failed to decode compressed frame"}

            if config.mode == "delta":
                config._prev_raw = raw

            transfer_time = time.time() - start_time
            return bmp, {
                "bmp_size": len(bmp),
                "transfer_time": transfer_time,
                "elapsed": transfer_time,
                "raw_bytes": len(payload) + COMP_HEADER_LEN,
                "rate": len(bmp) / max(transfer_time, 0.001),
            }
    except Exception as e:
        return None, {"error": str(e)}


class CompressedState:
    def __init__(self):
        self.buf = bytearray()
        self.header = None
        self.expected = None
        self.done_event = asyncio.Event()
        self.first_byte_time: Optional[float] = None
        self.last_byte_time: Optional[float] = None

    def handle_data(self, data: bytes) -> None:
        now = time.time()
        if self.first_byte_time is None:
            self.first_byte_time = now
        self.last_byte_time = now
        self.buf.extend(data)
        if self.header is None and len(self.buf) >= COMP_HEADER_LEN:
            self.header = parse_comp_header(self.buf[:COMP_HEADER_LEN])
            if self.header:
                self.expected = COMP_HEADER_LEN + self.header["payload_size"]
        if self.expected is not None and len(self.buf) >= self.expected:
            self.done_event.set()


async def capture_ble_compressed(config: CaptureConfig, cmd: str) -> tuple[Optional[bytes], dict]:
    if not BLEAK_AVAILABLE:
        return None, {"error": "bleak not available"}

    start_time = time.time()
    prev_raw = None
    if config.mode == "delta":
        prev_raw = getattr(config, "_prev_raw", None)
    state = CompressedState()

    try:
        device = None
        t0 = time.time()
        while time.time() - t0 < config.ble_scan_timeout:
            found = await BleakScanner.discover(timeout=3.0)
            for d in found:
                if d.name == config.ble_device_name:
                    device = d
                    break
            if device:
                break

        if not device:
            return None, {"error": f"Device {config.ble_device_name} not found"}

        async with BleakClient(device) as client:
            await client.start_notify(NUS_TX, lambda sender, data: state.handle_data(bytes(data)))
            await client.write_gatt_char(NUS_RX, cmd.encode("ascii"), response=True)

            try:
                await asyncio.wait_for(state.done_event.wait(), timeout=config.timeout)
            except asyncio.TimeoutError:
                return None, {"error": "Timeout waiting for transfer"}

        if not state.header:
            # Check if device fell back to binary mode (BM signature)
            if state.buf[:2] == b"BM":
                bmp = bytes(state.buf)
                transfer_time = (state.last_byte_time - state.first_byte_time) if state.first_byte_time else (time.time() - start_time)
                return bmp, {
                    "bmp_size": len(bmp),
                    "transfer_time": transfer_time,
                    "elapsed": time.time() - start_time,
                    "raw_bytes": len(bmp),
                    "rate": len(bmp) / max(transfer_time, 0.001),
                    "note": "Device fell back to uncompressed BMP (zlib not available)",
                }
            return None, {"error": "Invalid compressed header"}

        payload = bytes(state.buf[COMP_HEADER_LEN:COMP_HEADER_LEN + state.header["payload_size"]])
        bmp, raw = decode_compressed_frame(state.header, payload, prev_raw)
        if not bmp or not raw:
            return None, {"error": "Failed to decode compressed frame"}

        if config.mode == "delta":
            config._prev_raw = raw

        transfer_time = (state.last_byte_time - state.first_byte_time) if state.first_byte_time else (time.time() - start_time)
        return bmp, {
            "bmp_size": len(bmp),
            "transfer_time": transfer_time,
            "elapsed": time.time() - start_time,
            "raw_bytes": len(payload) + COMP_HEADER_LEN,
            "rate": len(bmp) / max(transfer_time, 0.001),
        }
    except Exception as e:
        return None, {"error": str(e)}


async def stream_capture(config: CaptureConfig) -> int:
    """Continuous capture and stream to external viewer."""
    try:
        frame_count = 0
        start_time = time.time()
        prev_raw = None
        
        # Create temp directory for frame files if using viewer
        temp_dir = None
        if config.viewer:
            temp_dir = tempfile.mkdtemp(prefix="ats_mini_")
        
        while True:
            # Capture frame
            config_no_progress = CaptureConfig(
                transport=config.transport,
                mode=config.mode,
                timeout=config.timeout,
                show_progress=False,  # Don't show progress in stream mode
                stream=False,
                stream_fps=config.stream_fps,
                viewer=config.viewer,
                serial_port=config.serial_port,
                baudrate=config.baudrate,
                ble_device_name=config.ble_device_name,
                ble_scan_timeout=config.ble_scan_timeout,
                verbose=config.verbose
            )
            if config.mode == "delta" and prev_raw is not None:
                config_no_progress._prev_raw = prev_raw
            
            bmp_data, info = await capture(config_no_progress)
            if config.mode == "delta":
                prev_raw = getattr(config_no_progress, "_prev_raw", prev_raw)
            
            if not bmp_data:
                print(f"✗ Capture failed: {info.get('error', 'Unknown error')}", file=sys.stderr)
                return 1
            
            # Prepare stats line
            elapsed = time.time() - start_time
            frame_rate = (frame_count + 1) / elapsed if elapsed > 0 else 0
            rate_str = CaptureState._fmt_rate(info['rate'])
            stats_line = (
                f"[Frame {frame_count+1:4d}] FPS: {frame_rate:5.2f} | "
                f"Transfer: {rate_str:12s} | Size: {info['bmp_size']:6,}B | "
                f"Time: {info['transfer_time']:6.2f}s"
            )

            # Stream to viewer if specified
            if config.viewer:
                try:
                    # Write to temporary file
                    temp_file = Path(temp_dir) / f"frame_{frame_count:06d}.bmp"
                    temp_file.write_bytes(bmp_data)

                    # Quote the file path to handle spaces and special chars
                    quoted_path = f'"{str(temp_file)}"'

                    # Build viewer command - support {} placeholder or append filename
                    if "{}" in config.viewer:
                        cmd = config.viewer.format(quoted_path)
                    else:
                        cmd = f"{config.viewer} {quoted_path}"

                    if config.verbose:
                        print(f"[Debug] Running viewer: {cmd}", file=sys.stderr)
                        print(f"[Debug] File exists: {temp_file.exists()}", file=sys.stderr)

                    # Clear terminal and print stats line at top before image
                    sys.stdout.write("\033[2J\033[H")
                    sys.stdout.write(stats_line + "\n")
                    sys.stdout.flush()

                    # Run viewer - let it access stdout/stderr directly for terminal display
                    proc = subprocess.Popen(
                        cmd,
                        stderr=subprocess.PIPE if config.verbose else subprocess.DEVNULL,
                        shell=True
                    )

                    try:
                        _, stderr = proc.communicate(timeout=5)
                        if proc.returncode != 0 and config.verbose:
                            print(f"[Debug] Viewer returned code {proc.returncode}", file=sys.stderr)
                            if stderr:
                                print(f"[Debug] Viewer stderr: {stderr.decode()}", file=sys.stderr)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        if config.verbose:
                            print(f"[Debug] Viewer timeout", file=sys.stderr)

                    # Clean up old frame files (keep only last 3)
                    all_frames = sorted(Path(temp_dir).glob("frame_*.bmp"))
                    for old_frame in all_frames[:-3]:
                        old_frame.unlink()

                except FileNotFoundError:
                    print(f"✗ Viewer not found: {config.viewer.split()[0]}", file=sys.stderr)
                    print(f"   Install it and try again (e.g., 'brew install catimg')", file=sys.stderr)
                    return 1
                except Exception as e:
                    print(f"✗ Viewer error: {e}", file=sys.stderr)
                    return 1
            else:
                # No viewer - output to stdout as binary stream
                try:
                    sys.stdout.buffer.write(bmp_data)
                    sys.stdout.buffer.flush()
                except BrokenPipeError:
                    # Normal when piped to another command that closes
                    return 0

                # Print stats to stderr so they don't interfere with output
                print(stats_line, file=sys.stderr)
            
            # Control frame rate
            if config.stream_fps > 0:
                frame_delay = 1.0 / config.stream_fps
                await asyncio.sleep(frame_delay)
            
            frame_count += 1
    
    except KeyboardInterrupt:
        print(f"\nStream stopped. Captured {frame_count} frames.", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"✗ Stream error: {e}", file=sys.stderr)
        return 1
    finally:
        # Clean up temp directory
        if temp_dir and Path(temp_dir).exists():
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass




def save_bmp(bmp_data: bytes, output_file: str) -> bool:
    """Save BMP data to file."""
    try:
        Path(output_file).write_bytes(bmp_data)
        return True
    except Exception as e:
        print(f"Error saving: {e}", file=sys.stderr)
        return False


async def async_main() -> int:
    """Main entry point."""
    try:
        ap = argparse.ArgumentParser(
            description="Capture screenshots from ATS-Mini via serial or BLE",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Capture via serial in binary mode (fastest)
  %(prog)s --transport serial --mode binary -p /dev/cu.usbmodem1101 -o screenshot.bmp
  
  # Capture via BLE in binary mode
  %(prog)s --transport ble --mode binary -o screenshot.bmp
  
  # Stream to catimg viewer (displays each frame)
  %(prog)s --stream --viewer catimg --transport ble --mode binary
  
  # Stream via serial to fbi viewer at 2 FPS
  %(prog)s --stream --fps 2 --viewer "fbi -a" --transport serial --mode binary -p /dev/cu.usbmodem1101
  
  # Custom viewer with explicit file path
  %(prog)s --stream --viewer "catimg {}" --transport ble --mode binary
  
  # Stream raw BMP to stdout (pipe to any tool)
  %(prog)s --stream --transport ble --mode binary | catimg
        """
        )
        
        # Transport and mode
        ap.add_argument("--transport", choices=["serial", "ble"], default="serial",
                   help="Transport: serial or BLE (default: serial)")
        ap.add_argument("--mode", choices=["hex", "binary", "zlib", "delta"], default="binary",
                   help="Capture mode: hex, binary, zlib, or delta (default: binary)")
        
        # Serial options
        ap.add_argument("-p", "--port", dest="serial_port",
                       help="Serial port device (required for serial transport)")
        ap.add_argument("--baudrate", type=int, default=115200,
                       help="Serial baudrate (default: 115200)")
        
        # BLE options
        ap.add_argument("--device-name", default="ATS-Mini",
                       help="BLE device name (default: ATS-Mini)")
        ap.add_argument("--ble-scan-timeout", type=float, default=10.0,
                       help="BLE scan timeout (default: 10s)")
        
        # Transfer options
        ap.add_argument("--timeout", type=float, default=60.0,
                       help="Max transfer time (default: 60s)")
        
        # Streaming options
        ap.add_argument("--stream", action="store_true",
                   help="Enable continuous capture mode (delta recommended)")
        ap.add_argument("--fps", dest="stream_fps", type=int, default=1,
                       help="Stream frames per second (default: 1)")
        ap.add_argument("--viewer", default=None,
                       help="External viewer command to display BMP frames (e.g., 'catimg', 'fbi -a', or use {} for file path)")
        
        # Output options
        ap.add_argument("-o", "--output", dest="output_file",
                       help="Save to file (default: print to stdout)")
        ap.add_argument("--no-progress", action="store_true",
                       help="Disable progress display")
        ap.add_argument("-v", "--verbose", action="store_true",
                       help="Verbose output")
        
        # Analysis options
        ap.add_argument("--analyze", dest="analyze_file",
                   help="Analyze an existing BMP file and exit")
        ap.add_argument("--analyze-after", action="store_true",
                   help="Analyze compression stats after capture")
        ap.add_argument("--analyze-delta", dest="analyze_delta",
                   help="Previous BMP for delta analysis (with --analyze or --analyze-after)")
        
        args = ap.parse_args()
        
        # Analyze existing file only
        if args.analyze_file:
            bmp_data = Path(args.analyze_file).read_bytes()
            prev_bmp = Path(args.analyze_delta).read_bytes() if args.analyze_delta else None
            analyze_bmp_compression(bmp_data, prev_bmp)
            return 0

        # Validate
        if args.transport == "serial" and not args.serial_port:
            print("Error: --port required for serial transport", file=sys.stderr)
            return 1
        
        if args.transport == "ble" and not BLEAK_AVAILABLE:
            print("Error: bleak required for BLE (pip install bleak)", file=sys.stderr)
            return 1
        
        # Create config
        config = CaptureConfig(
            transport=args.transport,
            mode=args.mode,
            timeout=args.timeout,
            show_progress=not args.no_progress,
            stream=args.stream,
            stream_fps=args.stream_fps,
            viewer=args.viewer,
            serial_port=args.serial_port,
            baudrate=args.baudrate,
            ble_device_name=args.device_name,
            ble_scan_timeout=args.ble_scan_timeout,
            output_file=args.output_file,
            verbose=args.verbose
        )
        
        # Handle streaming mode
        if args.stream:
            return await stream_capture(config)
        
        # Print header (for non-streaming mode)
        print(f"ATS-Mini Screenshot Capture")
        print(f"Transport: {config.transport}, Mode: {config.mode}")
        print()
        
        # Capture
        bmp_data, info = await capture(config)
        
        if not bmp_data:
            error = info.get("error", "Unknown error")
            print(f"✗ Capture failed: {error}", file=sys.stderr)
            if args.verbose and info:
                for key, value in info.items():
                    if key != "error":
                        print(f"  {key}: {value}", file=sys.stderr)
            return 1
        
        # Success
        print(f"✓ Capture successful!")
        print(f"  Image size: {info['bmp_size']:,} bytes")
        print(f"  Transfer time: {info['transfer_time']:.2f}s")
        print(f"  Rate: {CaptureState._fmt_rate(info['rate'])}")
        
        # Save or output
        if config.output_file:
            if save_bmp(bmp_data, config.output_file):
                print(f"  Saved to: {config.output_file}")
            else:
                return 1
        else:
            # Output binary to stdout
            sys.stdout.buffer.write(bmp_data)
        
        if args.analyze_after:
            prev_bmp = Path(args.analyze_delta).read_bytes() if args.analyze_delta else None
            analyze_bmp_compression(bmp_data, prev_bmp)
        
        return 0
    
    except KeyboardInterrupt:
        print("\n✗ Interrupted by user", file=sys.stderr)
        return 130


def main() -> int:
    """Sync wrapper."""
    try:
        if sys.version_info >= (3, 7):
            return asyncio.run(async_main())
        else:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_main())
    except KeyboardInterrupt:
        print("\n✗ Interrupted by user", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
