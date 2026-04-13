"""
Joy-Con R Battery Level Checker
Reads battery level via raw HID protocol (hidapi).

SDL2/pygame's get_power_level() returns "unknown" for Joy-Con,
so we use hidapi to read the battery nibble directly from the
standard input report.

Usage: python script/check_battery.py

Battery nibble (byte 2, high nibble):
  0-8 = charging level (0=empty, 8=full, each step ~12.5%)
  9-F = charging (battery level in low nibble)
"""
import hid
import sys

VID = 0x057E  # Nintendo
PID = 0x2007  # Joy-Con R

# Standard input report (simple HID mode, no subcommand)
REPORT_ID = 0x30


def find_joycon() -> dict | None:
    devices = hid.enumerate(VID, PID)
    if not devices:
        return None
    # Prefer input-capable interface
    return devices[0]


def battery_label(nibble: int) -> tuple[str, int]:
    """Return (description, percentage) from the 4-bit battery value."""
    if nibble <= 0x08:
        pct = min(nibble * 125 // 10, 100)  # 0..8 -> 0..100%
        return ("discharging", pct)
    elif nibble <= 0x0F:
        level = nibble & 0x0F
        pct = min(level * 125 // 10, 100)
        return ("charging", pct)
    return ("unknown", -1)


def main() -> None:
    print("=== Joy-Con R Battery Level Check ===\n")

    dev_info = find_joycon()
    if not dev_info:
        print("Joy-Con R not found via HID.")
        print("Make sure it is paired via Bluetooth.")
        sys.exit(1)

    print(f"Found: {dev_info.get('product_string', 'N/A')}\n")

    dev = hid.device()
    try:
        dev.open_path(dev_info["path"])
    except OSError as e:
        print(f"Cannot open device: {e}")
        print("Another app may be holding the Joy-Con. Close it first.")
        sys.exit(1)

    print(f"Opened: {dev.get_manufacturer_string()} - {dev.get_product_string()}\n")

    # Send a simple "request report" subcommand to get the Joy-Con into
    # standard input report mode (0x30). Without this, the device may not
    # send input reports spontaneously when opened via HID alone.
    # Subcommand 0x03 = set input report mode to 0x30 (standard full).
    # Report format: [0x01, counter, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    #                 0x00, 0x00, 0x03, report_mode]
    report_mode_cmd = bytes([
        0x01, 0x00,                         # report_id=0x01, counter=0
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, # rumble (off)
        0x00, 0x00,                         # padding
        0x03,                               # subcommand: set input report mode
        0x30,                               # mode: standard full report
    ])
    dev.write(report_mode_cmd)

    # Read a few input reports to find one with battery data
    # In standard input report (0x30), byte[2] high nibble = battery
    print("Reading battery level...")
    battery = None

    for _ in range(50):
        data = dev.read(64, timeout_ms=500)
        if not data:
            continue
        if len(data) < 3:
            continue

        # Check for standard input report (0x30) or simple (0x3F)
        report_id = data[0]
        if report_id not in (0x30, 0x3F):
            continue

        # Byte 2: high nibble = battery level, low nibble = connection info
        battery_byte = data[2]
        battery_nibble = (battery_byte >> 4) & 0x0F
        status, pct = battery_label(battery_nibble)
        battery = (status, pct, battery_nibble)
        break

    if battery is None:
        print("Could not read battery level from input reports.")
        print("Try holding a button on the Joy-Con while running this script.")
        dev.close()
        sys.exit(1)

    status, pct, raw = battery

    # Visual bar
    bar_len = 20
    filled = int(bar_len * pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)

    print(f"  Status:    {status}")
    print(f"  Battery:   {pct}%  [{bar}]")
    print(f"  Raw value: 0x{raw:X}")

    if status == "charging":
        print("  (Charging via grip/USB)")
    elif pct <= 25:
        print("  (Low battery — consider charging soon)")

    dev.close()


if __name__ == "__main__":
    main()
