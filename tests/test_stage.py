"""Tests for the shared stage helpers (tools/orchestrator/_stage.py)."""

from __future__ import annotations

import json

import pytest

from tools.orchestrator._stage import (
    append_log,
    is_kebab,
    load_skill,
    now_iso,
    parse_json_object,
)


def test_is_kebab():
    assert is_kebab("a-paper-2024")
    assert is_kebab("p")
    assert not is_kebab("Not Kebab")
    assert not is_kebab("-leading-hyphen")
    assert not is_kebab("Upper")
    assert not is_kebab("")


def test_now_iso_is_utc_isoformat():
    ts = now_iso()
    # Parses back and is timezone-aware UTC.
    from datetime import datetime

    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_parse_json_object_plain():
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_parse_json_object_fenced():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('```\n{"b": 2}\n```') == {"b": 2}


def test_parse_json_object_rejects_non_object():
    with pytest.raises(ValueError):
        parse_json_object("[1, 2, 3]")
    with pytest.raises(json.JSONDecodeError):
        parse_json_object("not json")


def test_load_skill_reads_agent_skill():
    text = load_skill("review/SKILL.md")
    assert isinstance(text, str) and text.strip()


def test_append_log_creates_dir_and_timestamps(tmp_path):
    review_dir = tmp_path / "ai4r" / "p"
    review_dir.mkdir(parents=True)
    append_log(review_dir, "KBE status=success mode=-")
    append_log(review_dir, "CQV status=failed mode=x")
    log = (review_dir / "logs" / "workflow.log").read_text()
    lines = log.splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("KBE status=success mode=-")
    assert lines[1].endswith("CQV status=failed mode=x")
    # each line is "<iso-timestamp> <message>"
    for ln in lines:
        ts = ln.split(" ", 1)[0]
        from datetime import datetime

        datetime.fromisoformat(ts)  # raises if not a valid timestamp


# --- patch 0066: doubled-key stutter pre-pass --------------------------------


def test_strip_doubled_key_stutter_no_match_returns_input_unchanged():
    """Stutter-free text is returned verbatim with count 0 — confirms the
    pre-pass is a no-op on healthy output (its dominant case)."""
    from tools.orchestrator._stage import strip_doubled_key_stutter

    healthy = '{"status": "success", "items": [{"file": "main.R", "line": 12}]}'
    out, n = strip_doubled_key_stutter(healthy)
    assert out == healthy
    assert n == 0


def test_strip_doubled_key_stutter_fixes_single_occurrence():
    """The exact smoke-C pattern: `"file": "file":` collapses to `"file":`."""
    from tools.orchestrator._stage import strip_doubled_key_stutter

    stuttered = '{"file": "file": "code/DoFiguresTables.R", "line": 26}'
    out, n = strip_doubled_key_stutter(stuttered)
    assert out == '{"file": "code/DoFiguresTables.R", "line": 26}'
    assert n == 1


def test_strip_doubled_key_stutter_fixes_multiple_occurrences():
    """Multiple stutters in one payload all get collapsed; count reflects the
    total (matters for the observability marker in CQV notes)."""
    from tools.orchestrator._stage import strip_doubled_key_stutter

    multi = (
        '{"file": "file": "a.R", "line": 1}, '
        '{"file": "b.R", "line": 2}, '
        '{"file": "file": "c.R", "line": 3}'
    )
    out, n = strip_doubled_key_stutter(multi)
    assert n == 2
    assert '"file": "file"' not in out


def test_strip_doubled_key_stutter_works_on_any_word_key():
    """The pattern is key-name-agnostic (matches via backreference). Future
    runs that stutter on `line` or `id` get the same fix without code changes."""
    from tools.orchestrator._stage import strip_doubled_key_stutter

    for key in ("line", "id", "severity"):
        stuttered = f'{{"{key}": "{key}": "value"}}'
        out, n = strip_doubled_key_stutter(stuttered)
        assert n == 1
        assert out == f'{{"{key}": "value"}}'


def test_strip_doubled_key_stutter_preserves_legitimate_matching_value():
    """A value that happens to equal its key (e.g. `{"file": "file"}` where the
    file IS literally named "file") is NOT modified. The stutter pattern
    requires a trailing colon after the second occurrence — which is invalid
    JSON in any case where the second `"file"` is a value."""
    from tools.orchestrator._stage import strip_doubled_key_stutter

    legitimate = '{"file": "file", "line": 1}'  # value just happens to equal key
    out, n = strip_doubled_key_stutter(legitimate)
    assert out == legitimate
    assert n == 0


def test_strip_doubled_key_stutter_is_idempotent():
    """Applying twice yields the same result as once — important because the
    helper sits in a hot path and may be hit multiple times in test setups."""
    from tools.orchestrator._stage import strip_doubled_key_stutter

    stuttered = '{"file": "file": "x.R", "line": 1}'
    once, n1 = strip_doubled_key_stutter(stuttered)
    twice, n2 = strip_doubled_key_stutter(once)
    assert once == twice
    assert n1 == 1
    assert n2 == 0


def test_strip_doubled_key_stutter_tolerates_whitespace_between():
    """`"X":\\n"X":` (whitespace, including newlines, between key and stutter)
    still matches — handles models that pretty-print across line breaks."""
    from tools.orchestrator._stage import strip_doubled_key_stutter

    stuttered = '{"file":\n  "file":\n  "x.R"}'
    out, n = strip_doubled_key_stutter(stuttered)
    assert n == 1
    assert '"file"' in out and '"file": "file"' not in out
