"""NS Joy-Con R Keyboard Mapper — CLI entry point.

Maps Nintendo Switch Joy-Con R controller inputs to keyboard shortcuts.
Supports configurable key mappings via JSON config files.

Usage:
    python -m src                    # Run with default mappings
    python src/main.py               # Also supported
    python -m src --discover         # Calibrate button indices
    python -m src --config my.json   # Use custom config
"""

import argparse
import ctypes
import logging
import sys
import threading
from pathlib import Path

# Ensure the project root is on sys.path so that `src` is importable
# as a package when running `python src/main.py` directly.
if __package__ is None:
    _project_root = str(Path(__file__).resolve().parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    __package__ = "src"

import pygame

from .battery_reader import BatteryReader
from .config_loader import load_config, get_profile, USER_CONFIG_PATH
from .gui import MainWindow
from .joycon_reader import find_joycon, detect_connection_mode, run_discover_mode, run_polling_loop, wait_for_reconnection
from .key_mapper import KeyMapper
from .tray_icon import create_tray_icon, run_tray

logger = logging.getLogger(__name__)


def is_admin() -> bool:
    """Check if the current process has administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def list_controls(config: dict) -> None:
    """Print all configured button/direction mappings."""
    from .constants import MODE_LABELS

    active_profile = config.get("active_profile", "single_right")
    profile_label = MODE_LABELS.get(active_profile, active_profile)
    print(f"\nActive profile: {profile_label} ({active_profile})")

    mappings = config.get("mappings", {})

    print("\n=== Button Mappings ===")
    for btn_name, mapping in mappings.get("buttons", {}).items():
        action = mapping["action"]
        if action == "combination":
            target = "+".join(mapping["keys"])
        else:
            target = mapping.get("key", "?")
        print(f"  {btn_name:8s} [{action:11s}] → {target}")

    print("\n=== Stick Direction Mappings ===")
    for direction, mapping in mappings.get("stick_directions", {}).items():
        action = mapping["action"]
        if action == "combination":
            target = "+".join(mapping["keys"])
        else:
            target = mapping.get("key", "?")
        print(f"  {direction:8s} [{action:11s}] → {target}")

    print(f"\nDeadzone: {config.get('deadzone', 0.15)}")
    print(f"Stick mode: {config.get('stick_mode', '4dir')}")
    print(f"Poll interval: {config.get('poll_interval', 0.01) * 1000:.0f}ms")

    # Show available profiles
    profiles = config.get("profiles", {})
    if profiles:
        print("\nAvailable profiles:")
        for mode in profiles:
            label = MODE_LABELS.get(mode, mode)
            marker = " (active)" if mode == active_profile else ""
            print(f"  {label} ({mode}){marker}")


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="NS Joy-Con R Keyboard Mapper — Map controller buttons to keyboard shortcuts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/main.py --discover       # Calibrate button indices first
  python src/main.py                  # Run with default mappings
  python src/main.py --config custom.json  # Use custom config
  python src/main.py --deadzone 0.2   # Override deadzone
  python src/main.py --list-controls  # Show current mappings
        """,
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to JSON config file (default: built-in defaults)",
    )
    parser.add_argument(
        "--discover", "-d",
        action="store_true",
        help="Discovery mode: print raw button/axis values for calibration",
    )
    parser.add_argument(
        "--deadzone",
        type=float,
        default=None,
        help="Override deadzone value (0.0 to 0.99)",
    )
    parser.add_argument(
        "--joystick", "-j",
        type=int,
        default=None,
        help="Specific joystick device index to use",
    )
    parser.add_argument(
        "--list-controls", "-l",
        action="store_true",
        help="List all control names and current mappings, then exit",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"NSJC {__import__('src.constants', fromlist=['__version__']).__version__}",
    )
    parser.add_argument(
        "--no-admin-warn",
        action="store_true",
        help="Suppress administrator privilege warning",
    )

    return parser


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
    ]
    if args.verbose:
        log_path = Path(__file__).resolve().parent.parent / "nsjc.log"
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    # Admin check
    if not args.no_admin_warn and not is_admin():
        print("WARNING: Not running as administrator. Keyboard simulation may not work.")
        print("         Try: run.bat  or  run as admin in PowerShell")
        print()

    # Load config — prefer user config if it exists
    config_path = args.config
    if config_path is None and Path(USER_CONFIG_PATH).exists():
        config_path = USER_CONFIG_PATH
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}")
        sys.exit(1)

    # Override deadzone if specified
    if args.deadzone is not None:
        if not 0.0 <= args.deadzone < 1.0:
            print(f"Invalid deadzone: {args.deadzone} (must be 0.0 to 0.99)")
            sys.exit(1)
        config["deadzone"] = args.deadzone

    # List controls mode
    if args.list_controls:
        list_controls(config)
        return

    # Discover mode
    if args.discover:
        run_discover_mode(args.joystick)
        return

    # Normal mode
    pygame.init()

    js = find_joycon(args.joystick)
    if js is None:
        print("No Joy-Con R detected.")
        print("\nPairing instructions:")
        print("  1. Windows Settings → Bluetooth & devices → Add device")
        print("  2. Hold the small pairing button on the Joy-Con rail for 3 seconds")
        print("  3. Lights will flash rapidly — select 'Joy-Con R' in Bluetooth list")
        print("  4. Run --discover to verify connection")
        pygame.quit()
        sys.exit(1)

    print(f"Controller: {js.get_name()}")
    print(f"Buttons: {js.get_numbuttons()}, Axes: {js.get_numaxes()}")

    # Detect connection mode and load the appropriate profile
    connection_mode = detect_connection_mode()
    profile = get_profile(config, connection_mode)
    profile_mappings = profile.get("mappings", config.get("mappings", {}))
    config["mappings"] = profile_mappings
    config["active_profile"] = connection_mode

    from .constants import MODE_LABELS
    profile_label = MODE_LABELS.get(connection_mode, connection_mode)
    print(f"Connection mode: {profile_label} ({connection_mode})")
    print(f"Deadzone: {config['deadzone']}, Stick mode: {config['stick_mode']}")

    # Restore KNOWN_APPS from saved config
    from .window_switcher import set_known_apps
    known_apps = config.get("known_apps")
    if known_apps:
        set_known_apps(known_apps)

    key_mapper = KeyMapper(config, mode=connection_mode)
    stop_event = threading.Event()

    # Initialize WindowCycler with all apps from config (not just code.exe default)
    if known_apps:
        key_mapper._window_cycler.app_names = list(known_apps.values())

    # Start battery reader
    battery_reader = BatteryReader(stop_event)
    battery_reader.start()

    # Create GUI first so we can pass its mode-change callback to polling loop
    gui = MainWindow(
        key_mapper, key_mapper._window_cycler, config, stop_event,
        connection_mode=connection_mode,
        battery_reader=battery_reader,
    )
    key_mapper.set_tk_root(gui.root)

    # Start polling loop in background thread (after GUI so callback is available)
    poll_thread = threading.Thread(
        target=_run_polling,
        args=(js, key_mapper, config, stop_event, gui.update_connection_mode),
        daemon=True,
    )
    poll_thread.start()

    # Start tray icon in background thread
    icon = create_tray_icon(stop_event, on_show_window=gui.show)
    tray_thread = threading.Thread(target=run_tray, args=(icon,), daemon=True)
    tray_thread.start()

    print("GUI and tray active. Close window or right-click tray to quit.")

    # Run GUI in main thread (blocks until window closed)
    gui.run()

    # Cleanup
    stop_event.set()
    icon.stop()
    poll_thread.join(timeout=2.0)
    battery_reader.join(timeout=2.0)
    key_mapper.release_all()
    pygame.quit()
    print("Clean exit. All keys released.")


def _run_polling(
    joystick,
    key_mapper: KeyMapper,
    config: dict,
    stop_event: threading.Event,
    on_mode_change=None,
) -> None:
    """Run polling loop in a background thread, handling exceptions."""
    try:
        run_polling_loop(joystick, key_mapper, config, stop_event, on_mode_change=on_mode_change)
    except Exception:
        logger.exception("Polling thread error")


if __name__ == "__main__":
    main()
