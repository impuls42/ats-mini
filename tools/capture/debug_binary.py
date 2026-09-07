#!/usr/bin/env python3
"""Debug script for binary mode header parsing."""

import serial
import time

def main():
    binbuf = bytearray()
    bmp_size = None
    
    ser = serial.Serial('/dev/cu.usbmodem1101', 115200, timeout=1)
    time.sleep(0.1)
    ser.reset_input_buffer()
    ser.write(b'c')
    ser.flush()
    
    start = time.time()
    last_data = time.time()
    
    while time.time() - start < 10:  # 10 second max
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            binbuf.extend(data)
            last_data = time.time()
            
            # Parse header once
            if bmp_size is None and len(binbuf) >= 6:
                if binbuf[0:2] == b'BM':
                    bmp_size = int.from_bytes(binbuf[2:6], 'little')
                    print(f'Parsed bmp_size: {bmp_size}')
            
            # Check complete
            if bmp_size and len(binbuf) >= bmp_size:
                elapsed = time.time() - start
                print(f'Complete! {len(binbuf)} bytes in {elapsed:.2f}s = {len(binbuf)/elapsed/1024:.1f} KiB/s')
                break
        else:
            if time.time() - last_data > 2:
                print(f'Stalled at {len(binbuf)} bytes')
                break
            time.sleep(0.01)
    
    print(f'Final: {len(binbuf)} bytes, bmp_size={bmp_size}')
    ser.close()


if __name__ == '__main__':
    main()
