#!/usr/bin/env python3
import serial
import time

port = '/dev/cu.usbmodem1101'
ser = serial.Serial(port, 115200, timeout=2)
ser.reset_input_buffer()

print('=== First delta call ===')
ser.write(b'd')
ser.flush()
time.sleep(0.5)
data1 = ser.read(512)
print(f'Bytes: {len(data1)}, Header: {data1[:2]}, Flags: 0x{data1[3]:02x}')
if data1[:2] == b'DR':
    is_delta = (data1[3] & 0x01) != 0
    payload_size = int.from_bytes(data1[12:16], 'little')
    print(f'Flag delta: {is_delta}, Payload: {payload_size}')

print()
print('=== Second delta call ===')
time.sleep(0.3)
ser.write(b'd')
ser.flush()
time.sleep(0.5)
data2 = ser.read(512)
print(f'Bytes: {len(data2)}, Header: {data2[:2]}, Flags: 0x{data2[3]:02x}')
if data2[:2] == b'DR':
    is_delta = (data2[3] & 0x01) != 0
    payload_size = int.from_bytes(data2[12:16], 'little')
    print(f'Flag delta: {is_delta}, Payload: {payload_size}')

ser.close()
