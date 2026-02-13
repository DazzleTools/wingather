# Changelog

All notable changes to wingather will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). Versions follow [Semantic Versioning](https://semver.org/).

## [0.2.2-alpha] - 2026-02-13

### Fixed
- **Package data missing from pip install**: `default_trust.json` and `lolbins.json` were not included in the wheel, causing trust verification and auto-trust features to silently fail on pip-installed copies. Added `[tool.setuptools.package-data]` to `pyproject.toml`.

## [0.2.1-alpha] - 2026-02-12

### Changed
- **Default mode**: wingather now only acts on suspicious windows by default. Normal, non-suspicious windows are skipped (`skip:normal`). Use `--all` / `-a` to restore the previous "gather everything" behavior.
- `--show-hidden` now only reveals hidden windows with concern indicators (dialog class, trust failure) by default. Use `--show-hidden --all` to reveal all hidden windows.
- `--filter` overrides the suspicious-only restriction — explicitly targeted windows are always acted on.

### Added
- `--all` / `-a` flag to opt-in to gathering all windows (previous default behavior)
- Educational banner when `--show-hidden` is used, explaining what hidden windows are and referencing `docs/hidden-windows.md`
- Auto-trust for Microsoft-signed OS binaries: suspicious windows with valid Authenticode signatures are automatically trusted (no manual whitelist entry needed)
- LOLBin exclusion list (`lolbins.json`): ~44 Microsoft-signed binaries known as attack vectors (cmd, powershell, mshta, rundll32, etc.) are excluded from auto-trust. Source: [LOLBAS Project](https://lolbas-project.github.io/)
- `wmplayer.exe` added to default trust list with signature verification (compact mini-mode triggers false positive on `shrunk` indicator)
- All suspicious windows are now brought to foreground (`bring_to_front`) regardless of concern level. Levels 1-3 still get TOPMOST (sticky). Levels 4-5 get a one-time z-order raise so the user actually sees them.

## [0.2.0-alpha] - 2026-02-12

### Added
- `--undo` flag to reverse `--show-hidden` by re-hiding previously revealed windows
- State file (`last_shown.json`) auto-saved after `--show-hidden` runs for undo support
- `hide_window()` platform method (Windows implementation via `ShowWindow(SW_HIDE)`)
- HWND + PID cross-validation on undo to prevent hiding wrong windows after handle reuse
- Graceful skip of stale entries (closed windows, PID mismatches) during undo
- `docs/hidden-windows.md` — guide to hidden window types (DDE, GDI+, .NET event handlers, tray icons, GPU drivers, shell internals) so users understand what `--show-hidden` reveals
- `PROJECT_PHASE` version field — dual-level maturity signaling: project-wide phase (prealpha/alpha/beta/stable) independent of per-MINOR feature phase
- `--version` now shows both levels: `wingather PREALPHA 0.2.0-alpha (build string)`

## [0.1.3-alpha] - 2026-02-12

### Changed
- Release workflow: switch from API token secrets to OIDC trusted publishers for PyPI and Test PyPI publishing (more secure, no token management needed)

## [0.1.2-alpha] - 2026-02-12

### Fixed
- CI build failure: switch from internal `setuptools.backends._legacy:_Backend` to standard `setuptools.build_meta` backend for compatibility with Python 3.9/3.10 on GitHub Actions runners
- CI build failure: `setup.py` imported from package during install (chicken-and-egg); now uses `exec()` pattern from preserve
- PEP 440 version compliance: full build metadata version string rejected by `packaging.version`; added `get_pip_version()` to produce compliant versions (e.g., `0.1.2a0`)
- Upgrade `setuptools` and `wheel` in CI install step

### Added
- `_version.py`: `get_version()`, `get_base_version()`, `get_pip_version()` helpers and `VERSION`, `BASE_VERSION`, `PIP_VERSION` constants (aligned with preserve's version.py pattern)
- CHANGELOG.md
- ROADMAP.md with 1.0 and cross-platform milestones

## [0.1.1-alpha] - 2026-02-12

### Added
- Unit tests: 65 tests covering concern scoring, trust matching, CLI parsing, and table rendering
- `docs/parameters.md` — full CLI reference with all options, filtering, trust configuration, concern levels, and indicator weights
- `docs/platform-support.md` — platform status, per-platform requirements, architecture overview, and contribution guidance
- README badges: PyPI, release date, Python version, license, discussions, combined platform badge
- README sections: suspicious window detection with concern level table, trust verification with examples
- Doc links from README to detailed parameter and platform references

### Changed
- README install section updated with PyPI line
- README license section updated with copyright

## [0.1.0-alpha] - 2026-02-12

### Added
- Win32 window enumeration via `EnumWindows` with DPI awareness
- Window state detection: normal, minimized, hidden, off-screen, cloaked
- Restore, show, and center windows on target monitor work area
- DWM cloaking analysis (app/shell/inherited) for virtual desktop detection
- Virtual desktop support via `IVirtualDesktopManager` COM interface
- DEFCON-style concern levels 1-5 with weighted scoring system
- Indicators: off-screen (4), shrunk (3), dialog (2), partially-off-screen (2), cloaked (1)
- Dialog class detection (`#32770` Windows standard dialog)
- TOPMOST z-order for concern levels 1-3
- Trust verification: default trust list with path validation + Authenticode signature check
- `trust-verification-failed` indicator (weight 5) for masquerading processes
- User trust patterns via `--trust`/`-tp` and `--trust-file`
- `--no-default-trust` to bypass built-in defaults
- Process filtering: `--filter`, `--exclude`, `--exclude-process`, `--exclude-file`
- Monitor targeting with `--monitor`
- Dry-run mode with target position calculation
- List-only mode for surveying windows
- `--show-hidden` for explicitly hidden windows
- `--include-virtual` for cross-desktop window pulling
- JSON output for scripting
- Column-position table rendering with overflow wrapping
- Help text with usage examples and concern level reference
- Platform abstraction layer with macOS and Linux stubs
- GitHub Actions CI (Windows, Python 3.9-3.12) and release workflow
- GPL-3.0 license
