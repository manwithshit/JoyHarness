# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NS Joy-Con R Keyboard Mapper — maps a Bluetooth-connected Nintendo Switch Joy-Con R controller to keyboard shortcuts on Windows 11. Written in Python, uses pygame for controller input and the `keyboard` library for keystroke simulation.

## Commands

```bash
pip install -r requirements.txt           # Install dependencies (pygame, keyboard)
python src/main.py                        # Run mapper with default config
python src/main.py --discover             # Raw button/axis value display for debugging
python src/main.py --config config/default.json  # Run with specific config
python src/main.py --list-controls        # Print all current mappings and exit
python src/main.py --verbose              # Debug logging
python src/main.py --deadzone 0.2         # Override deadzone at runtime
python calibrate.py                       # Interactive button/axis calibration tool
run.bat                                   # Launch with admin elevation (required for keyboard sim)
```

No build step, no test framework, no CI.

## Architecture

Data pipeline: `pygame joystick → joycon_reader → joystick_handler (math) → key_mapper → keyboard_output`

- **`src/constants.py`** — Single source of truth for hardware button indices, axis indices, default deadzone (0.2), default key mappings, and valid action types. These values were calibrated for a specific Joy-Con R via `calibrate.py`. Button indices are non-sequential (e.g., R=16, ZR=18) because SDL2 maps them that way.

- **`src/joycon_reader.py`** — pygame joystick polling at 100Hz. Auto-detects Joy-Con by name. Calls `pygame.event.pump()` every frame (required for state updates). Stick direction changes use snapback protection (2 frames at center before registering release).

- **`src/joystick_handler.py`** — Pure math: circular deadzone with radial rescaling, atan2-based direction classification (4dir/8dir).

- **`src/key_mapper.py`** — Event translation engine. Four action types:
  - `tap` — instant press-release
  - `hold` — press on down, release on up (modifiers)
  - `auto` — short press (<250ms) = tap, long press = hold (uses `poll()` per frame)
  - `combination` — multi-key chord (press left-to-right, release right-to-left)

- **`src/keyboard_output.py`** — `keyboard` library wrapper with `_held_keys` set to prevent double-press and ensure cleanup.

- **`src/config_loader.py`** — JSON config loading, deep merge with defaults, validates key names against `keyboard.key_to_scan_codes()`.

- **`src/main.py`** — CLI entry point via argparse. Checks admin privileges. Wires config → KeyMapper → polling loop.

- **`calibrate.py`** — Standalone interactive tool. Guides user to press each button, records pygame indices, calibrates stick axes. Outputs `calibration_result.json`.

- **`config/default.json`** — User-editable key mapping config. Schema: buttons map `{name: {action, key/keys}}`, stick_directions map `{direction: {action, key/keys}}`.

## Key Constraints

- **Admin required**: The `keyboard` library needs administrator privileges on Windows to simulate input. `run.bat` handles auto-elevation.
- **Button indices are hardware-specific**: SDL2 assigns non-obvious indices (e.g., X=0, A=1, Y=2, B=3, R=16, ZR=18). If controller/driver changes, re-run `calibrate.py`.
- **Stick axes**: Axis 0 = horizontal (left=-, right=+), Axis 1 = vertical (up=-, down=+). Deadzone 0.2 covers typical Joy-Con drift.
- **`pygame.event.pump()` must be called every frame** — without it, joystick state goes stale.
- **Stick `auto` action** = immediate hold (no short/long distinction like buttons), released on center. Button `auto` uses 250ms threshold.
