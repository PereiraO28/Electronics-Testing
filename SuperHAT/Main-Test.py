#!/usr/bin/env python3

import curses
import time

# GPIO
from gpiozero import DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice

# I2C / ADS1015
import board
import busio
from adafruit_ads1x15 import ADS1015, AnalogIn, ads1x15


# ============================================================
# CONFIGURATION
# ============================================================

# ---------------- GPIO ----------------

LEAK_GPIO = 26

DRV_IN1 = 9
DRV_IN2 = 10

PWM1_GPIO = 13
PWM2_GPIO = 12

MOSFET1_GPIO = 16
MOSFET2_GPIO = 11
MOSFET3_GPIO = 18
MOSFET4_GPIO = 19


# ---------------- ADS1015 ----------------

VOLTAGE_ADC_ADDRESS = 0x4A
LEFT_THRUSTER_ADC_ADDRESS = 0x48
RIGHT_THRUSTER_ADC_ADDRESS = 0x49


# ---------------- Scaling ----------------
#
# These values are taken directly from your existing ROV code.

SCALAR_48V = 19.8
SCALAR_12V = 5.273
SCALAR_3V3 = 2.0

SCALAR_CURRENT = 6.061


# ============================================================
# POWERBOARD MONITOR
# ============================================================

class PowerBoardMonitor:

    def __init__(self):

        # Initialize Raspberry Pi I2C
        self.i2c = busio.I2C(board.SCL, board.SDA)

        # ----------------------------------------------------
        # Voltage ADC - 0x4A
        # ----------------------------------------------------

        self.voltage_adc = ADS1015(
            self.i2c,
            address=VOLTAGE_ADC_ADDRESS
        )

        self.voltage_channels = [
            AnalogIn(self.voltage_adc, ads1x15.Pin.A0),
            AnalogIn(self.voltage_adc, ads1x15.Pin.A1),
            AnalogIn(self.voltage_adc, ads1x15.Pin.A2),
            AnalogIn(self.voltage_adc, ads1x15.Pin.A3),
        ]

        # ----------------------------------------------------
        # Left Thruster Current ADC - 0x48
        # ----------------------------------------------------

        self.left_adc = ADS1015(
            self.i2c,
            address=LEFT_THRUSTER_ADC_ADDRESS
        )

        self.left_channels = [
            AnalogIn(self.left_adc, ads1x15.Pin.A0),
            AnalogIn(self.left_adc, ads1x15.Pin.A1),
            AnalogIn(self.left_adc, ads1x15.Pin.A2),
            AnalogIn(self.left_adc, ads1x15.Pin.A3),
        ]

        # ----------------------------------------------------
        # Right Thruster Current ADC - 0x49
        # ----------------------------------------------------

        self.right_adc = ADS1015(
            self.i2c,
            address=RIGHT_THRUSTER_ADC_ADDRESS
        )

        self.right_channels = [
            AnalogIn(self.right_adc, ads1x15.Pin.A0),
            AnalogIn(self.right_adc, ads1x15.Pin.A1),
            AnalogIn(self.right_adc, ads1x15.Pin.A2),
            AnalogIn(self.right_adc, ads1x15.Pin.A3),
        ]

    # ========================================================
    # VOLTAGE READINGS
    # ========================================================

    def read_voltages(self):

        return {
            "48V": (
                self.voltage_channels[0].voltage
                * SCALAR_48V
            ),

            "12V_LEFT": (
                self.voltage_channels[1].voltage
                * SCALAR_12V
            ),

            "12V_RIGHT": (
                self.voltage_channels[2].voltage
                * SCALAR_12V
            ),

            "3V3": (
                self.voltage_channels[3].voltage
                * SCALAR_3V3
            ),
        }

    # ========================================================
    # CURRENT READINGS
    # ========================================================

    def read_thruster_currents(self):

        # Existing powerboard mapping:
        #
        # Thruster physical arrangement:
        #
        #       1   2
        #       5   6
        #       7   8
        #       3   4
        #
        #
        # ADS 0x48:
        #
        # A0 -> Thruster 1
        # A1 -> Thruster 5
        # A2 -> Thruster 7
        # A3 -> Thruster 3
        #
        #
        # ADS 0x49:
        #
        # A0 -> Thruster 2
        # A1 -> Thruster 6
        # A2 -> Thruster 8
        # A3 -> Thruster 4

        return {
            1: self.left_channels[0].voltage * SCALAR_CURRENT,
            2: self.right_channels[0].voltage * SCALAR_CURRENT,

            3: self.left_channels[3].voltage * SCALAR_CURRENT,
            4: self.right_channels[3].voltage * SCALAR_CURRENT,

            5: self.left_channels[1].voltage * SCALAR_CURRENT,
            6: self.right_channels[1].voltage * SCALAR_CURRENT,

            7: self.left_channels[2].voltage * SCALAR_CURRENT,
            8: self.right_channels[2].voltage * SCALAR_CURRENT,
        }


# ============================================================
# GPIO HARDWARE SETUP
# ============================================================

def setup_hardware():

    leak = DigitalInputDevice(
        LEAK_GPIO,
        pull_up=False
    )

    # DRV8871
    motor_in1 = DigitalOutputDevice(DRV_IN1)
    motor_in2 = DigitalOutputDevice(DRV_IN2)

    # PWM
    pwm1 = PWMOutputDevice(
        PWM1_GPIO,
        frequency=1000
    )

    pwm2 = PWMOutputDevice(
        PWM2_GPIO,
        frequency=1000
    )

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
# STATUS HELPERS
# ============================================================

def on_off(value):

    if value:
        return "ON"

    return "OFF"


def motor_direction(hw):

    in1 = hw["motor_in1"].value
    in2 = hw["motor_in2"].value

    if in1 and not in2:
        return "CLOCKWISE"

    elif not in1 and in2:
        return "COUNTER-CLOCKWISE"

    elif not in1 and not in2:
        return "STOPPED"

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
# SAFE TERMINAL WRITE
# ============================================================

def write_line(stdscr, y, text):

    try:
        height, width = stdscr.getmaxyx()

        if y >= height:
            return

        stdscr.addstr(
            y,
            0,
            text[:width - 1]
        )

    except curses.error:
        pass


# ============================================================
# DRAW SCREEN
# ============================================================

def draw_screen(
    stdscr,
    hw,
    powerboard,
    leak_enabled
):

    stdscr.erase()

    # ========================================================
    # SENSOR READINGS
    # ========================================================

    voltage_error = None
    current_error = None

    try:
        voltages = powerboard.read_voltages()

    except Exception as e:

        voltage_error = str(e)

        voltages = {
            "48V": 0,
            "12V_LEFT": 0,
            "12V_RIGHT": 0,
            "3V3": 0,
        }

    try:
        currents = powerboard.read_thruster_currents()

    except Exception as e:

        current_error = str(e)

        currents = {
            i: 0
            for i in range(1, 9)
        }

    # Leak sensor
    if leak_enabled:
        leak_status = bool(hw["leak"].value)

    else:
        leak_status = False

    # ========================================================
    # INTERFACE
    # ========================================================

    lines = [

        "",

        "===================== ROV ELECTRONICS TEST =====================",

        "",

        "             ------------        ------------",
        "-----        | MOSFET1 |        | MOSFET2 |        -----",
        "|   |        ------------        ------------        |   |",
        "| 1 |                                                | 2 |",
        "|   |        ------------        ------------        |   |",
        "-----        | MOSFET3 |        | MOSFET4 |        -----",
        "             ------------        ------------",

        "",

        "-------------------- SUPERHAT POWER BUSES --------------------",

        "",

        f"3.3V Bus : {voltages['3V3']:6.3f} V",
        f"5V Bus   : SuperHAT sensing not configured",
        f"12V Bus  : SuperHAT sensing not configured",

        "",

        f"Leak Status: {leak_status}",
        '(Toggle leak monitoring with "w")',

        "",

        "---------------------- POWERBOARD ----------------------------",

        "",

        "Power Rails:",

        f"48V       : {voltages['48V']:7.3f} V",
        f"12V Left  : {voltages['12V_LEFT']:7.3f} V",
        f"12V Right : {voltages['12V_RIGHT']:7.3f} V",
        f"3.3V      : {voltages['3V3']:7.3f} V",

        "",

        "Thruster Current:",

        f"Thruster 1 : {currents[1]:6.2f} A      "
        f"Thruster 2 : {currents[2]:6.2f} A",

        f"Thruster 5 : {currents[5]:6.2f} A      "
        f"Thruster 6 : {currents[6]:6.2f} A",

        f"Thruster 7 : {currents[7]:6.2f} A      "
        f"Thruster 8 : {currents[8]:6.2f} A",

        f"Thruster 3 : {currents[3]:6.2f} A      "
        f"Thruster 4 : {currents[4]:6.2f} A",

        "",

        "----------------------- OUTPUT TESTS -------------------------",

        "",

        f"Motor Driver Status: {motor_status(hw)}",

        '(Press "a" for clockwise)',
        '(Press "s" for counter-clockwise)',

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

        'Press "q" to quit or "r" to reset outputs',

    ]

    # ========================================================
    # ERRORS
    # ========================================================

    if voltage_error:

        lines += [
            "",
            "POWERBOARD VOLTAGE ERROR:",
            voltage_error,
        ]

    if current_error:

        lines += [
            "",
            "POWERBOARD CURRENT ERROR:",
            current_error,
        ]

    # ========================================================
    # WRITE SCREEN
    # ========================================================

    for y, line in enumerate(lines):
        write_line(stdscr, y, line)

    stdscr.refresh()


# ============================================================
# MAIN
# ============================================================

def main(stdscr):

    curses.curs_set(0)

    stdscr.nodelay(True)
    stdscr.timeout(50)

    # --------------------------------------------------------
    # Initialize GPIO
    # --------------------------------------------------------

    hw = setup_hardware()

    # --------------------------------------------------------
    # Initialize PowerBoard
    # --------------------------------------------------------

    powerboard = PowerBoardMonitor()

    leak_enabled = True

    reset_outputs(hw)

    try:

        while True:

            draw_screen(
                stdscr,
                hw,
                powerboard,
                leak_enabled
            )

            key = stdscr.getch()

            if key == -1:
                continue

            try:
                key = chr(key).lower()

            except ValueError:
                continue

            # =================================================
            # QUIT
            # =================================================

            if key == "q":
                break

            # =================================================
            # RESET
            # =================================================

            elif key == "r":

                reset_outputs(hw)

                leak_enabled = True

            # =================================================
            # LEAK SENSOR MONITOR
            # =================================================

            elif key == "w":

                leak_enabled = not leak_enabled

            # =================================================
            # MOTOR CLOCKWISE
            # =================================================

            elif key == "a":

                if (
                    hw["motor_in1"].value == 1
                    and
                    hw["motor_in2"].value == 0
                ):

                    # Already CW -> stop
                    hw["motor_in1"].off()
                    hw["motor_in2"].off()

                else:

                    hw["motor_in1"].on()
                    hw["motor_in2"].off()

            # =================================================
            # MOTOR COUNTER-CLOCKWISE
            # =================================================

            elif key == "s":

                if (
                    hw["motor_in1"].value == 0
                    and
                    hw["motor_in2"].value == 1
                ):

                    # Already CCW -> stop
                    hw["motor_in1"].off()
                    hw["motor_in2"].off()

                else:

                    hw["motor_in1"].off()
                    hw["motor_in2"].on()

            # =================================================
            # PWM 1
            # =================================================

            elif key == "d":

                if hw["pwm1"].value > 0:

                    hw["pwm1"].off()

                else:

                    hw["pwm1"].value = 1.0

            # =================================================
            # PWM 2
            # =================================================

            elif key == "f":

                if hw["pwm2"].value > 0:

                    hw["pwm2"].off()

                else:

                    hw["pwm2"].value = 1.0

            # =================================================
            # MOSFETS
            # =================================================

            elif key == "g":

                hw["mosfet1"].toggle()

            elif key == "h":

                hw["mosfet2"].toggle()

            elif key == "j":

                hw["mosfet3"].toggle()

            elif key == "k":

                hw["mosfet4"].toggle()

    # ========================================================
    # EMERGENCY CLEANUP
    # ========================================================

    finally:

        reset_outputs(hw)

        for device in hw.values():

            try:
                device.close()

            except Exception:
                pass


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    curses.wrapper(main)
