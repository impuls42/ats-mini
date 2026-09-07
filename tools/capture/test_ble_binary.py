#!/usr/bin/env python3
"""Minimal BLE binary transfer test."""

import asyncio
import time
from bleak import BleakClient, BleakScanner

UART_TX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e'
UART_RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'

async def test():
    print('Scanning...')
    dev = await BleakScanner.find_device_by_name('ATS-Mini', timeout=10)
    if not dev:
        print('Device not found')
        return
    
    print(f'Connecting to {dev.address}...')
    async with BleakClient(dev, timeout=30) as client:
        print(f'Connected, MTU={client.mtu_size}')
        
        buf = bytearray()
        done = asyncio.Event()
        last_recv = [time.time()]
        
        def callback(_, data):
            buf.extend(data)
            last_recv[0] = time.time()
            if len(buf) >= 6 and len(buf) >= int.from_bytes(buf[2:6], 'little'):
                done.set()
        
        await client.start_notify(UART_TX, callback)
        
        print('Sending c command...')
        await client.write_gatt_char(UART_RX, b'c')
        
        start = time.time()
        while not done.is_set() and time.time() - start < 60:
            await asyncio.sleep(0.1)
            elapsed = time.time() - start
            pct = len(buf) / 108866 * 100 if len(buf) > 6 else 0
            print(f'\r  Progress: {pct:5.1f}% | {len(buf):,} bytes | {len(buf)/elapsed/1024:.1f} KiB/s', end='')
            
            # Check for stall
            if time.time() - last_recv[0] > 5:
                print(f'\n  STALLED at {len(buf)} bytes after no data for 5s')
                break
        
        print()
        elapsed = time.time() - start
        if done.is_set():
            print(f'SUCCESS: Received {len(buf)} bytes in {elapsed:.2f}s = {len(buf)/elapsed/1024:.1f} KiB/s')
        else:
            print(f'FAILED: Received only {len(buf)} bytes in {elapsed:.2f}s')


if __name__ == '__main__':
    asyncio.run(test())
