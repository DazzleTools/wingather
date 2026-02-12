# wingather

Bring **all** windows to the foreground and center them on screen.

Finds hidden, minimized, off-screen, and obscured windows -- restores them and centers them on your chosen monitor. Useful for:

- **Security investigation** -- surface suspicious hidden dialogs or message boxes
- **Window rescue** -- recover windows lost off-screen after monitor disconnect
- **Desktop cleanup** -- quickly gather all windows to one spot

## Installation

```bash
# From source
git clone https://github.com/DazzleTools/wingather.git
cd wingather
pip install -e .

# Or run directly
python -m wingather
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

## Cross-Platform

Designed with a platform abstraction layer. Currently implemented for **Windows** only. macOS and Linux stubs are in place for future development.

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

GNU GPL v3 -- see [LICENSE](LICENSE) file.
