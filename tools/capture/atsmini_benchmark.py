#!/usr/bin/env python3
"""
ATS-Mini Screenshot Capture Benchmark

Benchmarks serial and BLE screenshot capture with hex and binary modes.
Measures throughput, transfer time, and overhead.
"""

from __future__ import annotations

import argparse
import asyncio
import binascii
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from bleak import BleakClient, BleakScanner
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False
    print("Warning: bleak not available, BLE benchmarks disabled", file=sys.stderr)

try:
    import serial
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False
    print("Warning: pyserial not available, serial benchmarks disabled", file=sys.stderr)


NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

HEX_RE = re.compile(rb"[0-9a-fA-F]+")
SIG_HEX = b"424d"  # "BM" in ASCII hex
SIG_BIN = b"BM"


def fmt_rate(bps: float) -> str:
    if bps >= 1024 * 1024:
        return f"{bps / (1024 * 1024):.2f} MiB/s"
    if bps >= 1024:
        return f"{bps / 1024:.2f} KiB/s"
    return f"{bps:.1f} B/s"


def fmt_time(seconds: float) -> str:
    if seconds < 1.0:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.2f}s"


@dataclass
class BenchmarkResult:
    """Results from a single capture benchmark run."""
    transport: str              # "serial" or "ble"
    mode: str                   # "hex" or "binary"
    success: bool
    bmp_size: Optional[int]     # Final BMP size in bytes
    transfer_time: Optional[float]  # Time from first byte to last byte (seconds)
    total_time: Optional[float]     # Total time including setup (seconds)
    raw_bytes: Optional[int]    # Raw bytes received (before filtering)
    effective_rate: Optional[float]  # BMP bytes per second
    raw_rate: Optional[float]        # Raw transport bytes per second
    overhead_pct: Optional[float]    # Percentage overhead (hex encoding, newlines, etc.)
    error: Optional[str]        # Error message if failed

    def print_summary(self, index: int = 0) -> None:
        """Print formatted benchmark results."""
        prefix = f"[{index}]" if index > 0 else ""
        print(f"\n{prefix} {self.transport.upper()} / {self.mode.upper()}")
        print("-" * 60)
        
        if not self.success:
            print(f"❌ FAILED: {self.error}")
            return
        
        print(f"✅ SUCCESS")
        print(f"BMP size:        {self.bmp_size:,} bytes")
        print(f"Transfer time:   {fmt_time(self.transfer_time)}")
        print(f"Total time:      {fmt_time(self.total_time)}")
        print(f"Raw bytes:       {self.raw_bytes:,} bytes")
        print(f"Overhead:        {self.overhead_pct:.1f}%")
        print(f"Effective rate:  {fmt_rate(self.effective_rate)}")
        print(f"Raw rate:        {fmt_rate(self.raw_rate)}")


class CaptureStateBenchmark:
    """Capture state for benchmarking (minimal logging)."""
    
    def __init__(self, binary: bool = False, show_progress: bool = True):
        self.binary = binary
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
        self.done_event = asyncio.Event()
    
    def handle_data(self, data: bytes) -> None:
        """Handle incoming data (BLE or serial)."""
        now = time.time()
        if self.first_byte_time is None:
            self.first_byte_time = now
        self.last_byte_time = now
        self.raw_bytes_received += len(data)
        
        if self.binary:
            self._handle_binary(data)
        else:
            self._handle_hex(data)
        
        # Show progress every 0.5 seconds
        if self.show_progress and now - self.last_progress_time >= 0.5:
            self._print_progress(now)
            self.last_progress_time = now
    
    def _handle_binary(self, data: bytes) -> None:
        """Handle binary BMP data."""
        self.binbuf.extend(data)
        
        # Only sync to signature if we haven't found the header yet
        # Once found, don't search again (pixel data can contain "BM" bytes!)
        if self.bmp_size is None:
            pos = self.binbuf.find(SIG_BIN)
            if pos > 0:
                del self.binbuf[:pos]
            
            # Parse header
            if len(self.binbuf) >= 6:
                if self.binbuf[0:2] == SIG_BIN:
                    self.bmp_size = int.from_bytes(self.binbuf[2:6], "little")
                    self.need_total_bytes = self.bmp_size
        
        # Check completion
        if self.need_total_bytes is not None and len(self.binbuf) >= self.need_total_bytes:
            self.done_event.set()
    
    def _handle_hex(self, data: bytes) -> None:
        """Handle hex-encoded BMP data."""
        # Extract hex tokens
        for m in HEX_RE.finditer(data):
            self.hexbuf.extend(m.group(0))
        
        # Sync to signature
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
        
        # Check completion
        if self.need_total_hex is not None and len(self.hexbuf) >= self.need_total_hex:
            self.done_event.set()
    
    def _print_progress(self, now: float) -> None:
        """Print real-time progress update."""
        if not self.first_byte_time:
            return
        
        elapsed = max(now - self.first_byte_time, 0.01)
        
        if self.bmp_size:
            # We know the target size
            if self.binary:
                received = len(self.binbuf)
            else:
                received = len(self.hexbuf) // 2  # Hex chars to bytes
            
            progress = min(100.0 * received / self.bmp_size, 100.0)
            
            # Calculate rate and ETA based on actual BMP bytes
            effective_rate = received / elapsed if elapsed > 0 else 0
            remaining = max(self.bmp_size - received, 0)
            eta = remaining / effective_rate if effective_rate > 0 else 0
            
            # Show raw transport rate for reference
            raw_rate = self.raw_bytes_received / elapsed
            
            print(f"  Progress: {progress:5.1f}% | {received:,}/{self.bmp_size:,} bytes | "
                  f"{fmt_rate(effective_rate)} | Raw: {fmt_rate(raw_rate)} | ETA: {fmt_time(eta)}", end="\r")
        else:
            # Don't know size yet
            raw_rate = self.raw_bytes_received / elapsed
            print(f"  Received: {self.raw_bytes_received:,} bytes | {fmt_rate(raw_rate)} | "
                  f"Waiting for header...", end="\r")
    
    def get_bmp(self) -> Optional[bytes]:
        """Extract final BMP bytes."""
        if self.binary:
            if self.need_total_bytes and len(self.binbuf) >= self.need_total_bytes:
                return bytes(self.binbuf[:self.need_total_bytes])
        else:
            if self.need_total_hex and len(self.hexbuf) >= self.need_total_hex:
                try:
                    return binascii.unhexlify(self.hexbuf[:self.need_total_hex])
                except binascii.Error:
                    pass
        return None


async def benchmark_ble(device_name: str, cmd: str, binary: bool, 
                       scan_timeout: float, max_seconds: float, show_progress: bool = True) -> BenchmarkResult:
    """Benchmark BLE capture."""
    if not BLEAK_AVAILABLE:
        return BenchmarkResult(
            transport="ble", mode="binary" if binary else "hex",
            success=False, bmp_size=None, transfer_time=None, total_time=None,
            raw_bytes=None, effective_rate=None, raw_rate=None, overhead_pct=None,
            error="bleak library not available"
        )
    
    start_time = time.time()
    state = CaptureStateBenchmark(binary=binary, show_progress=show_progress)
    
    try:
        # Find device
        device = None
        t0 = time.time()
        while time.time() - t0 < scan_timeout:
            found = await BleakScanner.discover(timeout=3.0)
            for d in found:
                if d.name == device_name:
                    device = d
                    break
            if device:
                break
        
        if not device:
            return BenchmarkResult(
                transport="ble", mode="binary" if binary else "hex",
                success=False, bmp_size=None, transfer_time=None, total_time=None,
                raw_bytes=None, effective_rate=None, raw_rate=None, overhead_pct=None,
                error=f"Device {device_name} not found"
            )
        
        # Connect and capture
        async with BleakClient(device) as client:
            # Start notifications
            await client.start_notify(
                NUS_TX,
                lambda sender, data: state.handle_data(bytes(data))
            )
            
            # Send command
            await client.write_gatt_char(NUS_RX, cmd.encode("ascii"), response=True)
            
            # Monitor for stalls with a watchdog task
            async def watchdog():
                """Monitor for data stalls."""
                stall_timeout = 20.0  # 20 seconds with no data = stalled (BLE can be very slow with large transfers)
                while not state.done_event.is_set():
                    await asyncio.sleep(1.0)
                    if state.last_byte_time is not None:
                        idle_time = time.time() - state.last_byte_time
                        if idle_time > stall_timeout:
                            if state.show_progress:
                                print(f"\n  Warning: No data for {idle_time:.1f}s - transfer may be stalled")
                            # Check if we're actually complete before breaking
                            if state.bmp_size and state.raw_bytes_received >= state.bmp_size * 0.9:
                                # Close to complete - check if done
                                bmp = state.get_bmp()
                                if bmp and len(bmp) == state.bmp_size:
                                    state.done_event.set()
                                    return
                            return  # Exit watchdog, will trigger timeout
            
            # Wait for completion or stall
            watchdog_task = asyncio.create_task(watchdog())
            try:
                done, pending = await asyncio.wait(
                    [asyncio.create_task(state.done_event.wait()), watchdog_task],
                    timeout=max_seconds,
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                if state.show_progress:
                    print()  # New line after progress updates
                
                # Check if we completed successfully
                if not state.done_event.is_set():
                    # Final check - might have completed just as timeout/stall hit
                    bmp = state.get_bmp()
                    if bmp and len(bmp) > 0:
                        # Data looks complete, continue to metrics
                        pass
                    else:
                        return BenchmarkResult(
                            transport="ble", mode="binary" if binary else "hex",
                            success=False, bmp_size=state.bmp_size, transfer_time=None,
                            total_time=time.time() - start_time,
                            raw_bytes=state.raw_bytes_received, effective_rate=None,
                            raw_rate=None, overhead_pct=None,
                            error=f"Transfer stalled at {state.raw_bytes_received} bytes"
                        )
            except asyncio.TimeoutError:
                watchdog_task.cancel()
                if state.show_progress:
                    print()  # New line after progress updates
                
                return BenchmarkResult(
                    transport="ble", mode="binary" if binary else "hex",
                    success=False, bmp_size=state.bmp_size, transfer_time=None,
                    total_time=time.time() - start_time,
                    raw_bytes=state.raw_bytes_received, effective_rate=None,
                    raw_rate=None, overhead_pct=None,
                    error="Timeout waiting for transfer"
                )
        
        # Calculate metrics
        total_time = time.time() - start_time
        transfer_time = state.last_byte_time - state.first_byte_time if state.first_byte_time else None
        bmp = state.get_bmp()
        
        if not bmp or not transfer_time:
            return BenchmarkResult(
                transport="ble", mode="binary" if binary else "hex",
                success=False, bmp_size=None, transfer_time=None, total_time=total_time,
                raw_bytes=state.raw_bytes_received, effective_rate=None, 
                raw_rate=None, overhead_pct=None,
                error="Failed to decode BMP"
            )
        
        bmp_size = len(bmp)
        effective_rate = bmp_size / transfer_time
        raw_rate = state.raw_bytes_received / transfer_time
        overhead_pct = ((state.raw_bytes_received - bmp_size) / bmp_size) * 100
        
        return BenchmarkResult(
            transport="ble", mode="binary" if binary else "hex",
            success=True, bmp_size=bmp_size, transfer_time=transfer_time,
            total_time=total_time, raw_bytes=state.raw_bytes_received,
            effective_rate=effective_rate, raw_rate=raw_rate, overhead_pct=overhead_pct,
            error=None
        )
    
    except Exception as e:
        return BenchmarkResult(
            transport="ble", mode="binary" if binary else "hex",
            success=False, bmp_size=None, transfer_time=None,
            total_time=time.time() - start_time, raw_bytes=None,
            effective_rate=None, raw_rate=None, overhead_pct=None,
            error=str(e)
        )


def benchmark_serial(port: str, baudrate: int, cmd: str, binary: bool,
                    max_seconds: float, show_progress: bool = True) -> BenchmarkResult:
    """Benchmark serial capture."""
    if not PYSERIAL_AVAILABLE:
        return BenchmarkResult(
            transport="serial", mode="binary" if binary else "hex",
            success=False, bmp_size=None, transfer_time=None, total_time=None,
            raw_bytes=None, effective_rate=None, raw_rate=None, overhead_pct=None,
            error="pyserial library not available"
        )
    
    start_time = time.time()
    state = CaptureStateBenchmark(binary=binary, show_progress=show_progress)
    
    try:
        with serial.Serial(port, baudrate, timeout=1) as ser:
            # Clear buffer
            ser.reset_input_buffer()
            
            # Send command
            ser.write(cmd.encode("ascii"))
            ser.flush()
            
            # Read data
            deadline = time.time() + max_seconds
            last_data_time = time.time()
            stall_timeout = 3.0  # 3 seconds with no data = check if complete
            
            while time.time() < deadline:
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting)
                    state.handle_data(data)
                    last_data_time = time.time()
                    
                    if state.done_event.is_set():
                        break
                else:
                    # No data available - check if we might be done
                    if state.done_event.is_set():
                        break
                    
                    # Check for stall only if we've waited long enough
                    if time.time() - last_data_time > stall_timeout:
                        # Final check - might have completed during the wait
                        if state.done_event.is_set():
                            break
                        
                        # Truly stalled
                        if state.show_progress:
                            print(f"\n  Warning: No data received for {stall_timeout}s, transfer may be stalled")
                        break
                
                time.sleep(0.01)
            
            if state.show_progress:
                print()  # New line after progress updates
            
            if not state.done_event.is_set():
                # Provide more detailed error based on what we received
                if state.bmp_size and state.raw_bytes_received > 0:
                    if state.binary:
                        received = len(state.binbuf)
                    else:
                        received = len(state.hexbuf) // 2
                    pct = 100.0 * received / state.bmp_size
                    error_msg = f"Transfer incomplete: {received}/{state.bmp_size} bytes ({pct:.1f}%)"
                else:
                    error_msg = "Transfer incomplete or timeout"
                
                return BenchmarkResult(
                    transport="serial", mode="binary" if binary else "hex",
                    success=False, bmp_size=state.bmp_size, transfer_time=None,
                    total_time=time.time() - start_time,
                    raw_bytes=state.raw_bytes_received, effective_rate=None,
                    raw_rate=None, overhead_pct=None,
                    error=error_msg
                )
            
            # Calculate metrics
            total_time = time.time() - start_time
            transfer_time = state.last_byte_time - state.first_byte_time if state.first_byte_time else None
            bmp = state.get_bmp()
            
            if not bmp or not transfer_time:
                return BenchmarkResult(
                    transport="serial", mode="binary" if binary else "hex",
                    success=False, bmp_size=None, transfer_time=None,
                    total_time=total_time, raw_bytes=state.raw_bytes_received,
                    effective_rate=None, raw_rate=None, overhead_pct=None,
                    error="Failed to decode BMP"
                )
            
            bmp_size = len(bmp)
            effective_rate = bmp_size / transfer_time
            raw_rate = state.raw_bytes_received / transfer_time
            overhead_pct = ((state.raw_bytes_received - bmp_size) / bmp_size) * 100
            
            return BenchmarkResult(
                transport="serial", mode="binary" if binary else "hex",
                success=True, bmp_size=bmp_size, transfer_time=transfer_time,
                total_time=total_time, raw_bytes=state.raw_bytes_received,
                effective_rate=effective_rate, raw_rate=raw_rate,
                overhead_pct=overhead_pct, error=None
            )
    
    except Exception as e:
        return BenchmarkResult(
            transport="serial", mode="binary" if binary else "hex",
            success=False, bmp_size=None, transfer_time=None,
            total_time=time.time() - start_time, raw_bytes=None,
            effective_rate=None, raw_rate=None, overhead_pct=None,
            error=str(e)
        )


async def run_benchmarks(args: argparse.Namespace) -> list[BenchmarkResult]:
    """Run all requested benchmarks."""
    results = []
    
    # Determine which transports and modes to test
    test_configs = []
    
    if args.transport in ("all", "serial") and args.serial_port:
        if args.mode in ("all", "hex"):
            test_configs.append(("serial", "C", False))
        if args.mode in ("all", "binary"):
            test_configs.append(("serial", "c", True))
    
    if args.transport in ("all", "ble"):
        if args.mode in ("all", "hex"):
            test_configs.append(("ble", "C", False))
        if args.mode in ("all", "binary"):
            test_configs.append(("ble", "c", True))
    
    # Run benchmarks
    for i, (transport, cmd, binary) in enumerate(test_configs, 1):
        print(f"\n{'='*60}")
        print(f"Benchmark {i}/{len(test_configs)}: {transport.upper()} / {'BINARY' if binary else 'HEX'}")
        print(f"{'='*60}")
        
        if args.delay > 0 and i > 1:
            print(f"Waiting {args.delay}s before next test...")
            await asyncio.sleep(args.delay)
        
        if transport == "serial":
            result = benchmark_serial(
                args.serial_port, args.baudrate, cmd, binary, args.max_seconds,
                show_progress=not args.no_progress
            )
        else:  # ble
            result = await benchmark_ble(
                args.device_name, cmd, binary, args.scan_timeout, args.max_seconds,
                show_progress=not args.no_progress
            )
        
        result.print_summary(i)
        results.append(result)
    
    return results


def print_comparison(results: list[BenchmarkResult]) -> None:
    """Print comparison table of all results."""
    successful = [r for r in results if r.success]
    
    if len(successful) < 2:
        return
    
    print("\n" + "=" * 60)
    print("COMPARISON TABLE")
    print("=" * 60)
    print(f"{'Transport':<10} {'Mode':<8} {'Size':<12} {'Time':<10} {'Rate':<12} {'Overhead':<10}")
    print("-" * 60)
    
    for r in results:
        if not r.success:
            print(f"{r.transport:<10} {r.mode:<8} {'FAILED':<12} {'-':<10} {'-':<12} {'-':<10}")
        else:
            print(f"{r.transport:<10} {r.mode:<8} {r.bmp_size:>10,}B "
                  f"{fmt_time(r.transfer_time):>9} {fmt_rate(r.effective_rate):>11} "
                  f"{r.overhead_pct:>8.1f}%")
    
    # Calculate speedups
    if len(successful) >= 2:
        print("\n" + "=" * 60)
        print("SPEEDUP ANALYSIS")
        print("=" * 60)
        
        # Binary vs hex for same transport
        transports = {r.transport for r in successful}
        for transport in transports:
            hex_result = next((r for r in successful if r.transport == transport and r.mode == "hex"), None)
            bin_result = next((r for r in successful if r.transport == transport and r.mode == "binary"), None)
            
            if hex_result and bin_result:
                speedup = bin_result.effective_rate / hex_result.effective_rate
                time_saved = hex_result.transfer_time - bin_result.transfer_time
                print(f"\n{transport.upper()}: Binary is {speedup:.2f}x faster than Hex")
                print(f"  Time saved: {fmt_time(time_saved)} ({time_saved/hex_result.transfer_time*100:.1f}% faster)")
                print(f"  Overhead reduction: {hex_result.overhead_pct:.1f}% → {bin_result.overhead_pct:.1f}%")


async def async_main() -> int:
    ap = argparse.ArgumentParser(
        description="Benchmark ATS-Mini screenshot capture performance"
    )
    ap.add_argument("--transport", choices=["serial", "ble", "all"], default="all",
                   help="Transport to benchmark (default: all)")
    ap.add_argument("--mode", choices=["hex", "binary", "all"], default="all",
                   help="Capture mode to benchmark (default: all)")
    ap.add_argument("--serial-port", help="Serial port device (e.g., /dev/cu.usbmodem1101)")
    ap.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate (default: 115200)")
    ap.add_argument("--device-name", default="ATS-Mini", help="BLE device name (default: ATS-Mini)")
    ap.add_argument("--scan-timeout", type=float, default=10.0, help="BLE scan timeout (default: 10s)")
    ap.add_argument("--max-seconds", type=float, default=60.0, 
                   help="Max transfer time per test - stops slow transfers (default: 60s, use higher for slow BLE)")
    ap.add_argument("--delay", type=float, default=2.0, help="Delay between tests (default: 2s)")
    ap.add_argument("--runs", type=int, default=1, help="Number of runs per configuration (default: 1)")
    ap.add_argument("--no-progress", action="store_true", help="Disable real-time progress display")
    args = ap.parse_args()
    
    # Validate
    if args.transport in ("serial", "all") and not args.serial_port:
        if not PYSERIAL_AVAILABLE:
            print("Serial transport not available (pyserial not installed)", file=sys.stderr)
            args.transport = "ble" if args.transport == "all" else None
        else:
            print("Error: --serial-port required for serial benchmarks", file=sys.stderr)
            return 1
    
    if args.transport in ("ble", "all") and not BLEAK_AVAILABLE:
        print("BLE transport not available (bleak not installed)", file=sys.stderr)
        if args.transport == "all":
            args.transport = "serial"
        else:
            return 1
    
    if args.transport is None:
        print("Error: No transports available", file=sys.stderr)
        return 1
    
    print("ATS-Mini Screenshot Capture Benchmark")
    print("=" * 60)
    print(f"Transport: {args.transport}")
    print(f"Mode:      {args.mode}")
    print(f"Runs:      {args.runs}")
    if args.serial_port:
        print(f"Serial:    {args.serial_port} @ {args.baudrate}")
    if args.transport in ("ble", "all"):
        print(f"BLE:       {args.device_name}")
    
    all_results = []
    
    for run in range(args.runs):
        if args.runs > 1:
            print(f"\n{'#'*60}")
            print(f"RUN {run + 1}/{args.runs}")
            print(f"{'#'*60}")
        
        results = await run_benchmarks(args)
        all_results.extend(results)
    
    # Print final comparison
    print_comparison(all_results)
    
    # Calculate averages if multiple runs
    if args.runs > 1:
        print("\n" + "=" * 60)
        print("AVERAGE RESULTS")
        print("=" * 60)
        
        configs = set((r.transport, r.mode) for r in all_results)
        for transport, mode in sorted(configs):
            runs = [r for r in all_results if r.transport == transport and r.mode == mode and r.success]
            if runs:
                avg_time = sum(r.transfer_time for r in runs) / len(runs)
                avg_rate = sum(r.effective_rate for r in runs) / len(runs)
                avg_overhead = sum(r.overhead_pct for r in runs) / len(runs)
                print(f"\n{transport.upper()} / {mode.upper()} ({len(runs)} successful runs)")
                print(f"  Avg transfer time: {fmt_time(avg_time)}")
                print(f"  Avg rate:          {fmt_rate(avg_rate)}")
                print(f"  Avg overhead:      {avg_overhead:.1f}%")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
