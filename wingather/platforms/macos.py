"""macOS implementation stub for window management.

Future implementation would use:
- PyObjC (AppKit, Quartz/CoreGraphics)
- CGWindowListCopyWindowInfo for enumeration
- Accessibility API (AXUIElement) for manipulation
- NSWorkspace for process info
"""

from wingather.platforms.base import PlatformBase


class MacOSPlatform(PlatformBase):

    def setup(self):
        pass

    def is_elevated(self):
        import os
        return os.geteuid() == 0

    def get_primary_monitor_work_area(self):
        raise NotImplementedError("macOS support not yet implemented")

    def get_monitor_work_area(self, monitor_index):
        raise NotImplementedError("macOS support not yet implemented")

    def enumerate_windows(self, include_hidden=False):
        raise NotImplementedError("macOS support not yet implemented")

    def restore_window(self, window_info):
        raise NotImplementedError("macOS support not yet implemented")

    def show_window(self, window_info):
        raise NotImplementedError("macOS support not yet implemented")

    def center_window(self, window_info, target_x, target_y, area_width, area_height):
        raise NotImplementedError("macOS support not yet implemented")

    def bring_to_front(self, window_info):
        raise NotImplementedError("macOS support not yet implemented")
