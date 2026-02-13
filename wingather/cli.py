"""Command-line interface for wingather."""

import argparse
import json
import logging
import sys

from wingather import __version__, __app_name__, DISPLAY_VERSION
from wingather.core import gather_windows, undo_show_hidden


def build_parser():
    parser = argparse.ArgumentParser(
        prog=__app_name__,
        description="Find suspicious windows and bring them to your attention.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s --dry-run -v                    Preview suspicious windows (verbose)
  %(prog)s --all --dry-run                 Preview ALL windows (original behavior)
  %(prog)s -n --show-hidden                Dryrun + reveal suspicious hidden windows
  %(prog)s --show-hidden --all             Reveal ALL hidden windows (use with caution)
  %(prog)s --undo                          Re-hide windows from last --show-hidden
  %(prog)s --include-virtual               Pull windows from other desktops
  %(prog)s -tp xntimer.exe -tp "myapp*"    Trust multiple processes (skip flagging)
  %(prog)s --trust-file mytrust.txt        Trust from file (one per line)
  %(prog)s --no-default-trust --dry-run    Flag everything, ignore defaults
  %(prog)s -xp notepad.exe --dry-run       Exclude a process entirely
  %(prog)s -f "*chrome*" --dry-run         Only affect Chrome windows
  %(prog)s --json --dry-run                Output as JSON

common:
  %(prog)s -n -iv -v --dry-run             Preview suspicious windows on all desktops (verbose)

concern levels:
  [!1] ALERT    Highest concern (e.g., off-screen + dialog)
  [!2] ALERT    High concern (e.g., off-screen)
  [!3] CONCERN  Moderate (e.g., shrunk window)
  [!4] NOTE     Low concern (e.g., dialog, partial off-screen)
  [!5] NOTE     Informational (e.g., cloaked on another desktop)
  All flagged windows are centered and brought to the foreground.
  Higher concern windows appear on top of lower concern ones.

trust verification:
  Built-in trusted processes (e.g., explorer.exe) are verified by checking
  their file path and Microsoft Authenticode signature before suppressing
  flags. Use --no-default-trust to bypass. User -tp patterns are name-only.

Report bugs: https://github.com/DazzleTools/wingather/issues
Copyright (C) 2026 Dustin Darcy. Licensed under GPL-3.0.""",
    )
    parser.add_argument(
        '--version', action='version',
        version=f'{__app_name__} {DISPLAY_VERSION} ({__version__})'
    )
    parser.add_argument(
        '--list-only', '-l', action='store_true',
        help='List windows without any action simulation'
    )
    parser.add_argument(
        '--dry-run', '-n', action='store_true',
        help='Simulate: show what would be moved and where, without moving anything'
    )
    parser.add_argument(
        '--all', '-a', dest='gather_all', action='store_true',
        help='Act on all windows, not just suspicious ones (default: suspicious only)'
    )
    parser.add_argument(
        '--show-hidden', '-sh', action='store_true',
        help='Also reveal hidden windows (use with caution; use --undo to reverse)'
    )
    parser.add_argument(
        '--undo', '-u', action='store_true',
        help='Re-hide windows that were shown by a previous --show-hidden run'
    )
    parser.add_argument(
        '--include-virtual', "-iv", action='store_true',
        help='Pull windows from other virtual desktops to the current one'
    )
    parser.add_argument(
        '--json', dest='json_output', action='store_true',
        help='Output results as JSON'
    )
    parser.add_argument(
        '--monitor', '-m', type=int, default=0,
        help='Display monitor index to center windows on (default: primary = 0)'
    )
    parser.add_argument(
        '--filter', '-f', type=str, default=None,
        help='Only affect windows matching pattern (fnmatch, applied to title and process)'
    )
    parser.add_argument(
        '--exclude', '-x', type=str, default=None,
        help='Exclude windows matching pattern (fnmatch, applied to title and process)'
    )
    parser.add_argument(
        '--exclude-process', '-xp', action='append', default=[],
        metavar='NAME',
        help='Exclude windows by process name (repeatable, fnmatch pattern). '
             'E.g.: -xp notepad.exe -xp calc.exe -xp "chrome*"'
    )
    parser.add_argument(
        '--exclude-file', '-xf', type=str, default=None, metavar='PATH',
        help='File containing process names to exclude, one per line'
    )
    parser.add_argument(
        '--trust', '-tp', action='append', default=[],
        metavar='NAME',
        help='Trust a process (skip suspicious flagging). Repeatable, fnmatch pattern. '
             'E.g.: -tp xntimer.exe -tp "myapp*"'
    )
    parser.add_argument(
        '--trust-file', '-tf', type=str, default=None, metavar='PATH',
        help='File containing trusted process names, one per line'
    )
    parser.add_argument(
        '--no-default-trust', '-ndt', action='store_true',
        help='Bypass the built-in default trust list (still honors -tp patterns)'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Verbose logging output'
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s',
    )

    # Handle --undo: re-hide windows from previous --show-hidden
    if args.undo:
        hidden_count, skipped_count = undo_show_hidden()
        if hidden_count or skipped_count:
            print(f"\n  Undo complete: {hidden_count} window(s) re-hidden"
                  f"{f', {skipped_count} skipped (stale/closed)' if skipped_count else ''}")
        else:
            print("\n  No undo state found. Run with --show-hidden first.")
        return

    # Print banner when --show-hidden is active
    if args.show_hidden:
        _print_show_hidden_banner(args.gather_all)

    # Build process exclusion list
    exclude_processes = list(args.exclude_process)
    if args.exclude_file:
        try:
            with open(args.exclude_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        exclude_processes.append(line)
        except FileNotFoundError:
            print(f"Warning: exclude file not found: {args.exclude_file}",
                  file=sys.stderr)

    # Build trusted process list (whitelist from suspicious flagging)
    trusted_processes = list(args.trust)
    if args.trust_file:
        try:
            with open(args.trust_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        trusted_processes.append(line)
        except FileNotFoundError:
            print(f"Warning: trust file not found: {args.trust_file}",
                  file=sys.stderr)

    try:
        results = gather_windows(
            list_only=args.list_only,
            dry_run=args.dry_run,
            show_hidden=args.show_hidden,
            include_virtual=args.include_virtual,
            monitor_index=args.monitor,
            filter_pattern=args.filter,
            exclude_pattern=args.exclude,
            exclude_processes=exclude_processes,
            trusted_processes=trusted_processes or None,
            no_default_trust=args.no_default_trust,
            gather_all=args.gather_all,
        )
    except NotImplementedError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine display mode
    mode = 'list' if args.list_only else ('dry-run' if args.dry_run else 'live')

    if args.json_output:
        _print_json(results, mode)
    else:
        _print_table(results, mode)


def _print_show_hidden_banner(gather_all):
    """Print educational banner when --show-hidden is used."""
    print("\n  NOTE: Hidden windows are typically system internals (GDI+ surfaces,")
    print("  DDE handlers, .NET event pumps) with no user interface. They are")
    print("  hidden because they serve background functions. Use --undo to reverse.")
    print("  See docs/hidden-windows.md for details.")
    if not gather_all:
        print("  Mode: suspicious hidden windows only. Use --all to reveal all.\n")
    else:
        print("  Mode: showing ALL hidden windows.\n")


def _print_json(results, mode):
    data = []
    for wi in results:
        entry = {
            'handle': wi.handle,
            'title': wi.title,
            'class': wi.class_name,
            'process': wi.process_name,
            'pid': wi.pid,
            'state': wi.state,
            'action': wi.action_taken,
            'current_position': {'x': wi.x, 'y': wi.y, 'w': wi.width, 'h': wi.height},
        }
        if wi.target_x is not None:
            entry['target_position'] = {'x': wi.target_x, 'y': wi.target_y}
        if wi.suspicious:
            entry['concern_level'] = wi.concern_level
            entry['concern_score'] = wi.concern_score
            entry['concern_reason'] = wi.suspicious_reason
        if wi.trusted:
            entry['trusted'] = True
            entry['trust_source'] = wi.trust_source
            if wi.trust_verified:
                entry['trust_verified'] = wi.trust_verified
            entry['would_concern_level'] = wi.would_concern_level
            entry['would_concern_reason'] = wi.would_flag_reason
        data.append(entry)
    print(json.dumps(data, indent=2))


def _safe_str(s):
    """Encode string safely for console output, replacing unencodable chars."""
    try:
        s.encode(sys.stdout.encoding or 'utf-8')
        return s
    except (UnicodeEncodeError, LookupError):
        return s.encode('ascii', errors='replace').decode('ascii')


def _render_wrapped(parts):
    """Render a table row, wrapping to the next line when a field overflows.

    parts: list of (col_start, text) in column order.
    When a field's content extends past the next field's start position,
    remaining fields wrap to a new line at their correct column positions.
    """
    lines = []
    line = ""
    for col_start, text in parts:
        cursor = len(line)
        if cursor > col_start and line.strip():
            lines.append(line.rstrip())
            line = " " * col_start + text
        else:
            line += " " * max(0, col_start - cursor) + text
    if line.strip():
        lines.append(line.rstrip())
    return "\n".join(lines)


def _print_table(results, mode):
    if not results:
        print("No windows found.")
        return

    show_target = mode in ('dry-run', 'live')

    # Header
    labels = {'list': 'DISCOVERED', 'dry-run': 'DRY RUN', 'live': 'GATHERED'}
    header = labels.get(mode, 'WINDOWS')
    print(f"\n  {header}: {len(results)} window(s)")
    if mode == 'dry-run':
        print("  (no windows will be moved)\n")
    else:
        print()

    # Column definitions: (label, width, gap_after, right_align)
    # Empty label = blank in header/separator (used for the [!N] flag prefix)
    columns = [
        ('',            4,  1, False),
        ('HWND',       10,  2, True),
        ('PID',         7,  2, True),
        ('STATE',      12,  2, False),
    ]
    if show_target:
        columns += [
            ('ACTION',      28,  2, False),
            ('CURRENT POS', 22,  2, False),
            ('TARGET POS',  14,  2, False),
        ]
    else:
        columns += [
            ('ACTION',      12,  2, False),
        ]
    columns += [
        ('PROCESS',    24,  2, False),
        ('TITLE',      35,  0, False),
    ]

    # Compute absolute column start positions
    starts = []
    pos = 0
    for _, width, gap, _ in columns:
        starts.append(pos)
        pos += width + gap

    # Print header and separator
    hdr_parts = []
    sep_parts = []
    for i, (label, width, _, right) in enumerate(columns):
        if not label:
            hdr_parts.append((starts[i], " " * width))
            sep_parts.append((starts[i], " " * width))
        else:
            fmt = f"{label:>{width}}" if right else f"{label:<{width}}"
            hdr_parts.append((starts[i], fmt))
            sep_parts.append((starts[i], "-" * width))
    print(_render_wrapped(hdr_parts))
    print(_render_wrapped(sep_parts))

    # Print rows
    for wi in results:
        action = wi.action_taken or ('--' if mode == 'list' else 'skipped')
        title = _safe_str(wi.title[:50]) if wi.title else '<untitled>'
        proc = _safe_str(wi.process_name[:20]) if wi.process_name else '<unknown>'
        flag = f'[!{wi.concern_level}]' if wi.suspicious else '    '

        cells = [flag, f"{wi.handle:>10}", f"{wi.pid:>7}", wi.state]
        if show_target:
            cur_pos = f"({wi.x},{wi.y}) {wi.width}x{wi.height}"
            tgt_pos = f"-> ({wi.target_x},{wi.target_y})" if wi.target_x is not None else ""
            cells += [action, cur_pos, tgt_pos]
        else:
            cells += [action]
        cells += [proc, title]

        parts = list(zip(starts, cells))
        print(_render_wrapped(parts))

        if wi.suspicious:
            label = {1: 'ALERT', 2: 'ALERT', 3: 'CONCERN',
                     4: 'NOTE', 5: 'NOTE'}.get(wi.concern_level, 'NOTE')
            print(f"      ** {label} {wi.concern_level}: {wi.suspicious_reason}")

    print()

    # Summary
    flagged = [w for w in results if w.suspicious]
    if mode != 'list':
        actions = {}
        for wi in results:
            a = wi.action_taken or 'skipped'
            actions[a] = actions.get(a, 0) + 1
        summary = ', '.join(f"{v} {k}" for k, v in sorted(actions.items()))
        print(f"  Summary: {summary}")
    if flagged:
        by_level = {}
        for w in flagged:
            by_level.setdefault(w.concern_level, 0)
            by_level[w.concern_level] += 1
        parts = [f"{count}x level {lvl}" for lvl, count in sorted(by_level.items())]
        print(f"  Flagged: {len(flagged)} window(s) ({', '.join(parts)})")
        print(f"  Scale: 1=highest concern, 5=informational.")

    # Show trusted (suppressed) windows so users know what was skipped
    trusted = [w for w in results if w.trusted]
    if trusted:
        print(f"\n  Trusted (flagging suppressed): {len(trusted)} window(s)")
        for w in trusted:
            level_label = {1: 'ALERT', 2: 'ALERT', 3: 'CONCERN',
                           4: 'NOTE', 5: 'NOTE'}.get(w.would_concern_level, 'NOTE')
            proc = _safe_str(w.process_name[:24]) if w.process_name else '<unknown>'
            verify_labels = {'microsoft': 'MS-signed'}
            verified = verify_labels.get(w.trust_verified, w.trust_verified)
            badge = f"{w.trust_source}, {verified}" if w.trust_verified else w.trust_source
            print(f"    {proc:<24} would be [!{w.would_concern_level}] "
                  f"{level_label}: {w.would_flag_reason}  [{badge}]")
        print(f"  Use --no-default-trust to flag these windows too.")
    print()
