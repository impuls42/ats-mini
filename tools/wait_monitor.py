#!/usr/bin/env python3
import time
import os
import sys
import glob
import serial

def get_serial_port():
    # Look for the port ESP32-S3 usually shows up as on macOS
    # Prioritize cu.usbmodem for macOS as it doesn't block on DCD
    ports = glob.glob('/dev/cu.usbmodem*')
    if ports:
        return ports[0]
    return None

def main():
    print("--- Wait-Reconnect Monitor ---")
    
    first_connection = True
    
    while True:
        print("Waiting for device serial port to become available...")
        
        timeout = 30 # seconds
        start_time = time.time()
        port = None
        
        while True:
            port = get_serial_port()
            if port:
                print(f"Device detected at: {port}")
                break
            
            if time.time() - start_time > timeout:
                print("Timed out waiting for device.")
                sys.exit(1)
                
            time.sleep(0.2)
        
        # Brief settle time to let the OS register the device fully
        time.sleep(0.5)
        
        print(f"Opening serial port {port}...")
        
        try:
            # Open serial port
            # DTR=True is required for the ESP32-S3 'if(Serial)' check to pass
            ser = serial.Serial(port, 115200, timeout=1)
            
            if first_connection:
                print("Connected. Resetting device to capture boot logs...")
                # Reset sequence (DTR=False/RTS=True -> Reset)
                ser.dtr = False
                ser.rts = True
                time.sleep(0.1)
                ser.rts = False
                ser.dtr = True # Assert DTR to enable Serial print
                first_connection = False
            else:
                print("Connected. Resuming monitoring...")
            
            print(f"Monitoring {port} (Ctrl+C to exit)...")
            
            last_data_time = time.time()
            timeout = 15.0

            while True:
                if time.time() - last_data_time > timeout:
                    print(f"\nNo output for {timeout} seconds. Exiting.")
                    return
                
                try:
                    if ser.in_waiting > 0:
                        line = ser.readline()
                        last_data_time = time.time()
                        try:
                            decoded = line.decode('utf-8', errors='replace').rstrip()
                            print(decoded)
                            if "ETS: Setup complete" in decoded:
                                print("\nSetup complete detected. Exiting successfully.")
                                return # Exit function/script
                        except Exception as e:
                            print(f"<Decode Error: {e}>")
                    else:
                        time.sleep(0.01)
                except OSError as e:
                    # Handle device disconnection during monitoring
                    print(f"\nDevice disconnected: {e}")
                    ser.close()
                    print("Attempting to reconnect...")
                    break  # Break to outer while loop to reconnect
                    
        except KeyboardInterrupt:
            print("\nExiting...")
            sys.exit(0)
        except Exception as e:
            print(f"Error opening/reading serial port: {e}")
            # Assuming the user might not have pyserial installed in the default python
            print("Ensure pyserial is installed: pip install pyserial")
            sys.exit(1)

if __name__ == "__main__":
    main()
