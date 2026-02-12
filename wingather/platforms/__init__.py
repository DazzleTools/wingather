"""Platform-specific window management implementations."""

import sys


def get_platform():
    """Return the appropriate platform implementation for the current OS."""
    if sys.platform == "win32":
        from wingather.platforms.windows import WindowsPlatform
        return WindowsPlatform()
    elif sys.platform == "darwin":
        from wingather.platforms.macos import MacOSPlatform
        return MacOSPlatform()
    elif sys.platform.startswith("linux"):
        from wingather.platforms.linux import LinuxPlatform
        return LinuxPlatform()
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
