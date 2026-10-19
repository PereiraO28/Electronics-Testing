from smbus2 import SMBus

ADDRESS = 0x61  # Replace with actual PMBus address

with SMBus(1) as bus:
    # Read current soft-start setting
    current = bus.read_word_data(ADDRESS, 0x61)
    print(f"Current rise time: {current} ms")

    # Set soft-start to 100 ms
    bus.write_word_data(ADDRESS, 0x61, 100)

    # Verify
    print("New rise time:",
          bus.read_word_data(ADDRESS, 0x61), "ms")
