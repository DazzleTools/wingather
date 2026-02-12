"""Tests for CLI argument parsing."""

import pytest
from wingather.cli import build_parser


class TestCLIParsing:
    """Verify argument parsing produces correct values."""

    def test_defaults(self):
        args = build_parser().parse_args([])
        assert not args.list_only
        assert not args.dry_run
        assert not args.show_hidden
        assert not args.include_virtual
        assert not args.json_output
        assert args.monitor == 0
        assert args.filter is None
        assert args.exclude is None
        assert args.exclude_process == []
        assert args.trust == []
        assert args.trust_file is None
        assert not args.no_default_trust
        assert not args.verbose

    def test_dry_run_short(self):
        args = build_parser().parse_args(['-n'])
        assert args.dry_run

    def test_dry_run_long(self):
        args = build_parser().parse_args(['--dry-run'])
        assert args.dry_run

    def test_list_only(self):
        args = build_parser().parse_args(['--list-only'])
        assert args.list_only

    def test_list_only_short(self):
        args = build_parser().parse_args(['-l'])
        assert args.list_only

    def test_verbose(self):
        args = build_parser().parse_args(['-v'])
        assert args.verbose

    def test_monitor_index(self):
        args = build_parser().parse_args(['-m', '2'])
        assert args.monitor == 2

    def test_json_output(self):
        args = build_parser().parse_args(['--json'])
        assert args.json_output

    def test_show_hidden(self):
        args = build_parser().parse_args(['--show-hidden'])
        assert args.show_hidden

    def test_include_virtual(self):
        args = build_parser().parse_args(['--include-virtual'])
        assert args.include_virtual

    def test_filter_pattern(self):
        args = build_parser().parse_args(['-f', '*chrome*'])
        assert args.filter == '*chrome*'

    def test_exclude_pattern(self):
        args = build_parser().parse_args(['-x', '*debug*'])
        assert args.exclude == '*debug*'

    def test_exclude_process_single(self):
        args = build_parser().parse_args(['-xp', 'notepad.exe'])
        assert args.exclude_process == ['notepad.exe']

    def test_exclude_process_multiple(self):
        args = build_parser().parse_args(['-xp', 'notepad.exe', '-xp', 'calc.exe'])
        assert args.exclude_process == ['notepad.exe', 'calc.exe']

    def test_trust_single(self):
        args = build_parser().parse_args(['-tp', 'myapp.exe'])
        assert args.trust == ['myapp.exe']

    def test_trust_multiple(self):
        args = build_parser().parse_args(['-tp', 'app1.exe', '-tp', 'app2*'])
        assert args.trust == ['app1.exe', 'app2*']

    def test_trust_file(self):
        args = build_parser().parse_args(['--trust-file', 'trust.txt'])
        assert args.trust_file == 'trust.txt'

    def test_no_default_trust(self):
        args = build_parser().parse_args(['--no-default-trust'])
        assert args.no_default_trust

    def test_combined_flags(self):
        args = build_parser().parse_args([
            '-n', '-v', '--json', '-tp', 'explorer.exe', '-xp', 'calc.exe'
        ])
        assert args.dry_run
        assert args.verbose
        assert args.json_output
        assert args.trust == ['explorer.exe']
        assert args.exclude_process == ['calc.exe']
