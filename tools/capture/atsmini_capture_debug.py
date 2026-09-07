#!/usr/bin/env python3
"""
Debug tool for ATS-Mini screenshot capture issues.
Shows detailed byte-by-byte progress and helps diagnose stalls.
"""

import argparse
import sys
import time

try:
    import serial
    PYSERIAL_AVAILABLE = True
except ImportError:
    PYSERIAL_AVAILABLE = False
    print("Error: pyserial not available", file=sys.stderr)
    sys.exit(1)


def debug_serial_capture(port: str, baudrate: int, cmd: str, timeout: float = 30.0):
    """Debug serial capture with detailed output."""
    print(f"Opening {port} @ {baudrate}...")
    
    with serial.Serial(port, baudrate, timeout=1) as ser:
        # Clear buffer
        ser.reset_input_buffer()
        time.sleep(0.1)
        
        # Send command
        print(f"Sending command: '{cmd}'")
        ser.write(cmd.encode("ascii"))
        ser.flush()
        
        # Read with detailed logging
        start_time = time.time()
        last_data_time = time.time()
        total_bytes = 0
        chunk_count = 0
        last_report = 0.0
        all_data = bytearray()
        expected_size = None
        
        print("\nReading data...")
        print("-" * 60)
        
        try:
            while time.time() - start_time < timeout:
                now = time.time()
                
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting)
                    chunk_len = len(data)
                    total_bytes += chunk_len
                    chunk_count += 1
                    last_data_time = now
                    all_data.extend(data)
                    
                    # Try to parse BMP header once we have enough data
                    if expected_size is None and len(all_data) >= 6:
                        if all_data[0:2] == b'BM':
                            expected_size = int.from_bytes(all_data[2:6], 'little')
                            print(f"\n📊 BMP header detected! Expected size: {expected_size:,} bytes\n")
                    
                    # Show chunk details
                    if chunk_len > 0:
                        elapsed = now - start_time
                        rate = total_bytes / elapsed if elapsed > 0 else 0
                        progress = ""
                        if expected_size:
                            pct = (total_bytes / expected_size) * 100
                            progress = f" ({pct:5.1f}%)"
                        
                        print(f"[{elapsed:6.2f}s] Chunk #{chunk_count:4d}: {chunk_len:5d} bytes "
                              f"| Total: {total_bytes:7d}{progress} | Rate: {rate:8.1f} B/s")
                        
                        # Show first few bytes of first chunks
                        if chunk_count <= 3:
                            preview = ' '.join(f'{b:02x}' for b in data[:32])
                            print(f"           Preview: {preview}...")
                
                # Check for stall
                stall_time = now - last_data_time
                if stall_time > 2.0 and now - last_report > 1.0:
                    # Check if we actually got everything before warning
                    if expected_size and total_bytes >= expected_size:
                        print(f"\n✅ Transfer complete! Received {total_bytes:,} bytes")
                        break
                    
                    print(f"\n⚠️  WARNING: No data for {stall_time:.1f}s (stalled?)")
                    last_report = now
                    
                    if stall_time > 5.0:
                        if expected_size:
                            print(f"\n❌ Transfer stalled: {total_bytes:,}/{expected_size:,} bytes "
                                  f"({total_bytes/expected_size*100:.1f}%)")
                        else:
                            print(f"\n❌ Transfer stalled after {total_bytes:,} bytes")
                        break
                
                time.sleep(0.01)
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
        
        # Final summary
        elapsed = time.time() - start_time
        rate = total_bytes / elapsed if elapsed > 0 else 0
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total bytes:   {total_bytes:,}")
        print(f"Chunks:        {chunk_count}")
        print(f"Time:          {elapsed:.2f}s")
        print(f"Average rate:  {rate:.1f} B/s ({rate/1024:.2f} KiB/s)")
        
        if total_bytes > 0:
            print(f"Avg chunk:     {total_bytes/chunk_count:.1f} bytes")
        
        # Check completeness
        if expected_size:
            if total_bytes >= expected_size:
                print(f"\n✅ SUCCESS: Complete transfer ({total_bytes:,}/{expected_size:,} bytes)")
            else:
                pct = (total_bytes / expected_size) * 100
                print(f"\n⚠️  INCOMPLETE: {total_bytes:,}/{expected_size:,} bytes ({pct:.1f}%)")
        elif total_bytes >= 66:
            print("\n⚠️  Received data but couldn't parse BMP header")
        elif total_bytes >= 2:
            print("\n❌ Incomplete transfer - didn't get full header")
        else:
            print("\n❌ No data received")


def main():
    ap = argparse.ArgumentParser(description="Debug ATS-Mini screenshot capture")
    ap.add_argument("--port", required=True, help="Serial port (e.g., /dev/cu.usbmodem1101)")
    ap.add_argument("--baudrate", type=int, default=115200, help="Baudrate (default: 115200)")
    ap.add_argument("--cmd", default="c", help="Command to send (default: c for binary)")
    ap.add_argument("--timeout", type=float, default=30.0, help="Max time to wait (default: 30s)")
    args = ap.parse_args()
    
    if not PYSERIAL_AVAILABLE:
        print("Error: pyserial not installed. Run: pip install pyserial", file=sys.stderr)
        return 1
    
    try:
        debug_serial_capture(args.port, args.baudrate, args.cmd, args.timeout)
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
