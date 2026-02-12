"""Tests for table rendering utilities."""

import pytest
from wingather.cli import _render_wrapped, _safe_str


class TestSafeStr:
    """Verify safe string encoding for console output."""

    def test_ascii_passthrough(self):
        assert _safe_str("hello world") == "hello world"

    def test_common_unicode(self):
        result = _safe_str("café")
        assert isinstance(result, str)

    def test_empty_string(self):
        assert _safe_str("") == ""


class TestRenderWrapped:
    """Verify column-position table rendering with overflow wrapping."""

    def test_simple_row(self):
        parts = [(0, "AAA"), (10, "BBB"), (20, "CCC")]
        result = _render_wrapped(parts)
        assert "AAA" in result
        assert "BBB" in result
        assert "CCC" in result

    def test_single_line_no_overflow(self):
        parts = [(0, "Hi"), (10, "There")]
        result = _render_wrapped(parts)
        lines = result.split("\n")
        assert len(lines) == 1

    def test_overflow_wraps_to_next_line(self):
        """When a field overflows past the next field's start, wrap."""
        parts = [(0, "A very long first field that overflows"), (10, "B")]
        result = _render_wrapped(parts)
        lines = result.split("\n")
        assert len(lines) == 2

    def test_empty_parts(self):
        result = _render_wrapped([])
        assert result == ""

    def test_column_alignment(self):
        """Fields should start at their specified column positions."""
        parts = [(0, "A"), (5, "B"), (10, "C")]
        result = _render_wrapped(parts)
        lines = result.split("\n")
        assert len(lines) == 1
        assert lines[0].index("A") == 0
        assert lines[0].index("B") == 5
        assert lines[0].index("C") == 10
