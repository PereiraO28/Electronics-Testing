
#!/usr/bin/env python3
"""
Murata MPQ860 PMBus diagnostic tool
Raspberry Pi 5 / Linux I2C

READ ONLY: no configuration writes or fault clearing.
"""

import argparse
import csv
import time
from datetime import datetime
from smbus2 import SMBus

# (name, command, SMBus type, decoding, unit)
# "raw" means the register is reported without interpretation.
COMMANDS = [
    # Telemetry
    ("Input Voltage",       0x88, "word", "linear11", "V"),
    ("Output Voltage",      0x8B, "word", "vout", "V"),
    ("Output Current",      0x8C, "word", "linear11", "A"),
    ("Temperature",         0x8D, "word", "linear11", "C"),
    ("Duty Cycle",          0x94, "word", "linear11", "%"),
    ("Switching Frequency", 0x95, "word", "linear11", "kHz"),
    ("Output Power",        0x96, "word", "linear11", "W"),

    # Overall status
    ("STATUS_BYTE",         0x78, "byte", "hex", ""),
    ("STATUS_WORD",         0x79, "word", "hex", ""),
    ("STATUS_VOUT",         0x7A, "byte", "hex", ""),
    ("STATUS_IOUT",         0x7B, "byte", "hex", ""),
    ("STATUS_INPUT",        0x7C, "byte", "hex", ""),
    ("STATUS_TEMPERATURE",  0x7D, "byte", "hex", ""),
    ("STATUS_CML",          0x7E, "byte", "hex", ""),

    # Configuration / operating state
    ("OPERATION",           0x01, "byte", "hex", ""),
    ("ON_OFF_CONFIG",       0x02, "byte", "hex", ""),
    ("WRITE_PROTECT",       0x10, "byte", "hex", ""),
    ("CAPABILITY",          0x19, "byte", "hex", ""),
    ("VOUT_MODE",           0x20, "byte", "hex", ""),
    ("VOUT_TRIM",           0x22, "word", "raw", ""),
    ("VOUT_DROOP",          0x28, "word", "raw", ""),
    ("VIN_ON",              0x35, "word", "linear11", "V"),
    ("VIN_OFF",             0x36, "word", "linear11", "V"),

    # Output voltage protection
    ("VOUT_OV_FAULT_LIMIT",  0x40, "word", "vout", "V"),
    ("VOUT_OV_RESPONSE",     0x41, "byte", "hex", ""),
    ("VOUT_OV_WARN_LIMIT",   0x42, "word", "vout", "V"),

    # Output current protection
    ("IOUT_OC_FAULT_LIMIT",  0x46, "word", "linear11", "A"),
    ("IOUT_OC_RESPONSE",     0x47, "byte", "hex", ""),
    ("IOUT_OC_WARN_LIMIT",   0x4A, "word", "linear11", "A"),

    # Thermal protection
    ("OT_FAULT_LIMIT",      0x4F, "word", "linear11", "C"),
    ("OT_FAULT_RESPONSE",   0x50, "byte", "hex", ""),
    ("OT_WARN_LIMIT",       0x51, "word", "linear11", "C"),

    # Input protection
    ("VIN_OV_FAULT_LIMIT",  0x55, "word", "linear11", "V"),
    ("VIN_OV_RESPONSE",     0x56, "byte", "hex", ""),
    ("VIN_OV_WARN_LIMIT",   0x57, "word", "linear11", "V"),
    ("VIN_UV_WARN_LIMIT",   0x58, "word", "linear11", "V"),
    ("VIN_UV_FAULT_LIMIT",  0x59, "word", "linear11", "V"),
    ("VIN_UV_RESPONSE",     0x5A, "byte", "hex", ""),

    # Power good and startup
    ("POWER_GOOD_ON",       0x5E, "word", "vout", "V"),
    ("POWER_GOOD_OFF",      0x5F, "word", "vout", "V"),
    ("TON_RISE",            0x61, "word", "raw", ""),

    # PMBus version
    ("PMBUS_REVISION",      0x98, "byte", "hex", ""),

    # Manufacturer-specific settings
    ("MFR_ON_OFF_CONFIG",   0xDD, "byte", "hex", ""),
    ("MFR_PGOOD_POLARITY",  0xDE, "byte", "hex", ""),
    ("MFR_FAULT_LOG_CONFIG",0xDF, "byte", "hex", ""),
    ("MFR_VIN_OV_HYST",     0xE8, "word", "raw", ""),
    ("MFR_VIN_UV_HYST",     0xE9, "word", "raw", ""),
    ("MFR_OT_HYST",         0xEA, "word", "raw", ""),
    ("MFR_VOUT_CAL",        0xFB, "word", "raw", ""),
]

# Manufacturer fault-log blocks are excluded:
# their layout/transaction format needs separate validation.

def signed(value, bits):
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def linear11(raw):
    exponent = signed((raw >> 11) & 0x1F, 5)
    mantissa = signed(raw & 0x7FF, 11)
    return mantissa * (2.0 ** exponent)


def vout_linear16(raw, mode):
    if mode is None:
        return None

    # VOUT_MODE bits 7:5 = 000 means Linear mode.
    if (mode >> 5) != 0:
        return None

    exponent = signed(mode & 0x1F, 5)
    return raw * (2.0 ** exponent)


def read_register(bus, address, cmd, kind):
    if kind == "byte":
        return bus.read_byte_data(address, cmd)
    return bus.read_word_data(address, cmd)


def decode(raw, fmt, mode):
    if fmt == "linear11":
        return linear11(raw)
    if fmt == "vout":
        return vout_linear16(raw, mode)
    if fmt == "hex":
        return f"0x{raw:04X}"
    return None


def collect(bus, address, commands, mode):
    rows = []

    for name, cmd, kind, fmt, unit in commands:
        stamp = datetime.now().isoformat(timespec="milliseconds")

        try:
            raw = read_register(bus, address, cmd, kind)
            value = decode(raw, fmt, mode)
            status = "OK"

            if isinstance(value, float):
                display = f"{value:.3f} {unit}".strip()
            elif value is None:
                display = "Raw only"
            else:
                display = str(value)

            raw_hex = f"0x{raw:04X}"

        except OSError as error:
            raw_hex = ""
            value = None
            display = "Read failed"
            status = str(error)

        rows.append({
            "timestamp": stamp,
            "address": f"0x{address:02X}",
            "name": name,
            "command": f"0x{cmd:02X}",
            "raw": raw_hex,
            "value": value,
            "unit": unit,
            "status": status
        })

        print(
            f"{name:<25} "
            f"{raw_hex:<10} "
            f"{display:<18} "
            f"{status}"
        )

    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bus", type=int, default=1)
    parser.add_argument("--address", type=lambda x: int(x, 0),
                        default=0x6A)
    parser.add_argument("--interval", type=float, default=0)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--output", default="mpq860_log.csv")
    parser.add_argument("--all", action="store_true",
                        help="Include configuration registers")
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")

    # Default: telemetry + status only.
    # --all: every register listed above.
    commands = COMMANDS if args.all else COMMANDS[:14]

    fields = [
        "timestamp", "address", "name",
        "command", "raw", "value", "unit", "status"
    ]

    with SMBus(args.bus) as bus, open(
        args.output, "w", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        # Read VOUT_MODE once to determine voltage exponent.
        try:
            mode = bus.read_byte_data(args.address, 0x20)
            print(f"VOUT_MODE: 0x{mode:02X}")
        except OSError as error:
            mode = None
            print(f"VOUT_MODE unavailable: {error}")
            print("Output voltage will remain raw.")

        for sample in range(args.count):
            print(
                f"\nMPQ860 0x{args.address:02X}"
                f" | Sample {sample + 1}/{args.count}"
            )
            print("-" * 85)

            rows = collect(bus, args.address, commands, mode)
            writer.writerows(rows)
            file.flush()

            if sample + 1 < args.count:
                time.sleep(max(0, args.interval))

    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
