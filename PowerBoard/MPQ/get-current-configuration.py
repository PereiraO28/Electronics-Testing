from smbus import SMBus

BUS_NUMBER = 1
MPQ_ADDRESS = 0x6a  # Replace with actual address

with SMBus(BUS_NUMBER) as bus:

    # Read overcurrent fault threshold
    fault_limit = bus.read_word_data(MPQ_ADDRESS, 0x46)

    # Read overcurrent response configuration
    fault_response = bus.read_byte_data(MPQ_ADDRESS, 0x47)

    # Read overcurrent warning threshold
    warn_limit = bus.read_word_data(MPQ_ADDRESS, 0x4A)

    print(f"Fault limit (raw): 0x{fault_limit:04X}")
    print(f"Fault response: 0x{fault_response:02X}")
    print(f"Warning limit (raw): 0x{warn_limit:04X}")
