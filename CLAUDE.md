# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

JoyHarness — maps Nintendo Switch Joy-Con controllers (left, right, or both) to keyboard shortcuts on Windows 11 via Bluetooth. Written in Python, uses pygame for controller input and the `keyboard` library for keystroke simulation.

Supports three connection modes with automatic detection:
- `single_right` — only right Joy-Con connected
- `single_left` — only left Joy-Con connected
- `dual` — both Joy-Cons connected as a combined SDL2 device

Each mode has its own key mapping profile, automatically selected at startup and hot-switched at runtime when connection mode changes.

## Commands

```bash
pip install -r requirements.txt           # Install dependencies (pygame, keyboard, pystray, ttkbootstrap, Pillow, hidapi)
python src/main.py                        # Run with default config (auto-detects connection mode)
python src/main.py --discover             # Raw button/axis value display for debugging/calibration
python src/main.py --config config/default.json  # Run with specific config
python src/main.py --list-controls        # Print current mappings, active profile, and available profiles
python src/main.py --verbose              # Debug logging
python src/main.py --deadzone 0.2         # Override deadzone at runtime
python calibrate.py                       # Interactive button/axis calibration tool
run.bat                                   # Launch with admin elevation (required for keyboard sim)
```

No build step, no test framework, no CI.

## Architecture

Data pipeline: `pygame joystick → joycon_reader (detect mode + poll) → joystick_handler (math) → key_mapper (profile-aware) → keyboard_output`

### Multi-Profile System

The config has a `profiles` dict with three entries (`single_right`, `single_left`, `dual`), each containing its own `mappings`. The active profile is selected by `detect_connection_mode()` and stored in `config["active_profile"]`.

- **`src/constants.py`** — Hardware button indices for all three modes (`BUTTON_NAMES`, `BUTTON_NAMES_LEFT`, `BUTTON_NAMES_DUAL` and their reverse `BUTTON_INDICES_*`). Mode-based lookup tables: `BUTTON_NAMES_BY_MODE`, `BUTTON_INDICES_BY_MODE`, `MAPPABLE_BUTTONS_BY_MODE`, `MODE_LABELS`. Default mappings for each mode: `DEFAULT_MAPPINGS`, `DEFAULT_MAPPINGS_LEFT`, `DEFAULT_MAPPINGS_DUAL`. Helper functions `get_button_names(mode)` and `get_button_indices(mode)`.

- **`src/joycon_reader.py`** — pygame joystick polling at 100Hz. `find_joycon()` auto-detects Joy-Cons by name (accepts both L and R). `detect_connection_mode()` scans all connected joysticks to determine `single_left`/`single_right`/`dual`. Polling loop includes:
  - Periodic mode check every 5 seconds — detects hot-plug changes (e.g., connecting a second Joy-Con)
  - Reconnection on joystick disconnect — catches `pygame.error`, calls `wait_for_reconnection()`, re-calibrates baseline, re-detects mode
  - `on_mode_change` callback to notify GUI of mode changes

- **`src/joystick_handler.py`** — Pure math: circular deadzone with radial rescaling, atan2-based direction classification (4dir/8dir).

- **`src/key_mapper.py`** — Event translation engine. Initialized with `mode` param to use the correct button index table. `switch_profile(config, mode)` method allows runtime hot-switching (releases all held keys, rebuilds mappings). Supports action types: `tap`, `hold`, `auto`, `combination`, `sequence`, `window_switch`, `macro`.

- **`src/keyboard_output.py`** — `keyboard` library wrapper with `_held_keys` set to prevent double-press and ensure cleanup.

- **`src/config_loader.py`** — JSON config loading with backward compatibility. `merge_with_defaults()` auto-migrates old format (top-level `mappings`) to `profiles.single_right`. `get_profile(config, mode)` retrieves a specific profile. `validate_config()` validates each profile against its mode-specific button names.

- **`src/main.py`** — CLI entry point via argparse. Detects connection mode after `find_joycon()`, loads the matching profile into `config["mappings"]`, creates `KeyMapper(config, mode=...)`. Passes `gui.update_connection_mode` as callback to polling loop for runtime mode change notifications.

- **`src/gui.py`** — ttkbootstrap main window. Title bar shows current mode (e.g., `JoyHarness [右手柄]`). `update_connection_mode(mode)` uses `root.after(0, ...)` for thread-safe widget updates from the polling daemon thread.

- **`src/settings_window.py`** — Settings UI. Uses `MAPPABLE_BUTTONS_BY_MODE[mode]` to show correct buttons for current mode. Reads/writes from `config["profiles"][mode]["mappings"]`. Reset defaults uses `DEFAULT_CONFIGS[mode]`.

- **`calibrate.py`** — Standalone interactive tool. Guides user to press each button, records pygame indices, calibrates stick axes. Outputs `calibration_result.json`.

- **`config/default.json`** — Default config. User customizations are saved to `config/user.json`.

## Key Constraints

- **Admin required**: The `keyboard` library needs administrator privileges on Windows to simulate input. `run.bat` handles auto-elevation.
- **Button indices are mode-specific**: SDL2 assigns different indices depending on connection mode. Right Joy-Con alone: X=0, A=1, R=16, ZR=18. Combined device: different indices. If button mapping is wrong, re-run `calibrate.py` in the correct connection mode.
- **Left/dual button indices are placeholders**: The `single_left` and `dual` mode constants in `constants.py` need calibration via `--discover` with actual hardware.
- **Stick axes**: Axis 0 = horizontal (left=-, right=+), Axis 1 = vertical (up=-, down=+). Deadzone 0.2 covers typical Joy-Con drift.
- **`pygame.event.pump()` must be called every frame** — without it, joystick state goes stale.
- **Stick `auto` action** = immediate hold (no short/long distinction like buttons), released on center. Button `auto` uses 250ms threshold.
- **Config backward compatibility**: Old format (top-level `mappings` without `profiles`) is auto-migrated to `profiles.single_right` on first load.
