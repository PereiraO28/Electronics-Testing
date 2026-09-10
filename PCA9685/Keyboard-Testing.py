#!/usr/bin/env python3
"""
Interactive PCA9685 ESC test tool for Rovotics ESC controller board.
Minimal dependencies: smbus2 + Python standard library (curses).

Controls:
  a-h   : toggle ESC on channel 0-7 on/off
  +/=   : increase throttle (pulse width) for any channels currently ON
  -/_   : decrease throttle (pulse width) for any channels currently ON
  n     : reset throttle to neutral value (does not turn channels off)
  q     : quit (sets all channels to neutral first)

SAFETY: Remove propellers/thrusters or secure the ROV before running.
"""

import curses
import time
from smbus2 import SMBus

# ---- PCA9685 register map ----
MODE1     = 0x00
MODE2     = 0x01
PRESCALE  = 0xFE
LED0_ON_L = 0x06

RESTART = 0x80
SLEEP   = 0x10
AUTOINC = 0x20
ALLCALL = 0x01

# ---- Configuration ----
I2C_BUS = 1
I2C_ADDRESS = 0x40
PWM_FREQUENCY = 50

NEUTRAL_US = 1500
MIN_US = 1100
MAX_US = 1900
STEP_US = 20          # throttle change per +/- press
ARM_DELAY = 3.0

NUM_CHANNELS = 8
CHANNEL_KEYS = "abcdefgh"   # key 'a' -> channel 0, ... 'h' -> channel 7


class PCA9685:
    def __init__(self, bus_num, address):
        self.bus = SMBus(bus_num)
        self.address = address
        self._reset()

    def _write(self, reg, value):
        self.bus.write_byte_data(self.address, reg, value)

    def _read(self, reg):
        return self.bus.read_byte_data(self.address, reg)

    def _reset(self):
        self._write(MODE1, ALLCALL)
        self._write(MODE2, 0x04)
        time.sleep(0.005)

    def set_pwm_freq(self, freq_hz):
        prescale_val = round(25_000_000.0 / (4096 * freq_hz)) - 1
        old_mode = self._read(MODE1)
        self._write(MODE1, (old_mode & 0x7F) | SLEEP)
        self._write(PRESCALE, prescale_val)
        self._write(MODE1, old_mode)
        time.sleep(0.005)
        self._write(MODE1, old_mode | RESTART | AUTOINC)

    def set_pwm(self, channel, on, off):
        base = LED0_ON_L + 4 * channel
        self._write(base, on & 0xFF)
        self._write(base + 1, (on >> 8) & 0xFF)
        self._write(base + 2, off & 0xFF)
        self._write(base + 3, (off >> 8) & 0xFF)

    def set_pulse_us(self, channel, pulse_us, freq_hz=PWM_FREQUENCY):
        period_us = 1_000_000 / freq_hz
        off_tick = int((pulse_us / period_us) * 4096)
        self.set_pwm(channel, 0, off_tick)

    def close(self):
        self.bus.close()


def draw_ui(stdscr, throttle_us, channel_on):
    stdscr.erase()
    stdscr.addstr(0, 0, "PCA9685 ESC Interactive Test  (Rovotics)")
    stdscr.addstr(1, 0, "-" * 44)
    stdscr.addstr(2, 0, f"Throttle (applies to ON channels): {throttle_us} us")
    stdscr.addstr(3, 0, f"Range: {MIN_US}-{MAX_US} us, neutral {NEUTRAL_US} us, step {STEP_US} us")
    stdscr.addstr(5, 0, "Channel states:")
    for i in range(NUM_CHANNELS):
        state = "ON " if channel_on[i] else "off"
        stdscr.addstr(6 + i, 2, f"[{CHANNEL_KEYS[i]}] ch{i}: {state}")
    stdscr.addstr(6 + NUM_CHANNELS + 1, 0,
                  "a-h: toggle channel   +/-: throttle   n: reset to neutral   q: quit")
    stdscr.refresh()


def main(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(50)  # ms poll interval

    pca = PCA9685(I2C_BUS, I2C_ADDRESS)
    pca.set_pwm_freq(PWM_FREQUENCY)

    channel_on = [False] * NUM_CHANNELS
    throttle_us = NEUTRAL_US

    # Arm all channels at neutral before allowing control
    stdscr.addstr(0, 0, f"Arming all channels at neutral ({NEUTRAL_US} us) for {ARM_DELAY}s...")
    stdscr.refresh()
    for ch in range(NUM_CHANNELS):
        pca.set_pulse_us(ch, NEUTRAL_US)
    time.sleep(ARM_DELAY)

    try:
        while True:
            draw_ui(stdscr, throttle_us, channel_on)
            key = stdscr.getch()

            if key == -1:
                continue

            ch = chr(key).lower() if 0 <= key < 256 else ""

            if ch == "q":
                break

            elif ch in CHANNEL_KEYS:
                idx = CHANNEL_KEYS.index(ch)
                channel_on[idx] = not channel_on[idx]
                pulse = throttle_us if channel_on[idx] else NEUTRAL_US
                pca.set_pulse_us(idx, pulse)

            elif ch in ("+", "="):
                throttle_us = min(MAX_US, throttle_us + STEP_US)
                for i in range(NUM_CHANNELS):
                    if channel_on[i]:
                        pca.set_pulse_us(i, throttle_us)

            elif ch in ("-", "_"):
                throttle_us = max(MIN_US, throttle_us - STEP_US)
                for i in range(NUM_CHANNELS):
                    if channel_on[i]:
                        pca.set_pulse_us(i, throttle_us)

            elif ch == "n":
                throttle_us = NEUTRAL_US
                for i in range(NUM_CHANNELS):
                    if channel_on[i]:
                        pca.set_pulse_us(i, throttle_us)

    finally:
        for i in range(NUM_CHANNELS):
            pca.set_pulse_us(i, NEUTRAL_US)
        time.sleep(0.3)
        pca.close()


if __name__ == "__main__":
    curses.wrapper(main)
