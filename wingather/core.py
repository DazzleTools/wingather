"""Core orchestration logic for wingather (platform-agnostic)."""

import fnmatch
import json
import logging
import os
import subprocess
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
#
# TOPMOST z-order is applied for levels 1-3 (score >= 3).
CONCERN_WEIGHTS = {
    'off-screen':                4,  # completely invisible to the user
    'shrunk':                    3,  # deliberately tiny, hiding in plain sight
    'dialog':                    2,  # transient popup persisting unexpectedly
    'partially-off-screen':      2,  # pushed partly out of view
    'cloaked':                   1,  # on another desktop or OS-managed
    'shell-cloaked':             1,  # bonus: OS hid it (not user action)
    'trust-verification-failed': 5,  # masquerading as a trusted process name
}

# Level 1-3 get TOPMOST treatment; 4-5 are flagged but not forced on top
TOPMOST_THRESHOLD = 3


def gather_windows(list_only=False, dry_run=False, show_hidden=False,
                   include_virtual=False, monitor_index=0,
                   filter_pattern=None, exclude_pattern=None,
                   exclude_processes=None, trusted_processes=None,
                   no_default_trust=False):
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
                         normally but won't be flagged [!] or set TOPMOST.
      no_default_trust:  If True, skip the built-in default trust list. User-provided
                         -tp patterns still apply.
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
    suspicious_count = sum(1 for w in windows if w.suspicious)
    trusted_count = sum(1 for w in windows if w.trusted)
    if suspicious_count:
        logger.info(f"Flagged {suspicious_count} suspicious window(s)")
    if trusted_count:
        logger.info(f"Trusted {trusted_count} window(s) (flagging suppressed)")

    if list_only:
        return windows

    # Split into concern tiers:
    #   high_concern = levels 1-3 (get TOPMOST z-order)
    #   low_concern  = levels 4-5 (flagged but not forced on top)
    #   normal       = no concern
    high_concern = [w for w in windows if w.concern_level and w.concern_level <= TOPMOST_THRESHOLD]
    low_concern = [w for w in windows if w.concern_level and w.concern_level > TOPMOST_THRESHOLD]
    normal = [w for w in windows if not w.suspicious]

    # Process normal first, then low concern, then high concern last
    # (last processed = on top of z-order)
    for wi in normal:
        if dry_run:
            _simulate_window(wi, area_x, area_y, area_w, area_h,
                             show_hidden, include_virtual)
        else:
            _process_window(platform, wi, area_x, area_y, area_w, area_h,
                            show_hidden, include_virtual, topmost=False)

    for wi in low_concern:
        if dry_run:
            _simulate_window(wi, area_x, area_y, area_w, area_h,
                             show_hidden, include_virtual)
        else:
            _process_window(platform, wi, area_x, area_y, area_w, area_h,
                            show_hidden, include_virtual, topmost=False)

    for wi in high_concern:
        if dry_run:
            _simulate_window(wi, area_x, area_y, area_w, area_h,
                             show_hidden, include_virtual)
        else:
            _process_window(platform, wi, area_x, area_y, area_w, area_h,
                            show_hidden, include_virtual, topmost=True)

    # Return sorted: highest concern first, then low concern, then normal
    return high_concern + low_concern + normal


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


def _compute_centered_position(wi, area_x, area_y, area_w, area_h):
    """Calculate the centered (x, y) for a window within the target area.

    Accounts for collapsed/tiny windows by using sane defaults.
    """
    w = wi.width if wi.width >= MIN_SANE_WIDTH else DEFAULT_RESTORE_WIDTH
    h = wi.height if wi.height >= MIN_SANE_HEIGHT else DEFAULT_RESTORE_HEIGHT
    w = min(w, area_w)
    h = min(h, area_h)
    cx = area_x + (area_w - w) // 2
    cy = area_y + (area_h - h) // 2
    return cx, cy


def _simulate_window(wi, area_x, area_y, area_w, area_h,
                     show_hidden, include_virtual):
    """Dry-run: determine what action would be taken and compute target position."""

    # Collapsed/tiny window annotation
    is_tiny = wi.width < MIN_SANE_WIDTH or wi.height < MIN_SANE_HEIGHT
    resize_note = '+resize' if is_tiny and wi.state != 'hidden' else ''
    use_topmost = wi.concern_level and wi.concern_level <= TOPMOST_THRESHOLD
    topmost_note = '+TOPMOST' if use_topmost else ''

    if wi.state == 'minimized':
        wi.action_taken = f'would:restore{resize_note}+center{topmost_note}'
        wi.target_x, wi.target_y = _compute_centered_position(
            wi, area_x, area_y, area_w, area_h)

    elif wi.state == 'hidden' and show_hidden:
        wi.action_taken = f'would:show{resize_note}+center{topmost_note}'
        wi.target_x, wi.target_y = _compute_centered_position(
            wi, area_x, area_y, area_w, area_h)

    elif wi.state == 'hidden' and not show_hidden:
        wi.action_taken = 'skip:hidden'

    elif wi.state == 'cloaked':
        if include_virtual or wi.suspicious:
            wi.action_taken = f'would:pull-desktop{resize_note}+center{topmost_note}'
            wi.target_x, wi.target_y = _compute_centered_position(
                wi, area_x, area_y, area_w, area_h)
        else:
            wi.action_taken = 'skip:cloaked'

    else:
        # normal, maximized, off-screen -- would be centered
        wi.action_taken = f'would:center{resize_note}{topmost_note}'
        wi.target_x, wi.target_y = _compute_centered_position(
            wi, area_x, area_y, area_w, area_h)


def _process_window(platform, wi, area_x, area_y, area_w, area_h,
                    show_hidden, include_virtual, topmost=False):
    """Restore, show, and center a single window.

    If topmost=True, the window is placed at HWND_TOPMOST z-order
    (used for suspicious windows so they're immediately visible).
    """
    action_parts = []

    if wi.state == 'minimized':
        if platform.restore_window(wi):
            action_parts.append('restored')
        else:
            wi.action_taken = 'failed'
            return

    elif wi.state == 'hidden' and show_hidden:
        if platform.show_window(wi):
            action_parts.append('shown')
        else:
            wi.action_taken = 'failed'
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

    # Center the window (topmost flag passed to platform)
    if platform.center_window(wi, area_x, area_y, area_w, area_h, topmost=topmost):
        action_parts.append('centered')
        if topmost:
            action_parts.append('TOPMOST')
        wi.target_x, wi.target_y = _compute_centered_position(
            wi, area_x, area_y, area_w, area_h)
    else:
        action_parts.append('center-failed')

    wi.action_taken = '+'.join(action_parts) if action_parts else 'unchanged'
