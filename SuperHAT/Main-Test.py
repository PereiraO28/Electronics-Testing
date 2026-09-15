#!/usr/bin/env python3

import curses
import time
from smbus2 import SMBus
from gpiozero import DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice

# ============================================================
# CONFIGURATION
# ============================================================

I2C_BUS = 1
INA3221_ADDRESS = 0x40

# INA3221 channels
# CH1 = 5 V
# CH2 = 12 V
# CH3 = 3.3 V

SHUNT_OHMS = 0.1  # Change to match your PCB

# GPIO assignments (BCM numbering)
LEAK_GPIO = 26

DRV_IN1 = 9
DRV_IN2 = 10

PWM1_GPIO = 13
PWM2_GPIO = 12

MOSFET1_GPIO = 16
MOSFET2_GPIO = 11
MOSFET3_GPIO = 18
MOSFET4_GPIO = 19


# ============================================================
# INA3221
# ============================================================

class INA3221:
    """
    Minimal INA3221 driver for reading bus voltage.
    """

    # Bus voltage registers
    BUS_REG = {
        1: 0x02,
        2: 0x04,
        3: 0x06,
    }

    def __init__(self, bus_num=1, address=0x40):
        self.bus = SMBus(bus_num)
        self.address = address

    def read_word(self, register):
        raw = self.bus.read_word_data(self.address, register)

        # SMBus returns bytes swapped for this device
        raw = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)

        return raw

    def read_bus_voltage(self, channel):
        raw = self.read_word(self.BUS_REG[channel])

        # INA3221 bus-voltage register:
        # bits 15:3 contain the measurement
        value = (raw >> 3) & 0x1FFF

        # 8 mV per bit
        return value * 0.008

    def close(self):
        self.bus.close()


# ============================================================
# HARDWARE SETUP
# ============================================================

def setup_hardware():

    # Leak sensor
    # Change pull_up depending on your SOS sensor circuitry.
    leak = DigitalInputDevice(
        LEAK_GPIO,
        pull_up=False
    )

    # DRV8871
    motor_in1 = DigitalOutputDevice(DRV_IN1)
    motor_in2 = DigitalOutputDevice(DRV_IN2)

    # PWM outputs
    pwm1 = PWMOutputDevice(PWM1_GPIO, frequency=1000)
    pwm2 = PWMOutputDevice(PWM2_GPIO, frequency=1000)

    # MOSFETs
    mosfet1 = DigitalOutputDevice(MOSFET1_GPIO)
    mosfet2 = DigitalOutputDevice(MOSFET2_GPIO)
    mosfet3 = DigitalOutputDevice(MOSFET3_GPIO)
    mosfet4 = DigitalOutputDevice(MOSFET4_GPIO)

    return {
        "leak": leak,

        "motor_in1": motor_in1,
        "motor_in2": motor_in2,

        "pwm1": pwm1,
        "pwm2": pwm2,

        "mosfet1": mosfet1,
        "mosfet2": mosfet2,
        "mosfet3": mosfet3,
        "mosfet4": mosfet4,
    }


# ============================================================
# OUTPUT HELPERS
# ============================================================

def on_off(value):
    return "ON" if value else "OFF"


def motor_direction(hw):

    in1 = hw["motor_in1"].value
    in2 = hw["motor_in2"].value

    if in1 and not in2:
        return "CLOCKWISE"

    elif not in1 and in2:
        return "COUNTER-CLOCKWISE"

    elif not in1 and not in2:
        return "STOPPED"

    else:
        return "BRAKE"


def motor_status(hw):

    if hw["motor_in1"].value or hw["motor_in2"].value:
        return "ON"

    return "OFF"


# ============================================================
# RESET
# ============================================================

def reset_outputs(hw):

    hw["motor_in1"].off()
    hw["motor_in2"].off()

    hw["pwm1"].off()
    hw["pwm2"].off()

    hw["mosfet1"].off()
    hw["mosfet2"].off()
    hw["mosfet3"].off()
    hw["mosfet4"].off()


# ============================================================
# TERMINAL DISPLAY
# ============================================================

def draw_screen(stdscr, hw, ina, leak_enabled):

    stdscr.erase()

    # --------------------------------------------------------
    # Read voltages
    # --------------------------------------------------------

    try:
        voltage_5v = ina.read_bus_voltage(1)
        voltage_12v = ina.read_bus_voltage(2)
        voltage_3v3 = ina.read_bus_voltage(3)

        voltage_string = (
            f"Voltage(3.3V: {voltage_3v3:.3f} V, "
            f"5V: {voltage_5v:.3f} V, "
            f"12V: {voltage_12v:.3f} V)"
        )

    except Exception as e:
        voltage_string = f"Voltage: INA3221 ERROR ({e})"

    # --------------------------------------------------------
    # Leak sensor
    # --------------------------------------------------------

    if leak_enabled:
        leak_status = bool(hw["leak"].value)
    else:
        leak_status = False

    # --------------------------------------------------------
    # Diagram
    # --------------------------------------------------------

    lines = [
        "",
        "             ------------        ------------",
        "-----        | MOSFET1 |        | MOSFET2 |        -----",
        "|   |        ------------        ------------        |   |",
        "| 1 |                                                | 2 |",
        "|   |        ------------        ------------        |   |",
        "-----        | MOSFET3 |        | MOSFET4 |        -----",
        "             ------------        ------------",
        "",
        voltage_string,
        "",
        f"Leak Status: {leak_status}",
        '(Toggle on/off with "w")',
        "",
        f"Motor Driver Status: {motor_status(hw)}",
        '(Click "a" for clockwise and "s" for counter-clockwise)',
        f"Motor Driver Direction: {motor_direction(hw)}",
        "",
        '(Toggle PWM1 with "d")',
        f"PWM1 Status: {on_off(hw['pwm1'].value > 0)}",
        "",
        '(Toggle PWM2 with "f")',
        f"PWM2 Status: {on_off(hw['pwm2'].value > 0)}",
        "",
        '(Toggle MOSFET1 with "g")',
        f"MOSFET1 Status: {on_off(hw['mosfet1'].value)}",
        "",
        '(Toggle MOSFET2 with "h")',
        f"MOSFET2 Status: {on_off(hw['mosfet2'].value)}",
        "",
        '(Toggle MOSFET3 with "j")',
        f"MOSFET3 Status: {on_off(hw['mosfet3'].value)}",
        "",
        '(Toggle MOSFET4 with "k")',
        f"MOSFET4 Status: {on_off(hw['mosfet4'].value)}",
        "",
        'Click "q" to quit or "r" to reset values',
    ]

    for y, line in enumerate(lines):
        try:
            stdscr.addstr(y, 0, line)
        except curses.error:
            pass

    stdscr.refresh()


# ============================================================
# MAIN
# ============================================================

def main(stdscr):

    curses.curs_set(0)

    # Don't block waiting for keyboard input
    stdscr.nodelay(True)

    # Refresh keyboard roughly every 50 ms
    stdscr.timeout(50)

    hw = setup_hardware()
    ina = INA3221(I2C_BUS, INA3221_ADDRESS)

    leak_enabled = True

    reset_outputs(hw)

    try:

        while True:

            draw_screen(
                stdscr,
                hw,
                ina,
                leak_enabled
            )

            key = stdscr.getch()

            if key == -1:
                continue

            try:
                key = chr(key).lower()
            except ValueError:
                continue

            # --------------------------------------------
            # Quit
            # --------------------------------------------

            if key == "q":
                break

            # --------------------------------------------
            # Reset
            # --------------------------------------------

            elif key == "r":
                reset_outputs(hw)
                leak_enabled = True

            # --------------------------------------------
            # Leak sensor
            # --------------------------------------------

            elif key == "w":
                leak_enabled = not leak_enabled

            # --------------------------------------------
            # Motor
            # --------------------------------------------

            elif key == "a":

                # Toggle clockwise
                if (
                    hw["motor_in1"].value == 1
                    and hw["motor_in2"].value == 0
                ):
                    hw["motor_in1"].off()
                    hw["motor_in2"].off()

                else:
                    hw["motor_in1"].on()
                    hw["motor_in2"].off()

            elif key == "s":

                # Toggle counter-clockwise
                if (
                    hw["motor_in1"].value == 0
                    and hw["motor_in2"].value == 1
                ):
                    hw["motor_in1"].off()
                    hw["motor_in2"].off()

                else:
                    hw["motor_in1"].off()
                    hw["motor_in2"].on()

            # --------------------------------------------
            # PWM
            # --------------------------------------------

            elif key == "d":

                if hw["pwm1"].value > 0:
                    hw["pwm1"].off()
                else:
                    # 100% duty cycle for simple output test
                    hw["pwm1"].value = 1.0

            elif key == "f":

                if hw["pwm2"].value > 0:
                    hw["pwm2"].off()
                else:
                    hw["pwm2"].value = 1.0

            # --------------------------------------------
            # MOSFETs
            # --------------------------------------------

            elif key == "g":
                hw["mosfet1"].toggle()

            elif key == "h":
                hw["mosfet2"].toggle()

            elif key == "j":
                hw["mosfet3"].toggle()

            elif key == "k":
                hw["mosfet4"].toggle()

    finally:

        # VERY IMPORTANT:
        # turn everything off if program exits/crashes

        reset_outputs(hw)

        ina.close()

        for device in hw.values():
            device.close()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    curses.wrapper(main)
