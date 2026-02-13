"""Core orchestration logic for wingather (platform-agnostic)."""

import datetime
import fnmatch
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from wingather.platforms import get_platform

logger = logging.getLogger(__name__)

# Minimum sane size for dry-run position estimation (mirrors windows.py)
MIN_SANE_WIDTH = 200
MIN_SANE_HEIGHT = 100
DEFAULT_RESTORE_WIDTH = 800
DEFAULT_RESTORE_HEIGHT = 600

# Window classes that indicate a dialog/popup -- these are transient by nature
# and a persistent one sitting around is worth flagging for the user's attention.
DIALOG_CLASSES = {
    '#32770',   # Standard Windows dialog (MessageBox, ShellExecute errors, etc.)
}

# Concern scoring: each indicator adds points. Total maps to a DEFCON-style
# level (1 = highest concern, 5 = lowest/informational).
#
# Score → Level:  5+ → 1,  4 → 2,  3 → 3,  2 → 4,  1 → 5
CONCERN_WEIGHTS = {
    'off-screen':                4,  # completely invisible to the user
    'shrunk':                    3,  # deliberately tiny, hiding in plain sight
    'dialog':                    2,  # transient popup persisting unexpectedly
    'partially-off-screen':      2,  # pushed partly out of view
    'cloaked':                   1,  # on another desktop or OS-managed
    'shell-cloaked':             1,  # bonus: OS hid it (not user action)
    'trust-verification-failed': 5,  # masquerading as a trusted process name
}

# Cascade positioning: offset suspicious windows around screen center so
# multiple flagged windows are all visible simultaneously.
# Index 0 = dead center (reserved for highest priority), then outward.
CASCADE_RADIUS = 60  # pixels from center per offset step

_CASCADE_DIRECTIONS = [
    (0, 0),       # center (highest priority)
    (-1, -1),     # top-left
    (1, -1),      # top-right
    (-1, 1),      # bottom-left
    (1, 1),       # bottom-right
    (0, -1),      # top
    (-1, 0),      # left
    (1, 0),       # right
    (0, 1),       # bottom
]


def _compute_cascade_offsets(count):
    """Compute (offset_x, offset_y) for each position in a cascade.

    Returns list indexed from 0 (center/highest priority) to count-1 (outermost).
    Positions 0-8 use fixed cardinal/diagonal directions.
    Positions 9+ use a ring-based fallback at increasing radius.
    """
    if count <= 0:
        return []
    offsets = []
    for i in range(count):
        if i < len(_CASCADE_DIRECTIONS):
            dx, dy = _CASCADE_DIRECTIONS[i]
            offsets.append((dx * CASCADE_RADIUS, dy * CASCADE_RADIUS))
        else:
            import math
            ring = (i - len(_CASCADE_DIRECTIONS)) // 8 + 2
            pos_in_ring = (i - len(_CASCADE_DIRECTIONS)) % 8
            angle = pos_in_ring * (math.pi / 4)
            radius = CASCADE_RADIUS * ring
            offsets.append((int(radius * math.cos(angle)),
                           int(radius * math.sin(angle))))
    return offsets


def gather_windows(list_only=False, dry_run=False, show_hidden=False,
                   include_virtual=False, monitor_index=0,
                   filter_pattern=None, exclude_pattern=None,
                   exclude_processes=None, trusted_processes=None,
                   no_default_trust=False, gather_all=False):
    """
    Main entry point: enumerate windows, optionally restore/show/center them.

    Modes:
      list_only:         Just enumerate, no action simulation
      dry_run:           Simulate full logic, compute targets, don't move anything
      (neither):         Actually perform the operations
      include_virtual:   Also pull windows from other virtual desktops
      exclude_processes: List of process name patterns to exclude (fnmatch)
      trusted_processes: List of process name patterns to whitelist from suspicious
                         flagging (fnmatch). These windows still get processed
                         normally but won't be flagged [!].
      no_default_trust:  If True, skip the built-in default trust list. User-provided
                         -tp patterns still apply.
      gather_all:        If True, act on ALL windows (original behavior). If False
                         (default), only act on suspicious windows. --filter
                         overrides this restriction.
    """
    platform = get_platform()
    platform.setup()

    # Warn about elevation
    if not platform.is_elevated():
        logger.warning(
            "Not running as Administrator. "
            "Elevated windows may not be movable."
        )

    # Get target monitor work area
    try:
        area_x, area_y, area_w, area_h = platform.get_monitor_work_area(monitor_index)
    except Exception:
        area_x, area_y, area_w, area_h = platform.get_primary_monitor_work_area()
    logger.debug(f"Target area: x={area_x}, y={area_y}, w={area_w}, h={area_h}")

    if dry_run:
        logger.info(f"Target monitor work area: ({area_x}, {area_y}) {area_w}x{area_h}")

    # Enumerate (always include hidden in enumeration if we want virtual desktops,
    # since cloaked windows may also be non-visible)
    windows = platform.enumerate_windows(include_hidden=show_hidden or include_virtual)
    logger.info(f"Found {len(windows)} window(s)")

    # Filter by title/process patterns
    if filter_pattern or exclude_pattern:
        windows = _apply_filters(windows, filter_pattern, exclude_pattern)
        logger.info(f"After pattern filtering: {len(windows)} window(s)")

    # Filter by process name exclusions
    if exclude_processes:
        before = len(windows)
        windows = _exclude_by_process(windows, exclude_processes)
        excluded = before - len(windows)
        if excluded:
            logger.info(f"Excluded {excluded} window(s) by process name")

    # Build trust entries: list of dicts with 'pattern', 'source', and
    # optional 'verify', 'expected_paths' for default trust verification.
    trust_entries = []
    if not no_default_trust:
        defaults = _load_default_trust()
        for entry in defaults:
            entry['source'] = 'default'
            trust_entries.append(entry)
        if defaults:
            logger.debug(f"Loaded {len(defaults)} default trust entry/entries")
    if trusted_processes:
        for p in trusted_processes:
            trust_entries.append({'pattern': p, 'source': 'user'})

    # For default entries that require verification, batch-verify signatures
    # up front so we only call PowerShell once.
    sig_cache = {}
    if trust_entries:
        verify_paths = set()
        for wi in windows:
            if wi.exe_path:
                for entry in trust_entries:
                    if entry.get('verify') and fnmatch.fnmatch(
                            wi.process_name.lower(), entry['pattern'].lower()):
                        verify_paths.add(wi.exe_path)
        if verify_paths:
            logger.debug(f"Verifying signatures for {len(verify_paths)} executable(s)")
            sig_cache = _verify_microsoft_signatures(list(verify_paths))

    # Flag suspicious windows (off-screen, collapsed, cloaked)
    _flag_suspicious(windows, trust_entries=trust_entries or None,
                     sig_cache=sig_cache)

    # Auto-trust: check if suspicious windows are Microsoft-signed OS binaries.
    # LOLBins (cmd, powershell, mshta, etc.) are excluded from auto-trust.
    if not no_default_trust:
        suspicious_paths = set()
        for wi in windows:
            if wi.suspicious and wi.exe_path:
                suspicious_paths.add(wi.exe_path)
        # Only verify paths not already in the cache
        new_paths = [p for p in suspicious_paths
                     if os.path.normcase(os.path.normpath(p)) not in sig_cache]
        if new_paths:
            logger.debug(f"Checking signatures for {len(new_paths)} suspicious executable(s)")
            new_sigs = _verify_microsoft_signatures(new_paths)
            sig_cache.update(new_sigs)
        lolbins = _load_lolbins()
        _auto_trust_microsoft(windows, sig_cache, lolbins)

    suspicious_count = sum(1 for w in windows if w.suspicious)
    trusted_count = sum(1 for w in windows if w.trusted)
    if suspicious_count:
        logger.info(f"Flagged {suspicious_count} suspicious window(s)")
    if trusted_count:
        logger.info(f"Trusted {trusted_count} window(s) (flagging suppressed)")

    if list_only:
        return windows

    # Split into suspicious and normal. Sort suspicious by concern_level
    # descending (level 5 first, level 1 last) so highest priority is
    # processed last and ends up on top of z-order.
    suspicious = sorted(
        [w for w in windows if w.suspicious],
        key=lambda w: w.concern_level, reverse=True)
    normal = [w for w in windows if not w.suspicious]

    # Compute cascade offsets: position 0 = center (highest priority),
    # outer positions = lower priority. Reverse so first-processed = outermost.
    cascade = _compute_cascade_offsets(len(suspicious))
    cascade.reverse()

    # Track windows that were hidden and get shown (for --undo support)
    shown_windows = []

    # Determine if we should process all windows or just suspicious ones.
    # --filter overrides the suspicious-only restriction (explicit user targeting).
    act_on_all = gather_all or filter_pattern is not None

    # Process normal windows first (no cascade offset)
    for wi in normal:
        if not act_on_all:
            # Default mode: skip non-suspicious windows
            wi.action_taken = 'skip:normal'
            continue
        if dry_run:
            _simulate_window(wi, area_x, area_y, area_w, area_h,
                             show_hidden, include_virtual)
        else:
            was_hidden = wi.state == 'hidden'
            _process_window(platform, wi, area_x, area_y, area_w, area_h,
                            show_hidden, include_virtual)
            if was_hidden and show_hidden and wi.action_taken and 'shown' in wi.action_taken:
                shown_windows.append(wi)

    # Process suspicious windows with cascade offsets.
    # Lowest concern first (outermost), highest concern last (center, on top).
    for i, wi in enumerate(suspicious):
        ox, oy = cascade[i] if i < len(cascade) else (0, 0)
        if dry_run:
            _simulate_window(wi, area_x, area_y, area_w, area_h,
                             show_hidden, include_virtual, act_on_all,
                             offset_x=ox, offset_y=oy)
        else:
            was_hidden = wi.state == 'hidden'
            _process_window(platform, wi, area_x, area_y, area_w, area_h,
                            show_hidden, include_virtual,
                            act_on_all=act_on_all, offset_x=ox, offset_y=oy)
            if was_hidden and show_hidden and wi.action_taken and 'shown' in wi.action_taken:
                shown_windows.append(wi)

    # Save state for --undo if we showed any hidden windows
    if shown_windows and not dry_run:
        save_shown_state(shown_windows)

    # Return sorted: highest concern first, then normal
    return list(reversed(suspicious)) + normal


def _score_to_level(score):
    """Map a raw concern score to a DEFCON-style level (1=highest, 5=lowest)."""
    if score >= 5:
        return 1
    if score >= 4:
        return 2
    if score >= 3:
        return 3
    if score >= 2:
        return 4
    return 5


def _load_default_trust():
    """Load default trusted process entries from the shipped JSON file.

    Returns list of dicts with at minimum 'pattern'. Entries may also have
    'verify', 'expected_paths', and 'reason' fields for verification.
    """
    trust_file = Path(__file__).parent / 'default_trust.json'
    try:
        with open(trust_file, 'r') as f:
            data = json.load(f)
        return data.get('processes', [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        logger.warning(f"Could not load default trust file: {trust_file}")
        return []


def _load_lolbins():
    """Load the LOLBin exclusion list (Microsoft-signed binaries to never auto-trust).

    Returns a set of lowercase process name patterns.
    """
    lolbin_file = Path(__file__).parent / 'lolbins.json'
    try:
        with open(lolbin_file, 'r') as f:
            data = json.load(f)
        return set(p.lower() for p in data.get('patterns', []))
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        logger.warning(f"Could not load LOLBin list: {lolbin_file}")
        return set()


def _auto_trust_microsoft(windows, sig_cache, lolbins):
    """Auto-trust suspicious windows whose executables are Microsoft-signed OS binaries.

    Skips windows matching the LOLBin exclusion list — those stay flagged.
    Converts suspicious windows to trusted with source='microsoft-signed'.
    """
    auto_trusted = 0
    for wi in windows:
        if not wi.suspicious or not wi.exe_path:
            continue

        # Check if this is a LOLBin (never auto-trust)
        if wi.process_name.lower() in lolbins:
            continue

        # Check signature cache
        norm_path = os.path.normcase(os.path.normpath(wi.exe_path))
        sig_info = sig_cache.get(norm_path)
        if not sig_info:
            continue

        if sig_info['valid'] and sig_info['is_os_binary']:
            # Convert from suspicious to trusted
            wi.trusted = True
            wi.trust_source = 'microsoft-signed'
            wi.trust_verified = 'microsoft'
            wi.would_flag_reason = wi.suspicious_reason
            wi.would_concern_score = wi.concern_score
            wi.would_concern_level = wi.concern_level
            wi.suspicious = False
            wi.suspicious_reason = None
            wi.concern_score = 0
            wi.concern_level = 0
            auto_trusted += 1

    if auto_trusted:
        logger.info(f"Auto-trusted {auto_trusted} Microsoft-signed window(s)")
    return auto_trusted


def _verify_exe_path(exe_path, expected_paths):
    """Check if an executable path matches any expected path pattern.

    Uses case-insensitive fnmatch to handle Windows path variations
    (e.g., SystemApps package hashes like _cw5n1h2txyewy).
    """
    if not exe_path:
        return False
    norm = os.path.normcase(os.path.normpath(exe_path))
    for expected in expected_paths:
        pattern = os.path.normcase(os.path.normpath(expected))
        if fnmatch.fnmatch(norm, pattern):
            return True
    return False


def _verify_microsoft_signatures(exe_paths):
    """Batch-verify Authenticode signatures for multiple executables.

    Uses a single PowerShell invocation to check all paths at once.
    Returns dict mapping path -> {'valid': bool, 'is_os_binary': bool, 'signer': str}.
    """
    if not exe_paths:
        return {}

    # Deduplicate and filter
    unique_paths = list(set(p for p in exe_paths if p))
    if not unique_paths:
        return {}

    # Build a PowerShell script that checks all paths in one invocation
    # Output format: path|Status|IsOSBinary|SignerSubject (one per line)
    lines = []
    for p in unique_paths:
        escaped = p.replace("'", "''")
        lines.append(
            f"$s = Get-AuthenticodeSignature '{escaped}'; "
            f"Write-Output ('{escaped}|' + $s.Status + '|' + $s.IsOSBinary + '|' + $s.SignerCertificate.Subject)"
        )
    script = '; '.join(lines)

    results = {}
    try:
        proc = subprocess.run(
            ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
             '-Command', script],
            capture_output=True, text=True, timeout=30,
        )
        for line in proc.stdout.strip().splitlines():
            parts = line.split('|', 3)
            if len(parts) >= 3:
                path = parts[0]
                status = parts[1].strip()
                is_os = parts[2].strip().lower() == 'true'
                signer = parts[3].strip() if len(parts) > 3 else ''
                results[os.path.normcase(os.path.normpath(path))] = {
                    'valid': status == 'Valid',
                    'is_os_binary': is_os,
                    'signer': signer,
                }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning(f"Signature verification failed: {e}")

    return results


def _flag_suspicious(windows, trust_entries=None, sig_cache=None):
    """Score windows for concern level using weighted indicators.

    Each indicator adds points. Total score maps to a DEFCON-style level
    (1 = highest concern, 5 = informational). Windows whose process name
    matches a trust entry (and passes verification if required) have flagging
    suppressed but the would-be concern info is recorded for reporting.

    trust_entries: list of dicts with 'pattern', 'source', and optional
                   'verify', 'expected_paths' fields.
    sig_cache:     dict from _verify_microsoft_signatures() for batch results.
    """
    sig_cache = sig_cache or {}

    for wi in windows:
        # Check trust (but don't skip -- we still compute indicators)
        trust_result = _check_trust(wi, trust_entries, sig_cache) if trust_entries else None
        # trust_result: None, ('trusted', entry), or ('failed', entry, fail_reason)

        indicators = []  # (reason_text, weight_key)

        # --- Verification failure indicator ---
        # Process name matches a trusted entry but verification failed.
        # This is a high concern: something is masquerading as a system process.
        if trust_result and trust_result[0] == 'failed':
            fail_reason = trust_result[2]
            indicators.append((f'trust-verify-failed({fail_reason})',
                               'trust-verification-failed'))

        # --- Positional indicators ---

        if wi.state == 'off-screen':
            indicators.append(('off-screen', 'off-screen'))

        # Cloaked windows can also be positionally off-screen -- check that
        # separately since state='cloaked' takes priority over 'off-screen'
        if wi.state == 'cloaked' and wi.is_off_screen:
            indicators.append(('off-screen', 'off-screen'))

        # Heavily shrunk: visible but tiny (not just minimized to taskbar)
        if wi.state not in ('minimized', 'hidden'):
            if 0 < wi.width < MIN_SANE_WIDTH or 0 < wi.height < MIN_SANE_HEIGHT:
                indicators.append((f'shrunk({wi.width}x{wi.height})', 'shrunk'))

        # Positioned partially off-screen (pushed mostly past a screen edge)
        if wi.state in ('normal', 'cloaked'):
            if wi.x < -wi.width // 2 or wi.y < -wi.height // 2:
                indicators.append(('partially-off-screen', 'partially-off-screen'))

        # --- Type indicators ---

        # Dialog/popup windows -- transient by nature, persistence is odd
        if wi.class_name in DIALOG_CLASSES:
            indicators.append((f'dialog({wi.class_name})', 'dialog'))

        # --- Cloaking indicators ---
        # Cloaking is a legitimate OS feature but still worth noting at low
        # concern. Can be abused, and compounds with other indicators.
        if wi.cloaked_type:
            indicators.append(('cloaked', 'cloaked'))
            # Shell/inherited cloaking: OS hid it (not user moving to desktop)
            if wi.cloaked_type & 0x6:
                indicators.append(('shell-cloaked', 'shell-cloaked'))

        # --- Score and level ---

        if indicators:
            reasons = [r for r, _ in indicators]
            score = sum(CONCERN_WEIGHTS.get(key, 1) for _, key in indicators)
            level = _score_to_level(score)

            is_trusted = trust_result and trust_result[0] == 'trusted'
            if is_trusted:
                # Trusted -- suppress flagging but record what would trigger
                entry = trust_result[1]
                wi.trusted = True
                wi.trust_source = entry['source']
                wi.trust_pattern = entry['pattern']
                wi.trust_verified = entry.get('verify')  # e.g., 'microsoft' or None
                wi.would_flag_reason = ', '.join(reasons)
                wi.would_concern_score = score
                wi.would_concern_level = level
            else:
                wi.suspicious = True
                wi.suspicious_reason = ', '.join(reasons)
                wi.concern_score = score
                wi.concern_level = level


def _check_trust(wi, trust_entries, sig_cache):
    """Check if a window's process matches a trust entry and passes verification.

    Returns:
        None                        - no name match
        ('trusted', entry)          - matched and verified (or no verification required)
        ('failed', entry, reason)   - matched by name but verification failed
    """
    proc_lower = wi.process_name.lower()

    for entry in trust_entries:
        if not fnmatch.fnmatch(proc_lower, entry['pattern'].lower()):
            continue

        # Name matched. Check if verification is required.
        verify = entry.get('verify')
        if not verify:
            # No verification needed (user trust or unverified default)
            return ('trusted', entry)

        # --- Path verification ---
        expected_paths = entry.get('expected_paths')
        if expected_paths:
            if not _verify_exe_path(wi.exe_path, expected_paths):
                actual = wi.exe_path or 'unknown'
                logger.warning(
                    f"Trust verification FAILED for {wi.process_name}: "
                    f"path '{actual}' doesn't match expected locations")
                return ('failed', entry, f'unexpected-path:{actual}')

        # --- Signature verification (Microsoft OS binary) ---
        if verify == 'microsoft' and wi.exe_path:
            norm_path = os.path.normcase(os.path.normpath(wi.exe_path))
            sig_info = sig_cache.get(norm_path)
            if sig_info is None:
                logger.warning(
                    f"Trust verification FAILED for {wi.process_name}: "
                    f"no signature data for '{wi.exe_path}'")
                return ('failed', entry, 'signature-not-checked')
            if not sig_info['valid']:
                logger.warning(
                    f"Trust verification FAILED for {wi.process_name}: "
                    f"invalid signature on '{wi.exe_path}'")
                return ('failed', entry, 'invalid-signature')
            if not sig_info['is_os_binary']:
                logger.warning(
                    f"Trust verification FAILED for {wi.process_name}: "
                    f"not a Microsoft OS binary '{wi.exe_path}'")
                return ('failed', entry, 'not-os-binary')

        return ('trusted', entry)

    return None


def _apply_filters(windows, include_pattern, exclude_pattern):
    """Apply fnmatch include/exclude filters on title and process name."""
    filtered = []
    for wi in windows:
        match_str = f"{wi.title} {wi.process_name}".lower()

        if include_pattern:
            if not fnmatch.fnmatch(match_str, include_pattern.lower()):
                continue

        if exclude_pattern:
            if fnmatch.fnmatch(match_str, exclude_pattern.lower()):
                continue

        filtered.append(wi)
    return filtered


def _exclude_by_process(windows, exclude_processes):
    """Remove windows whose process name matches any exclusion pattern."""
    filtered = []
    for wi in windows:
        proc_lower = wi.process_name.lower()
        excluded = False
        for pattern in exclude_processes:
            if fnmatch.fnmatch(proc_lower, pattern.lower()):
                excluded = True
                break
        if not excluded:
            filtered.append(wi)
    return filtered


def _compute_centered_position(wi, area_x, area_y, area_w, area_h,
                               offset_x=0, offset_y=0):
    """Calculate the centered (x, y) for a window within the target area.

    Accounts for collapsed/tiny windows by using sane defaults.
    Applies cascade offset and clamps to work area bounds.
    """
    w = wi.width if wi.width >= MIN_SANE_WIDTH else DEFAULT_RESTORE_WIDTH
    h = wi.height if wi.height >= MIN_SANE_HEIGHT else DEFAULT_RESTORE_HEIGHT
    w = min(w, area_w)
    h = min(h, area_h)
    cx = area_x + (area_w - w) // 2 + offset_x
    cy = area_y + (area_h - h) // 2 + offset_y
    # Clamp to work area bounds
    cx = max(area_x, min(cx, area_x + area_w - w))
    cy = max(area_y, min(cy, area_y + area_h - h))
    return cx, cy


def _simulate_window(wi, area_x, area_y, area_w, area_h,
                     show_hidden, include_virtual, act_on_all=True,
                     offset_x=0, offset_y=0):
    """Dry-run: determine what action would be taken and compute target position."""

    # Collapsed/tiny window annotation
    is_tiny = wi.width < MIN_SANE_WIDTH or wi.height < MIN_SANE_HEIGHT
    resize_note = '+resize' if is_tiny and wi.state != 'hidden' else ''
    fg_note = '+foreground' if wi.suspicious else ''

    if wi.state == 'minimized':
        wi.action_taken = f'would:restore{resize_note}+center{fg_note}'
        wi.target_x, wi.target_y = _compute_centered_position(
            wi, area_x, area_y, area_w, area_h, offset_x, offset_y)

    elif wi.state == 'hidden' and show_hidden:
        if act_on_all or wi.suspicious:
            wi.action_taken = f'would:show{resize_note}+center{fg_note}'
            wi.target_x, wi.target_y = _compute_centered_position(
                wi, area_x, area_y, area_w, area_h, offset_x, offset_y)
        else:
            wi.action_taken = 'skip:hidden-normal'

    elif wi.state == 'hidden' and not show_hidden:
        wi.action_taken = 'skip:hidden'

    elif wi.state == 'cloaked':
        if include_virtual or wi.suspicious:
            wi.action_taken = f'would:pull-desktop{resize_note}+center{fg_note}'
            wi.target_x, wi.target_y = _compute_centered_position(
                wi, area_x, area_y, area_w, area_h, offset_x, offset_y)
        else:
            wi.action_taken = 'skip:cloaked'

    else:
        # normal, maximized, off-screen -- would be centered
        wi.action_taken = f'would:center{resize_note}{fg_note}'
        wi.target_x, wi.target_y = _compute_centered_position(
            wi, area_x, area_y, area_w, area_h, offset_x, offset_y)


def _process_window(platform, wi, area_x, area_y, area_w, area_h,
                    show_hidden, include_virtual,
                    act_on_all=True, offset_x=0, offset_y=0):
    """Restore, show, and center a single window.

    offset_x, offset_y: cascade offset from center for visual separation.
    """
    action_parts = []

    if wi.state == 'minimized':
        if platform.restore_window(wi):
            action_parts.append('restored')
        else:
            wi.action_taken = 'failed'
            return

    elif wi.state == 'hidden' and show_hidden:
        if act_on_all or wi.suspicious:
            if platform.show_window(wi):
                action_parts.append('shown')
            else:
                wi.action_taken = 'failed'
                return
        else:
            wi.action_taken = 'skipped:hidden-normal'
            return

    elif wi.state == 'hidden' and not show_hidden:
        wi.action_taken = 'skipped'
        return

    elif wi.state == 'cloaked':
        if include_virtual or wi.suspicious:
            if platform.move_from_virtual_desktop(wi):
                action_parts.append('pulled-from-desktop')
                platform.show_window(wi)
            else:
                wi.action_taken = 'failed:vd-move'
                return
        else:
            wi.action_taken = 'skipped:cloaked'
            return

    # Center the window with cascade offset
    if platform.center_window(wi, area_x, area_y, area_w, area_h,
                              offset_x=offset_x, offset_y=offset_y):
        action_parts.append('centered')
        wi.target_x, wi.target_y = _compute_centered_position(
            wi, area_x, area_y, area_w, area_h, offset_x, offset_y)
    else:
        action_parts.append('center-failed')

    # All suspicious windows get brought to front so the user sees them.
    # Processing order (level 5 first → level 1 last) ensures the
    # highest concern windows end up on top of the z-order.
    if wi.suspicious:
        if platform.bring_to_front(wi):
            action_parts.append('foreground')

    wi.action_taken = '+'.join(action_parts) if action_parts else 'unchanged'


# ---------------------------------------------------------------------------
# State file for --undo support
# ---------------------------------------------------------------------------

def _get_state_dir():
    """Return the directory for wingather state files."""
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        return Path(base) / 'wingather'
    return Path.home() / '.local' / 'share' / 'wingather'


def _get_state_file():
    """Return the path to the last_shown state file."""
    return _get_state_dir() / 'last_shown.json'


def save_shown_state(windows_shown):
    """Save a record of windows that were made visible by --show-hidden.

    windows_shown: list of WindowInfo objects that were hidden and are now shown.
    """
    from wingather._version import PIP_VERSION

    state_dir = _get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for wi in windows_shown:
        records.append({
            'hwnd': wi.handle,
            'pid': wi.pid,
            'process_name': wi.process_name,
            'title': wi.title,
        })

    state = {
        'version': 1,
        'timestamp': datetime.datetime.now().isoformat(),
        'wingather_version': PIP_VERSION,
        'windows_shown': records,
    }

    state_file = _get_state_file()
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

    logger.info(f"Saved undo state: {len(records)} window(s) to {state_file}")
    return state_file


def undo_show_hidden():
    """Re-hide windows that were previously shown by --show-hidden.

    Reads the state file, validates each HWND still exists and matches
    the original PID, then hides it. Returns (hidden_count, skipped_count).
    """
    state_file = _get_state_file()
    if not state_file.exists():
        logger.error("No undo state found. Run with --show-hidden first.")
        return 0, 0

    with open(state_file, 'r') as f:
        state = json.load(f)

    records = state.get('windows_shown', [])
    if not records:
        logger.info("Undo state is empty — nothing to re-hide.")
        state_file.unlink(missing_ok=True)
        return 0, 0

    timestamp = state.get('timestamp', 'unknown')
    logger.info(f"Undo state from {timestamp}: {len(records)} window(s)")

    platform = get_platform()
    platform.setup()

    hidden_count = 0
    skipped_count = 0

    for rec in records:
        hwnd = rec['hwnd']
        expected_pid = rec['pid']
        proc_name = rec.get('process_name', '<unknown>')
        title = rec.get('title', '<untitled>')

        # Validate: check if the HWND still exists and belongs to the same PID
        try:
            import win32process
            import win32gui
            _, actual_pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            logger.debug(f"  Skip: HWND {hwnd} no longer exists ({proc_name}: {title})")
            skipped_count += 1
            continue

        if actual_pid != expected_pid:
            logger.debug(
                f"  Skip: HWND {hwnd} PID changed {expected_pid} -> {actual_pid} "
                f"({proc_name}: {title})")
            skipped_count += 1
            continue

        # Check if window is currently visible (no point hiding an already-hidden window)
        try:
            is_visible = win32gui.IsWindowVisible(hwnd)
        except Exception:
            skipped_count += 1
            continue

        if not is_visible:
            logger.debug(f"  Skip: HWND {hwnd} already hidden ({proc_name}: {title})")
            skipped_count += 1
            continue

        # Create a minimal WindowInfo for the platform hide call
        from wingather.platforms.base import WindowInfo
        wi = WindowInfo(
            handle=hwnd, title=title, class_name='',
            process_name=proc_name, pid=expected_pid,
            x=0, y=0, width=0, height=0,
            state='normal', is_visible=True,
        )

        if platform.hide_window(wi):
            logger.debug(f"  Hidden: HWND {hwnd} ({proc_name}: {title})")
            hidden_count += 1
        else:
            logger.debug(f"  Failed: HWND {hwnd} ({proc_name}: {title})")
            skipped_count += 1

    # Clean up state file
    state_file.unlink(missing_ok=True)
    logger.info(f"Undo complete: {hidden_count} re-hidden, {skipped_count} skipped")
    return hidden_count, skipped_count
