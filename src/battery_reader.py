"""Joy-Con R battery level reader via raw HID protocol.

Runs in a background daemon thread, reading battery status from the
Joy-Con's standard input report (report 0x30, byte 2 high nibble).
Works concurrently with pygame's joystick polling.

Thread-safe: writes to shared variables protected by a threading.Lock.
The GUI reads these variables via root.after() polling.
"""

import logging
import threading
import time

import hid

logger = logging.getLogger(__name__)

_VID = 0x057E  # Nintendo
_PID = 0x2007  # Joy-Con R


def battery_label(nibble: int) -> tuple[str, int]:
    """Return (status_string, percentage) from the 4-bit battery value.

    Values 0x00-0x08: discharging, each step ~12.5%.
    Values 0x09-0x0F: charging.
    """
    if nibble <= 0x08:
        return ("discharging", min(nibble * 125 // 10, 100))
    elif nibble <= 0x0F:
        return ("charging", min((nibble & 0x0F) * 125 // 10, 100))
    return ("unknown", -1)


class BatteryReader:
    """Reads Joy-Con battery level in a background thread.

    Stores the latest reading in thread-safe shared state that the GUI
    can poll via ``get_state()``.
    """

    def __init__(self, stop_event: threading.Event) -> None:
        self._stop_event = stop_event
        self._thread: threading.Thread | None = None

        # Shared state (protected by lock)
        self._lock = threading.Lock()
        self._status: str = "unknown"
        self._pct: int = -1

    # -- public API for the GUI --

    def get_state(self) -> tuple[str, int]:
        """Return (status, percentage). Thread-safe."""
        with self._lock:
            return self._status, self._pct

    def start(self) -> None:
        """Start the background reading thread."""
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the thread to stop."""
        self._stop_event.set()

    def join(self, timeout: float = 2.0) -> None:
        """Wait for the background thread to finish."""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # -- internal --

    def _set_state(self, status: str, pct: int) -> None:
        with self._lock:
            self._status = status
            self._pct = pct

    def _read_loop(self) -> None:
        """Main loop: find Joy-Con, open HID, read battery periodically."""
        while not self._stop_event.is_set():
            dev_info = self._find_joycon()
            if dev_info is None:
                self._set_state("disconnected", -1)
                self._stop_event.wait(5)
                continue

            dev = hid.device()
            try:
                dev.open_path(dev_info["path"])
            except OSError as e:
                logger.warning("Cannot open HID device for battery: %s", e)
                self._set_state("disconnected", -1)
                self._stop_event.wait(5)
                continue

            logger.debug("Battery reader: HID device opened")

            # Set input report mode to 0x30 (standard full report)
            report_mode_cmd = bytes([
                0x01, 0x00,                         # report_id, counter
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, # rumble off
                0x00, 0x00,                         # padding
                0x03,                               # subcommand: set report mode
                0x30,                               # mode: standard full
            ])
            try:
                dev.write(report_mode_cmd)
            except OSError:
                self._set_state("disconnected", -1)
                self._safe_close(dev)
                self._stop_event.wait(5)
                continue

            # Read reports until disconnect or stop
            self._read_reports(dev)
            self._safe_close(dev)
            logger.debug("Battery reader: HID device closed")

    def _read_reports(self, dev) -> None:
        """Continuously read HID reports and update battery state."""
        consecutive_errors = 0
        last_battery_time = 0.0

        while not self._stop_event.is_set():
            try:
                data = dev.read(64, timeout_ms=1000)
            except OSError:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    logger.debug("Battery reader: HID read failed repeatedly, device likely disconnected")
                    self._set_state("disconnected", -1)
                    return
                continue

            if not data:
                # Timeout, no data — keep alive
                # Check if we haven't had a reading in a while
                if last_battery_time > 0 and time.time() - last_battery_time > 10:
                    self._set_state("disconnected", -1)
                    return
                continue

            consecutive_errors = 0

            if len(data) < 3:
                continue

            report_id = data[0]
            if report_id not in (0x30, 0x3F):
                continue

            battery_byte = data[2]
            battery_nibble = (battery_byte >> 4) & 0x0F
            status, pct = battery_label(battery_nibble)
            self._set_state(status, pct)
            last_battery_time = time.time()

            # Sleep between readings — we don't need to read continuously,
            # just enough to keep the connection alive and catch changes
            self._stop_event.wait(5)

    @staticmethod
    def _find_joycon() -> dict | None:
        """Find Joy-Con R HID device."""
        devices = hid.enumerate(_VID, _PID)
        return devices[0] if devices else None

    @staticmethod
    def _safe_close(dev) -> None:
        """Close HID device, swallowing errors if already disconnected."""
        try:
            dev.close()
        except OSError:
            pass
