"""
Version information for wingather.

This file is the canonical source for version numbers.
The __version__ string is automatically updated by git hooks
with build metadata (branch, build number, date, commit hash).

Format: MAJOR.MINOR.PATCH[-PHASE]_BRANCH_BUILD-YYYYMMDD-COMMITHASH
Example: 0.1.0_main_4-20260211-a1b2c3d4

To manually update: ./scripts/update-version.sh
To bump version: edit MAJOR, MINOR, PATCH below
"""

# Version components - edit these for version bumps
MAJOR = 0
MINOR = 1
PATCH = 1
PHASE = None  # Options: None, "alpha", "beta", "rc1", etc.

# Auto-updated by git hooks - do not edit manually
__version__ = "0.1.1_main_6-20260212-da18e819"
__app_name__ = "wingather"
