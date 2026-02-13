# wingather — Platform Support

## Current Status

| Platform | Status | API | Notes |
|----------|--------|-----|-------|
| **Windows** | Supported | Win32 (pywin32) | Full implementation |
| **macOS** | Planned | PyObjC / Quartz | Stub in place |
| **Linux/X11** | Planned | python-xlib / wmctrl | Stub in place |
| **Linux/Wayland** | Not feasible | — | Compositor security model prevents cross-client window management |

## Windows (Supported)

### Requirements
- Python 3.8+
- `pywin32` >= 305
- `psutil` >= 5.9.0

### Features
- Window enumeration via `EnumWindows` with DPI awareness (`SetProcessDpiAwareness`)
- Window state detection: normal, minimized, maximized, hidden, off-screen, cloaked
- Window restore (`ShowWindow`), move/resize (`SetWindowPos`), and center on monitor
- DWM cloaking detection (`DwmGetWindowAttribute` with `DWMWA_CLOAKED`)
- Virtual desktop support via `IVirtualDesktopManager` COM interface
- Cascade positioning for suspicious windows with z-order priority
- Process executable path resolution for trust verification
- Microsoft Authenticode signature verification via PowerShell `Get-AuthenticodeSignature`

### Running as Administrator

For best results, run as Administrator. Without elevation:
- Windows belonging to elevated processes (Task Manager, Process Explorer, etc.) cannot be moved
- Some system windows may not be enumerable

### Multi-Monitor

wingather is DPI-aware and handles mixed-DPI multi-monitor setups correctly. Use `--monitor N` to target a specific monitor (0 = primary).

## macOS (Planned)

### Approach
The macOS stub is in `wingather/platforms/macos.py`. Implementation would use:
- **PyObjC** — Python bindings for Objective-C frameworks
- **Quartz / CGWindow API** — window enumeration and management
- **NSApplication** — application-level window access

### Challenges
- macOS Accessibility permissions required for cross-application window management
- App Sandbox restrictions may limit what's possible
- Virtual desktop (Spaces) API is private and undocumented

### How to Help
If you're a macOS developer interested in implementing this, see:
- [GitHub Discussions](https://github.com/DazzleTools/wingather/discussions) — share what works and what doesn't
- `wingather/platforms/base.py` — the abstract interface to implement
- `wingather/platforms/macos.py` — the current stub

## Linux/X11 (Planned)

### Approach
The Linux stub is in `wingather/platforms/linux.py`. Implementation would use:
- **python-xlib** — direct X11 protocol access
- **wmctrl** — command-line window management (fallback)
- **xdotool** — window manipulation toolkit

### Challenges
- Window manager diversity — behavior varies across GNOME, KDE, i3, etc.
- Extended Window Manager Hints (EWMH) compliance varies
- Some window managers intercept or modify positioning requests

### How to Help
If you're a Linux developer interested in implementing this:
- [GitHub Discussions](https://github.com/DazzleTools/wingather/discussions) — share your window manager and what APIs work
- The core logic (concern scoring, trust system, CLI) is platform-agnostic — only the platform layer needs implementation

## Linux/Wayland (Not Feasible)

Wayland's security model intentionally prevents clients from inspecting or manipulating other clients' windows. This is by design — it's a security feature, not a limitation to work around.

Compositors like Sway or GNOME Shell may expose their own IPC protocols (e.g., `sway-ipc`), but these are compositor-specific and don't provide a portable solution.

## Architecture

wingather uses a platform abstraction layer:

```
wingather/
├── core.py              # Platform-agnostic orchestration, scoring, trust
├── cli.py               # CLI parsing and output formatting
└── platforms/
    ├── __init__.py      # get_platform() auto-detection
    ├── base.py          # Abstract base class (WindowInfo, PlatformBase)
    ├── windows.py       # Windows implementation
    ├── macos.py         # macOS stub
    └── linux.py         # Linux stub
```

The `PlatformBase` abstract class defines the interface that each platform must implement:
- `setup()` — platform initialization (e.g., DPI awareness)
- `enumerate_windows()` — discover all top-level windows
- `restore_window()` — restore from minimized/hidden state
- `center_window()` — center and position with cascade offset
- `bring_to_front()` — bring window to foreground z-order
- `get_monitor_work_area()` — get usable screen area
- `is_elevated()` — check for admin/root privileges

All concern scoring, trust verification, filtering, and output logic lives in `core.py` and `cli.py` — platform implementations only need to handle the Win32/Cocoa/X11 specifics.
