import curses
import time

# GPIO
from gpiozero import DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice

# I2C / ADS1015
import board
import busio
from adafruit_ads1x15 import ADS1015, AnalogIn, ads1x15

#PMBus on MPQ Murata power converters
from smbus2 import SMBus

# GPIO

LEAK_GPIO = 26

DRV_IN1 = 9
DRV_IN2 = 10

PWM1_GPIO = 13
PWM2_GPIO = 12

MOSFET1_GPIO = 16
MOSFET2_GPIO = 11
MOSFET3_GPIO = 18
MOSFET4_GPIO = 19


# ADS

VOLTAGE_ADC_ADDRESS = 0x4A
LEFT_THRUSTER_ADC_ADDRESS = 0x48
RIGHT_THRUSTER_ADC_ADDRESS = 0x49


# Scalars for voltage sensing

SCALAR_48V = 19.8
SCALAR_12V = 5.273
SCALAR_3V3 = 2.0

SCALAR_CURRENT = 6.061

# Powerboard monitoring

class PowerBoardMonitor:
    RETRY_INTERVAL = 3.0  # Seconds between reconnect attempts

    def __init__(self):
        self.i2c = None
        self.channels = {addr: None for addr in (
            VOLTAGE_ADC_ADDRESS, LEFT_THRUSTER_ADC_ADDRESS,
            RIGHT_THRUSTER_ADC_ADDRESS
        )}
        self.last_attempt = {addr: -float("inf") for addr in self.channels}
        self.errors = {}
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
        except (OSError, RuntimeError, ValueError) as exc:
            self.errors["bus"] = str(exc)

    def _connect(self, address):
        if self.channels[address] is not None:
            return
        now = time.monotonic()
        if now - self.last_attempt[address] < self.RETRY_INTERVAL:
            return
        self.last_attempt[address] = now
        if self.i2c is None:
            try:
                self.i2c = busio.I2C(board.SCL, board.SDA)
                self.errors.pop("bus", None)
            except (OSError, RuntimeError, ValueError) as exc:
                self.errors["bus"] = str(exc)
                return
        try:
            adc = ADS1015(self.i2c, address=address)
            channels = [AnalogIn(adc, pin) for pin in (
                ads1x15.Pin.A0, ads1x15.Pin.A1,
                ads1x15.Pin.A2, ads1x15.Pin.A3
            )]
            # Verify the device responds, not just that the object was created.
            _ = channels[0].voltage
            self.channels[address] = channels
            self.errors.pop(address, None)
        except (OSError, RuntimeError, ValueError) as exc:
            self.channels[address] = None
            self.errors[address] = str(exc)

    def _read(self, address, channel, scalar):
        self._connect(address)
        channels = self.channels[address]
        if channels is None:
            return None
        try:
            result = channels[channel].voltage * scalar
            self.errors.pop(address, None)
            return result
        except (OSError, RuntimeError, ValueError) as exc:
            self.channels[address] = None
            self.errors[address] = str(exc)
            self.last_attempt[address] = time.monotonic()
            return None

    def read_voltages(self):
        a = VOLTAGE_ADC_ADDRESS
        return {
            "48V": self._read(a, 0, SCALAR_48V),
            "12V_LEFT": self._read(a, 1, SCALAR_12V),
            "12V_RIGHT": self._read(a, 2, SCALAR_12V),
            "3V3": self._read(a, 3, SCALAR_3V3),
        }

    def read_thruster_currents(self):
        # 0x48: A0=1, A1=5, A2=7, A3=3
        # 0x49: A0=2, A1=6, A2=8, A3=4
        left = LEFT_THRUSTER_ADC_ADDRESS
        right = RIGHT_THRUSTER_ADC_ADDRESS
        return {
            1: self._read(left, 0, SCALAR_CURRENT),
            2: self._read(right, 0, SCALAR_CURRENT),
            3: self._read(left, 3, SCALAR_CURRENT),
            4: self._read(right, 3, SCALAR_CURRENT),
            5: self._read(left, 1, SCALAR_CURRENT),
            6: self._read(right, 1, SCALAR_CURRENT),
            7: self._read(left, 2, SCALAR_CURRENT),
            8: self._read(right, 2, SCALAR_CURRENT),
        }

    def close(self):
        if self.i2c is not None:
            self.i2c.deinit()


def format_reading(value, decimals=3, width=7):
    return f"{value:{width}.{decimals}f}" if value is not None else f"{'N/A':>{width}}"


# GPIO Setup

def setup_hardware():

    leak = DigitalInputDevice(
        LEAK_GPIO,
        pull_up=False
    )

    # DRV8871 Motor Driver
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



# Status Indicators

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


# Reset

def reset_outputs(hw):

    hw["motor_in1"].off()
    hw["motor_in2"].off()

    hw["pwm1"].off()
    hw["pwm2"].off()

    hw["mosfet1"].off()
    hw["mosfet2"].off()
    hw["mosfet3"].off()
    hw["mosfet4"].off()


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



def draw_screen(
    stdscr,
    hw,
    powerboard,
    leak_enabled
):

    stdscr.erase()


    voltage_error = None
    current_error = None

    try:
        voltages = powerboard.read_voltages()

    except Exception as e:

        voltage_error = str(e)

        voltages = {
            "48V": None,
            "12V_LEFT": None,
            "12V_RIGHT": None,
            "3V3": None,
        }

    try:
        currents = powerboard.read_thruster_currents()

    except Exception as e:

        current_error = str(e)

        currents = {
            i: None
            for i in range(1, 9)
        }

    # Leak sensor
    if leak_enabled:
        leak_status = bool(hw["leak"].value)

    else:
        leak_status = False

    #Terminal Interface:

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

        f"3.3V Bus : {format_reading(voltages['3V3'], 3, 7)} V",
        f"5V Bus   : SuperHAT sensing not configured",
        f"12V Bus  : SuperHAT sensing not configured",

        "",

        f"Leak Status: {leak_status}",
        '(Toggle leak monitoring with "w")',

        "",

        "---------------------- POWERBOARD ----------------------------",

        "",

        "Power Rails:",

        f"48V       : {format_reading(voltages['48V'], 3, 7)} V",
        f"12V Left  : {format_reading(voltages['12V_LEFT'], 3, 7)} V",
        f"12V Right : {format_reading(voltages['12V_RIGHT'], 3, 7)} V",
        f"3.3V      : {format_reading(voltages['3V3'], 3, 7)} V",

        "",

        "Thruster Current:",

        f"Thruster 1 : {format_reading(currents[1], 2, 6)} A      "
        f"Thruster 2 : {format_reading(currents[2], 2, 6)} A",

        f"Thruster 5 : {format_reading(currents[5], 2, 6)} A      "
        f"Thruster 6 : {format_reading(currents[6], 2, 6)} A",

        f"Thruster 7 : {format_reading(currents[7], 2, 6)} A      "
        f"Thruster 8 : {format_reading(currents[8], 2, 6)} A",

        f"Thruster 3 : {format_reading(currents[3], 2, 6)} A      "
        f"Thruster 4 : {format_reading(currents[4], 2, 6)} A",

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

    
    # Error display

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

    lines += ["", "I2C ADC Status:"]
    for address in (VOLTAGE_ADC_ADDRESS, LEFT_THRUSTER_ADC_ADDRESS,
                    RIGHT_THRUSTER_ADC_ADDRESS):
        state = "CONNECTED" if powerboard.channels[address] is not None else "N/A (offline)"
        lines.append(f"0x{address:02X}: {state}")

    for y, line in enumerate(lines):
        write_line(stdscr, y, line)

    stdscr.refresh()


def main(stdscr):

    curses.curs_set(0)

    stdscr.nodelay(True)
    stdscr.timeout(50)

    # Initialize GPIO

    hw = setup_hardware()

    # Initialize PowerBoard

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

            # Quit

            if key == "q":
                break

            # Reset

            elif key == "r":

                reset_outputs(hw)

                leak_enabled = True

            # Leak Sensors

            elif key == "w":

                leak_enabled = not leak_enabled

            # Motor Direction

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

            # PWM 1

            elif key == "d":

                if hw["pwm1"].value > 0:

                    hw["pwm1"].off()

                else:

                    hw["pwm1"].value = 1.0

            # PWM 2

            elif key == "f":

                if hw["pwm2"].value > 0:

                    hw["pwm2"].off()

                else:

                    hw["pwm2"].value = 1.0

            # MOSFETS

            elif key == "g":

                hw["mosfet1"].toggle()

            elif key == "h":

                hw["mosfet2"].toggle()

            elif key == "j":

                hw["mosfet3"].toggle()

            elif key == "k":

                hw["mosfet4"].toggle()

    # EMERGENCY CLEANUP

    finally:

        reset_outputs(hw)
        powerboard.close()

        for device in hw.values():

            try:
                device.close()

            except Exception:
                pass


# START

if __name__ == "__main__":

    curses.wrapper(main)
