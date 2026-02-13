"""Windows implementation of window enumeration and manipulation."""

import ctypes
import ctypes.wintypes
import logging
import os

from wingather.platforms.base import PlatformBase, WindowInfo

logger = logging.getLogger(__name__)

# Lazy imports - only loaded on Windows
win32gui = None
win32con = None
win32process = None
win32api = None
psutil = None


def _load_win32():
    """Lazy-load pywin32 modules."""
    global win32gui, win32con, win32process, win32api, psutil
    if win32gui is not None:
        return
    try:
        import win32gui as _win32gui
        import win32con as _win32con
        import win32process as _win32process
        import win32api as _win32api
        import psutil as _psutil
        win32gui = _win32gui
        win32con = _win32con
        win32process = _win32process
        win32api = _win32api
        psutil = _psutil
    except ImportError as e:
        raise RuntimeError(
            "pywin32 and psutil are required on Windows. "
            "Install with: pip install pywin32 psutil"
        ) from e


# ---------------------------------------------------------------------------
# IVirtualDesktopManager COM interface (documented API)
# Allows checking and moving windows between virtual desktops.
# Lazy-loaded to avoid import noise when not needed.
# ---------------------------------------------------------------------------
_comtypes = None
_comtypes_client = None


def _load_comtypes():
    """Lazy-load comtypes to avoid import noise when not using virtual desktops."""
    global _comtypes, _comtypes_client
    if _comtypes is not None:
        return
    import logging as _logging
    # Suppress comtypes INFO-level cache messages
    _logging.getLogger('comtypes').setLevel(_logging.WARNING)
    import comtypes
    import comtypes.client
    _comtypes = comtypes
    _comtypes_client = comtypes.client


def _get_comtypes_guids():
    """Return (IID, CLSID) for IVirtualDesktopManager after loading comtypes."""
    _load_comtypes()
    IID = _comtypes.GUID('{A5CD92FF-29BE-454C-8D04-D82879FB3F1B}')
    CLSID = _comtypes.GUID('{AA509086-5CA9-4C25-8F95-589D3C07B48A}')
    return IID, CLSID


def _build_ivdm_class():
    """Build the IVirtualDesktopManager COM interface class dynamically.

    Done lazily so comtypes is only imported when actually needed.
    """
    _load_comtypes()
    IID, _ = _get_comtypes_guids()

    class IVirtualDesktopManager(_comtypes.IUnknown):
        _iid_ = IID
        _methods_ = [
            _comtypes.COMMETHOD(
                [], ctypes.HRESULT, 'IsWindowOnCurrentVirtualDesktop',
                (['in'], ctypes.wintypes.HWND, 'topLevelWindow'),
                (['out'], ctypes.POINTER(ctypes.c_bool), 'onCurrentDesktop'),
            ),
            _comtypes.COMMETHOD(
                [], ctypes.HRESULT, 'GetWindowDesktopId',
                (['in'], ctypes.wintypes.HWND, 'topLevelWindow'),
                (['out'], ctypes.POINTER(_comtypes.GUID), 'desktopId'),
            ),
            _comtypes.COMMETHOD(
                [], ctypes.HRESULT, 'MoveWindowToDesktop',
                (['in'], ctypes.wintypes.HWND, 'topLevelWindow'),
                (['in'], ctypes.POINTER(_comtypes.GUID), 'desktopId'),
            ),
        ]

    return IVirtualDesktopManager


class VirtualDesktopHelper:
    """Helper for moving windows between virtual desktops.

    Uses the documented IVirtualDesktopManager COM interface.
    This does NOT use the undocumented internal interfaces that break
    between Windows builds.
    """

    def __init__(self):
        self._manager = None
        self._current_desktop_id = None
        self._available = False
        self._init()

    def _init(self):
        try:
            _load_comtypes()
            _, CLSID = _get_comtypes_guids()
            IVDMClass = _build_ivdm_class()
            self._manager = _comtypes.CoCreateInstance(
                CLSID,
                interface=IVDMClass,
            )
            self._available = True
            logger.debug("IVirtualDesktopManager COM interface available")
        except Exception as e:
            logger.debug(f"Virtual desktop COM interface not available: {e}")
            self._available = False

    @property
    def available(self):
        return self._available

    def _ensure_current_desktop_id(self):
        """Determine the current virtual desktop's GUID.

        Strategy: find any non-cloaked, visible window and ask the COM
        interface which desktop it lives on.  That must be the active one.
        """
        if self._current_desktop_id is not None:
            return True
        if not self._available:
            return False

        _load_win32()
        fg = win32gui.GetForegroundWindow()
        if fg:
            try:
                guid = _comtypes.GUID()
                self._manager.GetWindowDesktopId(fg, ctypes.byref(guid))
                self._current_desktop_id = guid
                logger.debug(f"Current desktop GUID: {guid}")
                return True
            except Exception as e:
                logger.debug(f"Could not get desktop id from foreground: {e}")

        return False

    def is_on_current_desktop(self, hwnd):
        """Check if a window handle is on the current virtual desktop."""
        if not self._available:
            return True  # Assume current if COM not available
        try:
            on_current = ctypes.c_bool(False)
            self._manager.IsWindowOnCurrentVirtualDesktop(
                hwnd, ctypes.byref(on_current))
            return on_current.value
        except Exception:
            return True

    def move_to_current_desktop(self, hwnd):
        """Move a window from another virtual desktop to the current one.

        Returns True on success, False on failure.
        """
        if not self._available:
            return False
        if not self._ensure_current_desktop_id():
            logger.debug("Cannot determine current desktop GUID")
            return False
        try:
            self._manager.MoveWindowToDesktop(
                hwnd, ctypes.byref(self._current_desktop_id))
            logger.debug(f"Moved hwnd {hwnd} to current desktop")
            return True
        except Exception as e:
            logger.debug(f"Failed to move hwnd {hwnd} to current desktop: {e}")
            return False


# Window classes that should always be excluded (system/shell windows)
SYSTEM_CLASSES = {
    'Progman',                      # Desktop (Program Manager)
    'Shell_TrayWnd',                # Taskbar
    'Shell_SecondaryTrayWnd',       # Secondary monitor taskbar
    'NotifyIconOverflowWindow',     # Tray icon overflow
    'Windows.UI.Core.CoreWindow',   # Start Menu, Action Center, etc.
    'WorkerW',                      # Desktop worker windows
    'DV2ControlHost',               # Start menu host
    'SHELLDLL_DefView',             # Desktop shell view
    'tooltips_class32',             # Tooltip windows
    'IME',                          # Input Method Editor
    'MSCTFIME UI',                  # Text input framework
    'EdgeUiInputTopWndClass',       # Edge UI input
    'EdgeUiInputWndClass',          # Edge UI input
}

# DWM constants for cloaked window detection
DWMWA_CLOAKED = 14
DWM_CLOAKED_APP = 1
DWM_CLOAKED_SHELL = 2
DWM_CLOAKED_INHERITED = 4

# ShowWindow constants
SW_RESTORE = 9
SW_SHOW = 5
SW_SHOWNOACTIVATE = 4


# Minimum sane window size -- windows smaller than this get restored
# to a reasonable default before centering
MIN_SANE_WIDTH = 200
MIN_SANE_HEIGHT = 100
DEFAULT_RESTORE_WIDTH = 800
DEFAULT_RESTORE_HEIGHT = 600


class WindowsPlatform(PlatformBase):

    def __init__(self):
        self._own_pid = os.getpid()
        self._vd_helper = None  # Lazy-init virtual desktop helper

    @property
    def vd_helper(self):
        """Lazy-initialized virtual desktop helper."""
        if self._vd_helper is None:
            try:
                self._vd_helper = VirtualDesktopHelper()
            except Exception as e:
                logger.debug(f"Virtual desktop helper init failed: {e}")
                self._vd_helper = VirtualDesktopHelper.__new__(VirtualDesktopHelper)
                self._vd_helper._available = False
        return self._vd_helper

    def setup(self):
        """Set DPI awareness for accurate window coordinates."""
        try:
            # Per-Monitor DPI Aware V2 (best option, Win10 1703+)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(
                ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            )
            logger.debug("Set DPI awareness: Per-Monitor V2")
        except (AttributeError, OSError):
            try:
                # Per-Monitor DPI Aware (Win8.1+)
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                logger.debug("Set DPI awareness: Per-Monitor V1")
            except (AttributeError, OSError):
                logger.debug("Could not set DPI awareness (older Windows?)")

    def is_elevated(self):
        """Check if running as Administrator."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def get_primary_monitor_work_area(self):
        """Return (x, y, width, height) of the primary monitor work area."""
        _load_win32()
        # SystemParametersInfo with SPI_GETWORKAREA returns primary monitor work area
        # But using EnumDisplayMonitors is more reliable for multi-monitor
        monitors = self._get_all_monitors()
        for mon in monitors:
            if mon.get('primary', False):
                wa = mon['work_area']
                return (wa[0], wa[1], wa[2] - wa[0], wa[3] - wa[1])
        # Fallback: use the first monitor
        if monitors:
            wa = monitors[0]['work_area']
            return (wa[0], wa[1], wa[2] - wa[0], wa[3] - wa[1])
        # Last resort: GetSystemMetrics
        w = win32api.GetSystemMetrics(0)  # SM_CXSCREEN
        h = win32api.GetSystemMetrics(1)  # SM_CYSCREEN
        return (0, 0, w, h)

    def get_monitor_work_area(self, monitor_index):
        """Return (x, y, width, height) for a specific monitor."""
        monitors = self._get_all_monitors()
        if monitor_index < len(monitors):
            wa = monitors[monitor_index]['work_area']
            return (wa[0], wa[1], wa[2] - wa[0], wa[3] - wa[1])
        return self.get_primary_monitor_work_area()

    def _get_all_monitors(self):
        """Enumerate all monitors and their work areas."""
        _load_win32()
        monitors = []
        # pywin32 EnumDisplayMonitors returns list of (hMonitor, hdcMonitor, rect)
        for hmonitor, _hdc, _rect in win32api.EnumDisplayMonitors(None, None):
            info = win32api.GetMonitorInfo(hmonitor)
            monitors.append({
                'handle': hmonitor,
                'area': info['Monitor'],       # (left, top, right, bottom)
                'work_area': info['Work'],      # excludes taskbar
                'primary': info['Flags'] & 1,   # MONITORINFOF_PRIMARY
            })
        return monitors

    def enumerate_windows(self, include_hidden=False):
        """Enumerate all top-level windows, returning WindowInfo list."""
        _load_win32()
        windows = []
        monitors = self._get_all_monitors()

        def enum_callback(hwnd, _):
            try:
                wi = self._inspect_window(hwnd, monitors, include_hidden)
                if wi is not None:
                    windows.append(wi)
            except Exception as e:
                logger.debug(f"Error inspecting hwnd {hwnd}: {e}")
            return True

        win32gui.EnumWindows(enum_callback, None)
        return windows

    def _inspect_window(self, hwnd, monitors, include_hidden):
        """Inspect a single window and return WindowInfo or None if filtered."""
        # Get class name first for fast filtering
        try:
            class_name = win32gui.GetClassName(hwnd)
        except Exception:
            return None

        if class_name in SYSTEM_CLASSES:
            return None

        # Get window style
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)

        # Skip child windows (should have a parent)
        if style & win32con.WS_CHILD:
            return None

        # Skip tool windows unless they have a title
        title = win32gui.GetWindowText(hwnd)
        if (ex_style & win32con.WS_EX_TOOLWINDOW) and not title:
            return None

        # Check visibility
        is_visible = win32gui.IsWindowVisible(hwnd)

        # Check cloaked state (virtual desktop windows, suspended UWP apps, etc.)
        cloaked_value = self._get_cloaked_state(hwnd)
        is_cloaked = cloaked_value != 0

        # Determine if window should be included
        if not is_visible and not include_hidden:
            # Still include minimized windows (they're "not visible" but user wants them)
            if not (style & win32con.WS_MINIMIZE):
                return None

        # Skip windows with no title and not visible (background system windows)
        if not title and not is_visible:
            return None

        # Skip our own process
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return None

        if pid == self._own_pid:
            return None

        # Get process name
        process_name = self._get_process_name(pid)

        # Get window rect
        try:
            rect = win32gui.GetWindowRect(hwnd)
            x, y, right, bottom = rect
            width = right - x
            height = bottom - y
        except Exception:
            x, y, width, height = 0, 0, 0, 0

        # Determine state
        is_off_screen = self._is_off_screen(x, y, width, height, monitors)
        if style & win32con.WS_MINIMIZE:
            state = 'minimized'
        elif not is_visible:
            state = 'hidden'
        elif is_cloaked:
            state = 'cloaked'
        elif is_off_screen:
            state = 'off-screen'
        elif style & win32con.WS_MAXIMIZE:
            state = 'maximized'
        else:
            state = 'normal'

        wi = WindowInfo(
            handle=hwnd,
            title=title or f"<{class_name}>",
            class_name=class_name,
            process_name=process_name,
            pid=pid,
            x=x, y=y,
            width=width, height=height,
            state=state,
            is_visible=is_visible,
        )
        wi.exe_path = self._get_process_exe_path(pid)
        wi.cloaked_type = cloaked_value
        wi.is_off_screen = is_off_screen
        return wi

    def _get_cloaked_state(self, hwnd):
        """Return the DWM cloaked value for a window.

        Returns 0 if not cloaked, or a bitmask:
          1 (DWM_CLOAKED_APP)       - cloaked by the app itself
          2 (DWM_CLOAKED_SHELL)     - cloaked by the shell/OS (e.g., suspended UWP)
          4 (DWM_CLOAKED_INHERITED) - inherited from an ancestor
        """
        try:
            cloaked = ctypes.c_int(0)
            ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd, DWMWA_CLOAKED,
                ctypes.byref(cloaked), ctypes.sizeof(cloaked)
            )
            return cloaked.value
        except Exception:
            return 0

    def _is_off_screen(self, x, y, width, height, monitors):
        """Check if window rect doesn't intersect any monitor."""
        if width <= 0 or height <= 0:
            return True
        for mon in monitors:
            ma = mon['area']  # (left, top, right, bottom)
            # Check intersection
            if (x < ma[2] and x + width > ma[0] and
                    y < ma[3] and y + height > ma[1]):
                return False
        return True

    def _get_process_name(self, pid):
        """Get process name from PID."""
        _load_win32()
        try:
            proc = psutil.Process(pid)
            return proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return f"<pid:{pid}>"

    def _get_process_exe_path(self, pid):
        """Get full executable path from PID. Returns None on failure."""
        _load_win32()
        try:
            proc = psutil.Process(pid)
            return proc.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def restore_window(self, window_info):
        """Restore a minimized window to normal state."""
        _load_win32()
        try:
            win32gui.ShowWindow(window_info.handle, SW_RESTORE)
            return True
        except Exception as e:
            logger.debug(f"Failed to restore {window_info.handle}: {e}")
            return False

    def show_window(self, window_info):
        """Make a hidden window visible."""
        _load_win32()
        try:
            win32gui.ShowWindow(window_info.handle, SW_SHOW)
            return True
        except Exception as e:
            logger.debug(f"Failed to show {window_info.handle}: {e}")
            return False

    def hide_window(self, window_info):
        """Hide a visible window (reverse of show_window)."""
        _load_win32()
        try:
            win32gui.ShowWindow(window_info.handle, win32con.SW_HIDE)
            return True
        except Exception as e:
            logger.debug(f"Failed to hide {window_info.handle}: {e}")
            return False

    def move_from_virtual_desktop(self, window_info):
        """Move a cloaked window from another virtual desktop to the current one."""
        if not self.vd_helper.available:
            logger.debug("Virtual desktop API not available")
            return False
        return self.vd_helper.move_to_current_desktop(window_info.handle)

    def center_window(self, window_info, target_x, target_y, area_width, area_height,
                      offset_x=0, offset_y=0):
        """Move window to be centered within the given area.

        Handles edge cases:
        - Minimized windows: restores first to get real size
        - Collapsed/tiny windows (hidden by shrinking): restores to sane default
        - Oversized windows: clamped to fit within the target area

        offset_x, offset_y: cascade offset from dead center for visual separation.
        Positions are clamped to the monitor work area.
        """
        _load_win32()
        try:
            # For minimized windows, restore first to get their real size
            style = win32gui.GetWindowLong(window_info.handle, win32con.GWL_STYLE)
            if style & win32con.WS_MINIMIZE:
                win32gui.ShowWindow(window_info.handle, SW_RESTORE)
                import time
                time.sleep(0.05)  # Brief pause for restore to take effect

            # Get current window size (post-restore)
            rect = win32gui.GetWindowRect(window_info.handle)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]

            # Handle collapsed/tiny windows -- apps that "hide" by shrinking
            # to near-zero size. Restore to a sane default so the user can
            # actually see and interact with the window.
            if w < MIN_SANE_WIDTH or h < MIN_SANE_HEIGHT:
                logger.debug(
                    f"Window {window_info.handle} is tiny ({w}x{h}), "
                    f"restoring to {DEFAULT_RESTORE_WIDTH}x{DEFAULT_RESTORE_HEIGHT}"
                )
                w = DEFAULT_RESTORE_WIDTH
                h = DEFAULT_RESTORE_HEIGHT

            # Clamp window size to fit within the target area
            if w > area_width:
                w = area_width
            if h > area_height:
                h = area_height

            # Calculate centered position with cascade offset
            cx = target_x + (area_width - w) // 2 + offset_x
            cy = target_y + (area_height - h) // 2 + offset_y

            # Clamp to work area bounds
            cx = max(target_x, min(cx, target_x + area_width - w))
            cy = max(target_y, min(cy, target_y + area_height - h))

            z_order = win32con.HWND_TOP
            win32gui.SetWindowPos(
                window_info.handle,
                z_order,
                cx, cy, w, h,
                win32con.SWP_SHOWWINDOW
            )
            return True
        except Exception as e:
            logger.debug(f"Failed to center {window_info.handle}: {e}")
            return False

    def bring_to_front(self, window_info):
        """Bring window to front using AttachThreadInput workaround."""
        _load_win32()
        try:
            fg_hwnd = win32gui.GetForegroundWindow()
            if fg_hwnd == window_info.handle:
                return True

            fg_thread = win32process.GetWindowThreadProcessId(fg_hwnd)[0]
            target_thread = win32process.GetWindowThreadProcessId(window_info.handle)[0]

            attached = False
            if fg_thread != target_thread:
                try:
                    win32process.AttachThreadInput(fg_thread, target_thread, True)
                    attached = True
                except Exception:
                    pass

            try:
                win32gui.SetForegroundWindow(window_info.handle)
                win32gui.BringWindowToTop(window_info.handle)
            except Exception:
                # Fallback: just try BringWindowToTop
                try:
                    win32gui.BringWindowToTop(window_info.handle)
                except Exception:
                    pass

            if attached:
                try:
                    win32process.AttachThreadInput(fg_thread, target_thread, False)
                except Exception:
                    pass

            return True
        except Exception as e:
            logger.debug(f"Failed to bring to front {window_info.handle}: {e}")
            return False
