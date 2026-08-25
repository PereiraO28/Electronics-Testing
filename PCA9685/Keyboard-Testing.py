import time
import sys
from board import SCL, SDA
import busio
from adafruit_servokit import ServoKit
import keyboard

# Initialize I2C and ServoKit
i2c_bus = busio.I2C(SCL, SDA)
kit = ServoKit(channels=16, i2c=i2c_bus)

# Track the running state of channels 0 through 7 (False = Stopped, True = Spinning)
channel_states = {i: False for i in range(8)}

# Configure pulse widths and arm channels 0-7
print("Initializing channels 0-7... Sending neutral (1500 µs).")
for ch in range(8):
    kit.continuous_servo[ch].set_pulse_width_range(1100, 1900)
    kit.continuous_servo[ch].throttle = 0.0

print("Waiting 5 seconds for all ESCs to complete arming beeps...")
time.sleep(5)

print("\n--- SYSTEM ARMED AND READY ---")
print("Press keys 0 to 7 to toggle the corresponding ESC.")
print("Press 'q' to stop all motors and exit.")
print("-------------------------------\n")

def stop_all_motors():
    """Safety function to instantly cut power to all channels."""
    print("\nShutting down all motors safely...")
    for ch in range(8):
        kit.continuous_servo[ch].throttle = 0.0
        channel_states[ch] = False

try:
    while True:
        # Read keyboard events instantly
        event = keyboard.read_event()
        
        # Only trigger action on the initial key downpress
        if event.event_type == keyboard.KEY_DOWN:
            key = event.name
            
            # Exit condition
            if key == 'q':
                stop_all_motors()
                break
                
            # Check if the key pressed is between 0 and 7
            if key in ['0', '1', '2', '3', '4', '5', '6', '7']:
                ch = int(key)
                
                # Toggle logic
                if not channel_states[ch]:
                    # If stopped, spin forward at 20% speed
                    kit.continuous_servo[ch].throttle = 0.2
                    channel_states[ch] = True
                    print(True, f"Channel {ch}: SPINNING FORWARD (0.2 throttle)")
                else:
                    # If running, stop the motor
                    kit.continuous_servo[ch].throttle = 0.0
                    channel_states[ch] = False
                    print(False, f"Channel {ch}: STOPPED")
                    
        # Small sleep to prevent CPU spiking
        time.sleep(0.05)

except KeyboardInterrupt:
    stop_all_motors()

finally:
    print("Test script finished.")
    sys.exit()

