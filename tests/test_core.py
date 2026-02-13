"""Tests for core orchestration logic — simulation, mode gating, and banner."""

import pytest
from wingather.platforms.base import WindowInfo
from wingather.core import _simulate_window


def _make_window(state='normal', suspicious=False, concern_level=0,
                 width=800, height=600, class_name='', x=100, y=100):
    """Create a WindowInfo with sensible defaults for testing."""
    wi = WindowInfo(
        handle=12345, title='Test Window', class_name=class_name,
        process_name='test.exe', pid=1000,
        x=x, y=y, width=width, height=height,
        state=state, is_visible=(state != 'hidden'),
    )
    wi.suspicious = suspicious
    wi.concern_level = concern_level
    return wi


class TestSimulateWindowMode:
    """Test _simulate_window respects act_on_all for hidden window gating."""

    def test_normal_window_always_simulated(self):
        """Normal windows are simulated regardless of act_on_all
        (gating happens in the gather_windows loop, not in _simulate_window)."""
        wi = _make_window(state='normal')
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=False)
        assert wi.action_taken == 'would:center'

    def test_hidden_show_all(self):
        """Hidden window + show_hidden + act_on_all → would:show+center."""
        wi = _make_window(state='hidden')
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=True,
                         include_virtual=False, act_on_all=True)
        assert 'would:show' in wi.action_taken

    def test_hidden_show_suspicious_only_not_suspicious(self):
        """Hidden + show_hidden + not act_on_all + not suspicious → skip."""
        wi = _make_window(state='hidden', suspicious=False)
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=True,
                         include_virtual=False, act_on_all=False)
        assert wi.action_taken == 'skip:hidden-normal'

    def test_hidden_show_suspicious_only_is_suspicious(self):
        """Hidden + show_hidden + not act_on_all + suspicious → would:show."""
        wi = _make_window(state='hidden', suspicious=True, concern_level=4)
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=True,
                         include_virtual=False, act_on_all=False)
        assert 'would:show' in wi.action_taken

    def test_hidden_no_show_hidden_flag(self):
        """Hidden + show_hidden=False → skip:hidden regardless of mode."""
        wi = _make_window(state='hidden')
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=True)
        assert wi.action_taken == 'skip:hidden'

    def test_minimized_window_always_simulated(self):
        """Minimized windows are always simulated (concern gating is separate)."""
        wi = _make_window(state='minimized')
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=False)
        assert 'would:restore' in wi.action_taken

    def test_hidden_suspicious_foreground(self):
        """Hidden + suspicious at level 2 → would:show includes +foreground."""
        wi = _make_window(state='hidden', suspicious=True, concern_level=2)
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=True,
                         include_virtual=False, act_on_all=False)
        assert '+foreground' in wi.action_taken
        assert 'would:show' in wi.action_taken
        assert '+TOPMOST' not in wi.action_taken

    def test_cloaked_not_suspicious_not_virtual(self):
        """Cloaked + not suspicious + not include_virtual → skip:cloaked."""
        wi = _make_window(state='cloaked')
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=False)
        assert wi.action_taken == 'skip:cloaked'

    def test_cloaked_suspicious(self):
        """Cloaked + suspicious → pulled from desktop."""
        wi = _make_window(state='cloaked', suspicious=True, concern_level=3)
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=False)
        assert 'would:pull-desktop' in wi.action_taken

    def test_suspicious_gets_foreground(self):
        """All suspicious windows include +foreground in dry-run action."""
        wi = _make_window(state='normal', suspicious=True, concern_level=4)
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=True)
        assert '+foreground' in wi.action_taken

    def test_non_suspicious_no_foreground(self):
        """Non-suspicious windows do not include +foreground."""
        wi = _make_window(state='normal')
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=True)
        assert '+foreground' not in wi.action_taken

    def test_suspicious_level3_gets_foreground(self):
        """Level 3 suspicious gets +foreground, no TOPMOST."""
        wi = _make_window(state='normal', suspicious=True, concern_level=3)
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=True)
        assert '+foreground' in wi.action_taken
        assert '+TOPMOST' not in wi.action_taken

    def test_suspicious_level4_gets_foreground(self):
        """Level 4 suspicious gets +foreground, no TOPMOST."""
        wi = _make_window(state='normal', suspicious=True, concern_level=4)
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=True)
        assert '+foreground' in wi.action_taken
        assert '+TOPMOST' not in wi.action_taken


class TestCascadeOffsets:
    """Test cascade positioning offset computation."""

    def test_single_window_centered(self):
        """Single suspicious window has offset (0, 0) — dead center."""
        from wingather.core import _compute_cascade_offsets
        offsets = _compute_cascade_offsets(1)
        assert offsets == [(0, 0)]

    def test_two_windows_center_and_offset(self):
        """Two windows: one at center, one offset."""
        from wingather.core import _compute_cascade_offsets, CASCADE_RADIUS
        offsets = _compute_cascade_offsets(2)
        assert offsets[0] == (0, 0)
        assert offsets[1] == (-CASCADE_RADIUS, -CASCADE_RADIUS)

    def test_five_windows_all_unique(self):
        """Five windows get five unique positions."""
        from wingather.core import _compute_cascade_offsets
        offsets = _compute_cascade_offsets(5)
        assert len(offsets) == 5
        assert len(set(offsets)) == 5  # all unique

    def test_zero_windows(self):
        """Zero count returns empty list."""
        from wingather.core import _compute_cascade_offsets
        assert _compute_cascade_offsets(0) == []

    def test_cascade_offset_in_simulation(self):
        """Suspicious window with offset has adjusted target position."""
        wi = _make_window(state='normal', suspicious=True, concern_level=3)
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=True,
                         offset_x=60, offset_y=-60)
        # Center of 1920x1080 for 800x600 window = (560, 240)
        # With offset (+60, -60) = (620, 180)
        assert wi.target_x == 620
        assert wi.target_y == 180

    def test_cascade_offset_clamped_to_bounds(self):
        """Large offsets are clamped to work area bounds."""
        wi = _make_window(state='normal', suspicious=True, concern_level=5,
                         width=800, height=600)
        _simulate_window(wi, 0, 0, 1920, 1080, show_hidden=False,
                         include_virtual=False, act_on_all=True,
                         offset_x=2000, offset_y=2000)
        # Should be clamped: max x = 1920 - 800 = 1120, max y = 1080 - 600 = 480
        assert wi.target_x == 1120
        assert wi.target_y == 480


class TestShowHiddenBanner:
    """Test the educational banner output for --show-hidden."""

    def test_banner_suspicious_only_mode(self, capsys):
        from wingather.cli import _print_show_hidden_banner
        _print_show_hidden_banner(gather_all=False)
        output = capsys.readouterr().out
        assert 'hidden windows are typically system internals' in output.lower()
        assert 'suspicious hidden windows only' in output.lower()
        assert '--undo' in output

    def test_banner_all_mode(self, capsys):
        from wingather.cli import _print_show_hidden_banner
        _print_show_hidden_banner(gather_all=True)
        output = capsys.readouterr().out
        assert 'hidden windows are typically system internals' in output.lower()
        assert 'showing all hidden windows' in output.lower()

    def test_banner_references_docs(self, capsys):
        from wingather.cli import _print_show_hidden_banner
        _print_show_hidden_banner(gather_all=False)
        output = capsys.readouterr().out
        assert 'hidden-windows.md' in output


class TestAutoTrustMicrosoft:
    """Test auto-trust for Microsoft-signed binaries with LOLBin exclusion."""

    def test_microsoft_signed_gets_trusted(self):
        """A suspicious Microsoft-signed non-LOLBin should be auto-trusted."""
        from wingather.core import _auto_trust_microsoft
        import os

        wi = _make_window(state='normal', suspicious=True, concern_level=3)
        wi.exe_path = 'C:\\Program Files\\Windows Media Player\\wmplayer.exe'
        wi.suspicious_reason = 'shrunk(1180x55)'
        wi.concern_score = 3

        norm = os.path.normcase(os.path.normpath(wi.exe_path))
        sig_cache = {norm: {'valid': True, 'is_os_binary': True, 'signer': 'Microsoft'}}
        lolbins = {'cmd.exe', 'powershell.exe'}

        _auto_trust_microsoft([wi], sig_cache, lolbins)

        assert wi.trusted
        assert not wi.suspicious
        assert wi.trust_source == 'microsoft-signed'
        assert wi.would_flag_reason == 'shrunk(1180x55)'

    def test_lolbin_stays_suspicious(self):
        """A suspicious Microsoft-signed LOLBin should NOT be auto-trusted."""
        from wingather.core import _auto_trust_microsoft
        import os

        wi = _make_window(state='hidden', suspicious=True, concern_level=2)
        wi.process_name = 'mshta.exe'
        wi.exe_path = 'C:\\Windows\\System32\\mshta.exe'
        wi.suspicious_reason = 'off-screen'
        wi.concern_score = 4

        norm = os.path.normcase(os.path.normpath(wi.exe_path))
        sig_cache = {norm: {'valid': True, 'is_os_binary': True, 'signer': 'Microsoft'}}
        lolbins = {'mshta.exe', 'cmd.exe', 'powershell.exe'}

        _auto_trust_microsoft([wi], sig_cache, lolbins)

        assert wi.suspicious
        assert not wi.trusted
        assert wi.concern_level == 2

    def test_unsigned_stays_suspicious(self):
        """A suspicious window without valid MS signature stays suspicious."""
        from wingather.core import _auto_trust_microsoft
        import os

        wi = _make_window(state='normal', suspicious=True, concern_level=4)
        wi.exe_path = 'C:\\SomeApp\\shady.exe'
        wi.suspicious_reason = 'dialog(#32770)'
        wi.concern_score = 2

        norm = os.path.normcase(os.path.normpath(wi.exe_path))
        sig_cache = {norm: {'valid': False, 'is_os_binary': False, 'signer': ''}}
        lolbins = set()

        _auto_trust_microsoft([wi], sig_cache, lolbins)

        assert wi.suspicious
        assert not wi.trusted

    def test_no_exe_path_skipped(self):
        """Windows without exe_path are skipped (no crash)."""
        from wingather.core import _auto_trust_microsoft

        wi = _make_window(state='normal', suspicious=True, concern_level=4)
        wi.exe_path = None

        _auto_trust_microsoft([wi], {}, set())

        assert wi.suspicious

    def test_lolbins_load(self):
        """LOLBin list loads and contains expected entries."""
        from wingather.core import _load_lolbins
        lolbins = _load_lolbins()
        assert 'cmd.exe' in lolbins
        assert 'powershell.exe' in lolbins
        assert 'mshta.exe' in lolbins
        assert 'rundll32.exe' in lolbins
        # Non-LOLBin should not be in the list
        assert 'wmplayer.exe' not in lolbins
        assert 'notepad.exe' not in lolbins


class TestGatherWindowsModeGating:
    """Test that gather_windows() respects gather_all for normal windows.

    Uses mocked platform to avoid Win32 dependency.
    """

    def _make_mock_platform(self, windows):
        """Create a minimal mock platform returning pre-built windows."""
        from unittest.mock import MagicMock
        platform = MagicMock()
        platform.setup.return_value = None
        platform.is_elevated.return_value = True
        platform.get_monitor_work_area.return_value = (0, 0, 1920, 1080)
        platform.enumerate_windows.return_value = windows
        platform.restore_window.return_value = True
        platform.show_window.return_value = True
        platform.center_window.return_value = True
        return platform

    def test_default_mode_skips_normal(self):
        """Default mode (gather_all=False): normal windows get skip:normal."""
        from unittest.mock import patch

        wi_normal = _make_window(state='normal')
        wi_suspicious = _make_window(state='off-screen', suspicious=True, concern_level=2)

        platform = self._make_mock_platform([wi_normal, wi_suspicious])

        with patch('wingather.core.get_platform', return_value=platform), \
             patch('wingather.core._flag_suspicious'):
            from wingather.core import gather_windows
            results = gather_windows(dry_run=True, gather_all=False)

        actions = {w.process_name: w.action_taken for w in results}
        # Both have same process_name, so check the list
        normal_actions = [w.action_taken for w in results if not w.suspicious]
        suspicious_actions = [w.action_taken for w in results if w.suspicious]

        assert all('skip:normal' == a for a in normal_actions)
        assert all('would:' in a for a in suspicious_actions)

    def test_all_mode_processes_everything(self):
        """--all mode (gather_all=True): normal windows get processed."""
        from unittest.mock import patch

        wi_normal = _make_window(state='normal')
        platform = self._make_mock_platform([wi_normal])

        with patch('wingather.core.get_platform', return_value=platform), \
             patch('wingather.core._flag_suspicious'):
            from wingather.core import gather_windows
            results = gather_windows(dry_run=True, gather_all=True)

        assert results[0].action_taken == 'would:center'

    def test_filter_overrides_mode(self):
        """--filter implicitly overrides suspicious-only restriction."""
        from unittest.mock import patch

        wi_normal = _make_window(state='normal')
        platform = self._make_mock_platform([wi_normal])

        with patch('wingather.core.get_platform', return_value=platform), \
             patch('wingather.core._flag_suspicious'), \
             patch('wingather.core._apply_filters', return_value=[wi_normal]):
            from wingather.core import gather_windows
            results = gather_windows(dry_run=True, gather_all=False,
                                     filter_pattern='*test*')

        assert results[0].action_taken == 'would:center'
