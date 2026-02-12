# wingather — CLI Parameters

## Modes

### `--list-only`, `-l`

List all discovered windows without taking any action. No windows are moved, restored, or modified. The output table shows `--` in the ACTION column.

Useful for surveying what's running before deciding what to do.

```bash
wingather --list-only
wingather -l
```

### `--dry-run`, `-n`

Simulate the full gather operation without actually moving anything. Computes target positions, applies concern scoring, and shows exactly what _would_ happen. The output table includes CURRENT POS and TARGET POS columns.

This is the recommended first step when investigating suspicious windows.

```bash
wingather --dry-run
wingather -n -v          # with verbose logging
```

### `--version`

Print the version string and exit.

```bash
wingather --version
```

## Window Selection

### `--show-hidden`

Also reveal windows that have the `WS_VISIBLE` style flag unset. These are windows that have been explicitly hidden by the OS or applications for background communication, rendering, and system services.

**Use with caution** — a typical desktop has 50-100+ hidden windows, and the vast majority are normal operating system internals (DDE servers, GDI+ surfaces, .NET event handlers, tray icon message pumps). Revealing them will clutter your desktop with non-interactive phantom windows. Use `--undo` to reverse.

Always preview with `--dry-run` first:

```bash
wingather --show-hidden --dry-run    # preview what would be revealed
wingather --show-hidden              # reveal (state saved for --undo)
```

See [hidden-windows.md](hidden-windows.md) for a detailed guide to what these windows are and when they deserve attention.

### `--undo`

Re-hide windows that were revealed by a previous `--show-hidden` run. Reads the saved state file, validates that each window handle still belongs to the same process (prevents hiding the wrong window after handle reuse), and calls `ShowWindow(SW_HIDE)` on each.

```bash
wingather --undo
```

State is saved automatically to `%LOCALAPPDATA%\wingather\last_shown.json` after each non-dry-run `--show-hidden`. The state file is deleted after a successful undo.

### `--include-virtual`

Pull windows from other virtual desktops to the current one. By default, cloaked windows on other virtual desktops are skipped because the OS prevents moving them across desktops without switching.

```bash
wingather --include-virtual
```

### `--filter`, `-f` _PATTERN_

Only affect windows whose title or process name matches the given pattern. Uses Python's `fnmatch` (shell-style wildcards: `*`, `?`, `[seq]`).

```bash
wingather -f "*chrome*"           # only Chrome windows
wingather -f "notepad*" --dry-run # only Notepad
```

### `--exclude`, `-x` _PATTERN_

Exclude windows whose title or process name matches the given pattern. Inverse of `--filter`. Uses `fnmatch`.

```bash
wingather -x "*spotify*"     # gather everything except Spotify
```

### `--exclude-process`, `-xp` _NAME_

Exclude windows by process name. Repeatable. Uses `fnmatch` patterns. More precise than `--exclude` because it only matches the process name, not the window title.

```bash
wingather -xp notepad.exe -xp calc.exe
wingather -xp "chrome*"                   # all Chrome processes
```

### `--exclude-file` _PATH_

File containing process names to exclude, one per line. Lines starting with `#` are treated as comments. Blank lines are ignored.

```bash
wingather --exclude-file my_excludes.txt
```

Example file:
```
# Processes to skip
notepad.exe
calc.exe
chrome*
```

## Monitor Targeting

### `--monitor`, `-m` _INDEX_

Monitor index to center windows on. `0` is the primary monitor (default), `1` is the first secondary monitor, etc.

```bash
wingather -m 1        # center on secondary monitor
wingather -m 0        # center on primary (default)
```

## Trust System

### `--trust`, `-tp` _NAME_

Trust a process name pattern — suppress suspicious flagging for matching windows. Trusted windows are still gathered/moved normally, but they won't receive `[!N]` concern flags or TOPMOST z-order treatment.

Repeatable. Uses `fnmatch` patterns. These are **name-only** matches (no path or signature verification, unlike the built-in defaults).

```bash
wingather -tp xntimer.exe -tp "myapp*"
```

### `--trust-file` _PATH_

File containing trusted process name patterns, one per line. Same format as `--exclude-file` (comments with `#`, blank lines ignored).

```bash
wingather --trust-file my_trusted.txt
```

### `--no-default-trust`

Bypass the built-in default trust list. By default, wingather ships with a trust list of common Windows processes (explorer.exe, ApplicationFrameHost.exe, etc.) that are verified via path + Authenticode signature before suppressing flags.

With this flag, _all_ windows are evaluated for suspicious indicators — nothing is suppressed by default. User-provided `-tp` patterns still apply.

```bash
wingather --no-default-trust --dry-run   # flag everything
```

## Output

### `--json`

Output results as JSON instead of the table format. Includes all window metadata, concern levels, trust status, and position data. Useful for scripting and integration with other tools.

```bash
wingather --json --dry-run
wingather --json --dry-run | python -m json.tool    # pretty-print
```

### `--verbose`, `-v`

Enable verbose logging. Shows debug-level messages including window enumeration details, trust matching decisions, and signature verification results.

```bash
wingather -v --dry-run
```

## Concern Levels

Windows are scored using weighted indicators. The total score maps to a DEFCON-style concern level:

| Score | Level | Label | TOPMOST |
|-------|-------|-------|---------|
| 5+    | 1     | ALERT   | Yes |
| 4     | 2     | ALERT   | Yes |
| 3     | 3     | CONCERN | Yes |
| 2     | 4     | NOTE    | No  |
| 1     | 5     | NOTE    | No  |

### Indicator Weights

| Indicator | Weight | Description |
|-----------|--------|-------------|
| `trust-verification-failed` | 5 | Process name matches trusted entry but path or signature verification failed |
| `off-screen` | 4 | Window position is completely outside all monitor bounds |
| `shrunk` | 3 | Window is smaller than 200x100 pixels (not minimized) |
| `dialog` | 2 | Window class is `#32770` (standard Windows dialog) |
| `partially-off-screen` | 2 | Window is pushed mostly past a screen edge |
| `cloaked` | 1 | Window is cloaked (another virtual desktop or OS-managed) |
| `shell-cloaked` | 1 | Bonus: cloaking is shell/inherited type (OS hid it, not user action) |

Indicators are additive. A window that is off-screen (4) and a dialog (2) scores 6, which is level 1 ALERT.

## Default Trust List

wingather ships with a built-in trust list of common Windows processes. Each entry is verified before suppressing flags:

1. **Name match** — process name matches the pattern (fnmatch)
2. **Path validation** — executable path matches expected locations
3. **Signature check** — Microsoft Authenticode signature via `IsOSBinary`

If any verification step fails, the window is _not_ trusted and instead receives a `trust-verification-failed` indicator (weight 5 = instant level 1 ALERT). This catches processes masquerading as system binaries.

The trust summary at the end of output shows which windows were suppressed and how they were verified:

```
Trusted (flagging suppressed): 4 window(s)
    explorer.exe             would be [!5] NOTE: cloaked  [default, MS-signed]
    ShellExperienceHost.exe  would be [!5] NOTE: cloaked  [default, MS-signed]
```

See `wingather/default_trust.json` for the full list.
