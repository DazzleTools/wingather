"""Tests for trust matching, path verification, and default trust loading."""

import os
import pytest
from wingather.core import _verify_exe_path, _load_default_trust, _check_trust
from wingather.platforms.base import WindowInfo


class TestVerifyExePath:
    """Verify executable path matching against expected patterns."""

    def test_exact_match(self):
        assert _verify_exe_path(
            r"C:\Windows\explorer.exe",
            [r"C:\Windows\explorer.exe"]
        )

    def test_case_insensitive(self):
        assert _verify_exe_path(
            r"C:\WINDOWS\EXPLORER.EXE",
            [r"C:\Windows\explorer.exe"]
        )

    def test_wildcard_match(self):
        """SystemApps paths have package hashes that vary by Windows version."""
        assert _verify_exe_path(
            r"C:\Windows\SystemApps\ShellExperienceHost_cw5n1h2txyewy\ShellExperienceHost.exe",
            [r"C:\Windows\SystemApps\ShellExperienceHost_*\ShellExperienceHost.exe"]
        )

    def test_no_match(self):
        assert not _verify_exe_path(
            r"C:\Users\evil\explorer.exe",
            [r"C:\Windows\explorer.exe"]
        )

    def test_none_path(self):
        assert not _verify_exe_path(None, [r"C:\Windows\explorer.exe"])

    def test_empty_path(self):
        assert not _verify_exe_path("", [r"C:\Windows\explorer.exe"])

    def test_multiple_expected_paths(self):
        assert _verify_exe_path(
            r"C:\Windows\system32\sihost.exe",
            [r"C:\Windows\sihost.exe", r"C:\Windows\system32\sihost.exe"]
        )

    def test_forward_slashes_normalized(self):
        assert _verify_exe_path(
            "C:/Windows/explorer.exe",
            [r"C:\Windows\explorer.exe"]
        )


class TestLoadDefaultTrust:
    """Verify the default trust JSON loads correctly."""

    def test_loads_successfully(self):
        entries = _load_default_trust()
        assert isinstance(entries, list)
        assert len(entries) > 0

    def test_entries_have_pattern(self):
        entries = _load_default_trust()
        for entry in entries:
            assert 'pattern' in entry, f"Entry missing 'pattern': {entry}"

    def test_entries_have_reason(self):
        entries = _load_default_trust()
        for entry in entries:
            assert 'reason' in entry, f"Entry missing 'reason': {entry}"

    def test_explorer_is_in_defaults(self):
        entries = _load_default_trust()
        patterns = [e['pattern'] for e in entries]
        assert 'explorer.exe' in patterns

    def test_microsoft_entries_have_verify(self):
        """Entries with expected_paths should also have verify='microsoft'."""
        entries = _load_default_trust()
        for entry in entries:
            if 'expected_paths' in entry:
                assert entry.get('verify') == 'microsoft', (
                    f"Entry '{entry['pattern']}' has expected_paths but no verify"
                )


class TestCheckTrust:
    """Verify trust matching logic."""

    def _make_window(self, process_name, exe_path=None):
        wi = WindowInfo(
            handle=0x1234, title="Test", class_name="TestClass",
            process_name=process_name, pid=1000,
            x=100, y=100, width=800, height=600,
            state='normal', is_visible=True,
        )
        wi.exe_path = exe_path
        return wi

    def test_no_match_returns_none(self):
        wi = self._make_window("unknown.exe")
        entries = [{'pattern': 'explorer.exe', 'source': 'default'}]
        assert _check_trust(wi, entries, {}) is None

    def test_simple_name_match(self):
        wi = self._make_window("myapp.exe")
        entries = [{'pattern': 'myapp.exe', 'source': 'user'}]
        result = _check_trust(wi, entries, {})
        assert result[0] == 'trusted'

    def test_fnmatch_wildcard(self):
        wi = self._make_window("chrome_helper.exe")
        entries = [{'pattern': 'chrome*', 'source': 'user'}]
        result = _check_trust(wi, entries, {})
        assert result[0] == 'trusted'

    def test_case_insensitive_match(self):
        wi = self._make_window("Explorer.EXE")
        entries = [{'pattern': 'explorer.exe', 'source': 'default'}]
        result = _check_trust(wi, entries, {})
        assert result[0] == 'trusted'

    def test_path_verification_pass(self):
        wi = self._make_window("explorer.exe", r"C:\Windows\explorer.exe")
        entries = [{
            'pattern': 'explorer.exe',
            'source': 'default',
            'verify': 'microsoft',
            'expected_paths': [r"C:\Windows\explorer.exe"],
        }]
        # Provide valid sig cache
        norm = os.path.normcase(os.path.normpath(r"C:\Windows\explorer.exe"))
        sig_cache = {norm: {'valid': True, 'is_os_binary': True, 'signer': 'Microsoft'}}
        result = _check_trust(wi, entries, sig_cache)
        assert result[0] == 'trusted'

    def test_path_verification_fail(self):
        wi = self._make_window("explorer.exe", r"C:\Users\evil\explorer.exe")
        entries = [{
            'pattern': 'explorer.exe',
            'source': 'default',
            'verify': 'microsoft',
            'expected_paths': [r"C:\Windows\explorer.exe"],
        }]
        result = _check_trust(wi, entries, {})
        assert result[0] == 'failed'
        assert 'unexpected-path' in result[2]

    def test_signature_verification_fail_not_os_binary(self):
        wi = self._make_window("explorer.exe", r"C:\Windows\explorer.exe")
        entries = [{
            'pattern': 'explorer.exe',
            'source': 'default',
            'verify': 'microsoft',
            'expected_paths': [r"C:\Windows\explorer.exe"],
        }]
        norm = os.path.normcase(os.path.normpath(r"C:\Windows\explorer.exe"))
        sig_cache = {norm: {'valid': True, 'is_os_binary': False, 'signer': 'EvilCorp'}}
        result = _check_trust(wi, entries, sig_cache)
        assert result[0] == 'failed'
        assert 'not-os-binary' in result[2]

    def test_no_verify_skips_checks(self):
        """User trust patterns don't require verification."""
        wi = self._make_window("myapp.exe", r"C:\anywhere\myapp.exe")
        entries = [{'pattern': 'myapp.exe', 'source': 'user'}]
        result = _check_trust(wi, entries, {})
        assert result[0] == 'trusted'
