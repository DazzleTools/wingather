"""Abstract base class for platform-specific window management."""

from abc import ABC, abstractmethod


class WindowInfo:
    """Represents a discovered window."""

    def __init__(self, handle, title, class_name, process_name, pid,
                 x, y, width, height, state, is_visible):
        self.handle = handle
        self.title = title
        self.class_name = class_name
        self.process_name = process_name
        self.pid = pid
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.state = state          # 'normal', 'minimized', 'maximized', 'hidden', 'off-screen'
        self.is_visible = is_visible
        self.exe_path = None         # Full path to the executable (resolved from PID)
        self.action_taken = None     # Filled in after processing
        self.target_x = None         # Where it would/will be moved (for dry-run reporting)
        self.target_y = None
        self.cloaked_type = 0        # DWM cloak value: 0=none, 1=app, 2=shell, 4=inherited
        self.is_off_screen = False   # True if position doesn't intersect any monitor
        self.suspicious = False      # Flagged if off-screen, heavily shrunk, or otherwise questionable
        self.suspicious_reason = None
        self.concern_level = 0       # 0=none, 1=highest(DEFCON 1), 5=lowest(informational)
        self.concern_score = 0       # Raw score from accumulated indicators
        self.trusted = False         # True if process matched trust list (flagging suppressed)
        self.trust_source = None     # 'default' or 'user'
        self.trust_pattern = None    # The pattern that matched
        self.trust_verified = None   # Verification method if validated (e.g., 'microsoft')
        self.would_flag_reason = None   # What would have been flagged if not trusted
        self.would_concern_level = 0
        self.would_concern_score = 0

    def __repr__(self):
        return (f"WindowInfo(title={self.title!r}, process={self.process_name}, "
                f"pid={self.pid}, state={self.state})")


class PlatformBase(ABC):
    """Abstract interface for platform-specific window operations."""

    @abstractmethod
    def setup(self):
        """Platform-specific initialization (e.g., DPI awareness)."""
        pass

    @abstractmethod
    def is_elevated(self):
        """Check if running with elevated/admin privileges."""
        pass

    @abstractmethod
    def get_primary_monitor_work_area(self):
        """Return (x, y, width, height) of the primary monitor work area."""
        pass

    @abstractmethod
    def get_monitor_work_area(self, monitor_index):
        """Return (x, y, width, height) for a specific monitor's work area."""
        pass

    @abstractmethod
    def enumerate_windows(self, include_hidden=False):
        """Enumerate all top-level windows. Returns list of WindowInfo."""
        pass

    @abstractmethod
    def restore_window(self, window_info):
        """Restore a minimized/maximized window to normal state."""
        pass

    @abstractmethod
    def show_window(self, window_info):
        """Make a hidden window visible."""
        pass

    @abstractmethod
    def center_window(self, window_info, target_x, target_y, area_width, area_height,
                      topmost=False):
        """Move window to be centered within the given area.

        If topmost=True, place at HWND_TOPMOST z-order (for suspicious windows).
        """
        pass

    @abstractmethod
    def bring_to_front(self, window_info):
        """Bring window to the foreground / top of Z-order."""
        pass

    def hide_window(self, window_info):
        """Hide a visible window (reverse of show_window).

        Returns True on success, False if not supported or failed.
        Default implementation returns False (not supported).
        """
        return False

    def move_from_virtual_desktop(self, window_info):
        """Move a window from another virtual desktop to the current one.

        Returns True on success, False if not supported or failed.
        Default implementation returns False (not supported).
        """
        return False
