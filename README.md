# wingather

[![PyPI](https://img.shields.io/pypi/v/wingather?color=green)](https://pypi.org/project/wingather/)
[![Release Date](https://img.shields.io/github/release-date/DazzleTools/wingather?color=green)](https://github.com/DazzleTools/wingather/releases)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/license-GPL%20v3-green.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![GitHub Discussions](https://img.shields.io/github/discussions/DazzleTools/wingather)](https://github.com/DazzleTools/wingather/discussions)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](docs/platform-support.md)

> **Windows admin and security tool for discovering, recovering, and managing hidden or inaccessible windows.**

Finds hidden, minimized, off-screen, and obscured windows -- restores them and centers them on your chosen monitor. Useful for:

- **Security investigation** -- surface suspicious hidden dialogs or message boxes
- **Window rescue** -- recover windows lost off-screen after monitor disconnect
- **Desktop cleanup** -- quickly gather all windows to one spot (including from other desktops)

## Installation

```bash
# From PyPI (coming soon)
pip install wingather

# From source
git clone https://github.com/DazzleTools/wingather.git
cd wingather
pip install -e .
```

## Usage

```bash
# Gather all windows to center of primary monitor
wingather

# Dry run -- just list what's out there
wingather --list-only

# Also reveal hidden windows (use with caution)
wingather --show-hidden

# Center on a specific monitor (0=primary, 1=secondary, etc.)
wingather --monitor 1

# Filter by window title or process name (fnmatch patterns)
wingather --filter "*chrome*"
wingather --exclude "*spotify*"

# JSON output for scripting
wingather --json

# Verbose logging
wingather -v
```

See [docs/parameters.md](docs/parameters.md) for the full CLI reference with all options, filtering, trust configuration, and output modes.

### Running as Administrator

For best results, run as Administrator. Without elevation, windows belonging to elevated processes (e.g., Task Manager, Process Explorer) cannot be moved.

## What It Does

1. Sets DPI awareness for accurate multi-monitor coordinate handling
2. Enumerates **all** top-level windows via Win32 `EnumWindows`
3. Identifies window state: normal, minimized, hidden, off-screen, cloaked (virtual desktop)
4. Restores minimized windows
5. Optionally shows hidden windows
6. Centers each window on the target monitor's work area
7. Reports what was found and what action was taken

### Window States

| State | Description | Default Action |
|-------|-------------|----------------|
| `normal` | Visible, on-screen | Center |
| `minimized` | In taskbar | Restore + Center |
| `maximized` | Full-screen normal | Center (un-maximizes) |
| `hidden` | `WS_VISIBLE` not set | Skip (use `--show-hidden`) |
| `off-screen` | Beyond monitor bounds | Center |
| `cloaked` | On another virtual desktop | Skip (OS limitation) |

## Suspicious Window Detection

wingather flags windows that exhibit suspicious behavior using a weighted concern scoring system:

| Level | Label | Example Triggers | Action |
|-------|-------|-------------------|--------|
| `[!1]` | ALERT | Off-screen + dialog, trust verification failed | Set TOPMOST |
| `[!2]` | ALERT | Off-screen window | Set TOPMOST |
| `[!3]` | CONCERN | Heavily shrunk window | Set TOPMOST |
| `[!4]` | NOTE | Dialog, partially off-screen | Flagged only |
| `[!5]` | NOTE | Cloaked on another desktop | Flagged only |

See [docs/parameters.md](docs/parameters.md) for indicator weights and scoring details.

### Trust Verification

Built-in trusted processes (explorer.exe, etc.) are verified by checking their file path and Microsoft Authenticode signature before suppressing flags. A process masquerading as a trusted name but failing verification triggers an immediate level 1 ALERT.

```bash
# Bypass default trust list -- flag everything
wingather --no-default-trust --dry-run

# Trust additional processes
wingather -tp myapp.exe -tp "custom*"
```

## Cross-Platform

Designed with a platform abstraction layer. Currently implemented for **Windows** only. macOS and Linux stubs are in place for future development. See [docs/platform-support.md](docs/platform-support.md) for details, requirements, and how to help.

| Platform | Status |
|----------|--------|
| Windows | Implemented |
| macOS | Stub (PyObjC/Quartz planned) |
| Linux/X11 | Stub (python-xlib/wmctrl planned) |
| Linux/Wayland | Not feasible (compositor security model) |

## Requirements

- Python 3.8+
- Windows: `pywin32`, `psutil`

## Related Tools

- [process-delta](https://github.com/DazzleTools/process-delta) -- Process and service snapshot comparison tool
- [NirCmd](https://nircmd.nirsoft.net/) -- `win center alltop` does partial centering (no hidden/minimized restore)
- [GUIPropView](https://www.nirsoft.net/utils/gui_prop_view.html) -- GUI window inspector with manual center action

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

Like the project?

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)

## License

wingather, Copyright (C) 2026 Dustin Darcy

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

