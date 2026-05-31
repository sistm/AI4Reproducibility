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
