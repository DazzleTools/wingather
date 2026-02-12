"""Tests for concern scoring and level mapping."""

import pytest
from wingather.core import (
    _score_to_level,
    CONCERN_WEIGHTS,
    TOPMOST_THRESHOLD,
)


class TestScoreToLevel:
    """Verify DEFCON-style score → level mapping."""

    def test_level_1_score_5(self):
        assert _score_to_level(5) == 1

    def test_level_1_score_above_5(self):
        assert _score_to_level(8) == 1
        assert _score_to_level(100) == 1

    def test_level_2_score_4(self):
        assert _score_to_level(4) == 2

    def test_level_3_score_3(self):
        assert _score_to_level(3) == 3

    def test_level_4_score_2(self):
        assert _score_to_level(2) == 4

    def test_level_5_score_1(self):
        assert _score_to_level(1) == 5

    def test_level_5_score_0(self):
        """Score 0 shouldn't happen in practice but should return 5."""
        assert _score_to_level(0) == 5


class TestConcernWeights:
    """Verify concern weight definitions are consistent."""

    def test_off_screen_is_highest_positional(self):
        assert CONCERN_WEIGHTS['off-screen'] > CONCERN_WEIGHTS['partially-off-screen']

    def test_trust_verification_failed_is_highest(self):
        """Masquerading as a trusted process should be the most alarming."""
        max_weight = max(CONCERN_WEIGHTS.values())
        assert CONCERN_WEIGHTS['trust-verification-failed'] == max_weight

    def test_off_screen_alone_triggers_level_2(self):
        """Off-screen (weight 4) alone → level 2."""
        score = CONCERN_WEIGHTS['off-screen']
        assert _score_to_level(score) == 2

    def test_off_screen_plus_dialog_triggers_level_1(self):
        """Off-screen (4) + dialog (2) = 6 → level 1."""
        score = CONCERN_WEIGHTS['off-screen'] + CONCERN_WEIGHTS['dialog']
        assert _score_to_level(score) == 1

    def test_shrunk_alone_triggers_level_3(self):
        """Shrunk (weight 3) alone → level 3."""
        score = CONCERN_WEIGHTS['shrunk']
        assert _score_to_level(score) == 3

    def test_dialog_alone_triggers_level_4(self):
        """Dialog (weight 2) alone → level 4 (flagged but not TOPMOST)."""
        score = CONCERN_WEIGHTS['dialog']
        assert _score_to_level(score) == 4

    def test_cloaked_alone_triggers_level_5(self):
        """Cloaked (weight 1) alone → level 5 (informational)."""
        score = CONCERN_WEIGHTS['cloaked']
        assert _score_to_level(score) == 5

    def test_trust_fail_alone_triggers_level_1(self):
        """Trust verification failure (weight 5) → instant level 1."""
        score = CONCERN_WEIGHTS['trust-verification-failed']
        assert _score_to_level(score) == 1

    def test_topmost_threshold_is_3(self):
        """Levels 1-3 get TOPMOST, levels 4-5 don't."""
        assert TOPMOST_THRESHOLD == 3

    def test_all_weights_are_positive(self):
        for key, weight in CONCERN_WEIGHTS.items():
            assert weight > 0, f"Weight for '{key}' should be positive"
