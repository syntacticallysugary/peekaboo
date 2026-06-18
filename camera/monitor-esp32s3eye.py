#!/usr/bin/env python3
"""Monitor script for ESP32-S3-EYE with auto-detection of serial port."""

import serial
import serial.tools.list_ports
import sys
import time

def find_esp32_port():
    """Find the most recent ESP32 serial port."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if 'ttyACM' in port.device:
            return port.device
    return None

def main():
    """Main function to monitor serial output."""
    # Find the port
    serial_port = find_esp32_port()
    
    if not serial_port:
        print("ERROR: No ESP32 device found on /dev/ttyACM*")
        print("Please connect the ESP32-S3-EYE and try again.")
        sys.exit(1)
    
    print("=============================================")
    print("ESP32-S3-EYE Serial Monitor")
    print("=============================================")
    print(f"Detected port: {serial_port}")
    print("=============================================")
    print("Press Ctrl+C to exit")
    print("=============================================")
    
    try:
        # Open serial port
        ser = serial.Serial(serial_port, 115200, timeout=1)
        print(f"Connected to {serial_port} at 115200 baud")
        
        # Read and print serial output
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore')
                print(line, end='')
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        if 'ser' in locals():
            ser.close()

if __name__ == "__main__":
    main()
