import time
import sys
from board import SCL, SDA
import busio
from adafruit_pca9685 import PCA9685
import keyboard

# Initialize the I2C bus
i2c_bus = busio.I2C(SCL, SDA)

# Directly interface with the PCA9685 hardware address (default: 0x40)
try:
    pca = PCA9685(i2c_bus, address=0x40)
except Exception as e:
    print(f"Error opening PCA9685: {e}")
    print("Ensure you prepend RPI_lgpio_chip=0 to your execution command.")
    sys.exit(1)

# Match your ROV team's specific frequency parameter (100Hz)
pca.frequency = 100

# Track states for pins 0 through 7 (False = Stopped, True = Spinning)
channel_states = {i: False for i in range(8)}

def set_raw_duty_cycle(channel, fractional_duty):
    """
    Converts your team's fractional duty cycle (e.g. 0.15) to 
    the 16-bit integer (0-65535) expected by the Adafruit driver.
    """
    # 16-bit resolution calculation
    val_16bit = int(fractional_duty * 65535)
    pca.channels[channel].duty_cycle = val_16bit

print("Initializing channels 0-7... Sending neutral (0.15 duty cycle).")
for ch in range(8):
    set_raw_duty_cycle(ch, 0.15)

print("Waiting 5 seconds for Blue Robotics ESCs to finish arming beeps...")
time.sleep(5)

print("\n--- SYSTEM ARMED AND READY ---")
print("Press keys 0 to 7 to toggle the corresponding ESC channel.")
print("Press 'q' to stop all motors and exit.")
print("-------------------------------\n")

def stop_all_motors():
    """Safety function to instantly cut power to all channels."""
    print("\nShutting down all motors safely...")
    for ch in range(8):
        set_raw_duty_cycle(ch, 0.15)
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
                
                # Toggle logic based on ROV team math direction
                if not channel_states[ch]:
                    # Forward direction decreases duty cycle from 0.15 down to 0.14
                    set_raw_duty_cycle(ch, 0.14)
                    channel_states[ch] = True
                    print(f"Channel {ch}: SPINNING FORWARD (0.14 Duty Cycle)")
                else:
                    # Neutral stop
                    set_raw_duty_cycle(ch, 0.15)
                    channel_states[ch] = False
                    print(f"Channel {ch}: STOPPED (0.15 Duty Cycle)")
                    
        # Small sleep interval to prevent CPU spiking
        time.sleep(0.05)

except KeyboardInterrupt:
    stop_all_motors()

finally:
    print("Test script finished.")
    sys.exit()
