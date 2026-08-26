"""godotforge-adapter-nl's rejection_log.py — the persistence layer for
adapter-declined ("doesn't fit any template") descriptions, which Phase 3
of the roadmap depends on as its real prioritization backlog.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from godotforge_adapter_nl.rejection_log import (
    log_rejection,
    read_rejections,
    rejection_log_path,
)


def test_rejection_log_path_defaults_under_dot_godotforge(tmp_path: Path) -> None:
    path = rejection_log_path(tmp_path)
    assert path == tmp_path / ".godotforge" / "adapter-nl" / "rejections.jsonl"


def test_log_rejection_writes_one_json_line(tmp_path: Path) -> None:
    log_path = tmp_path / "rejections.jsonl"
    written = log_rejection("a farming simulator", "not a supported genre yet", log_path=log_path)
    assert written == log_path
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["description"] == "a farming simulator"
    assert entry["reason"] == "not a supported genre yet"
    assert entry["schema_version"] == 1
    assert "timestamp" in entry


def test_log_rejection_creates_parent_directories(tmp_path: Path) -> None:
    log_path = tmp_path / "nested" / "dir" / "rejections.jsonl"
    log_rejection("desc", "reason", log_path=log_path)
    assert log_path.is_file()


def test_log_rejection_appends_without_truncating(tmp_path: Path) -> None:
    log_path = tmp_path / "rejections.jsonl"
    log_rejection("first", "reason one", log_path=log_path)
    log_rejection("second", "reason two", log_path=log_path)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["description"] == "first"
    assert json.loads(lines[1])["description"] == "second"


def test_read_rejections_returns_empty_list_when_no_log_exists(tmp_path: Path) -> None:
    assert read_rejections(log_path=tmp_path / "does-not-exist.jsonl") == []


def test_read_rejections_round_trips_entries(tmp_path: Path) -> None:
    log_path = tmp_path / "rejections.jsonl"
    log_rejection("a", "reason a", log_path=log_path)
    log_rejection("b", "reason b", log_path=log_path)
    entries = read_rejections(log_path=log_path)
    assert [e["description"] for e in entries] == ["a", "b"]


def test_read_rejections_raises_on_corrupt_line(tmp_path: Path) -> None:
    log_path = tmp_path / "rejections.jsonl"
    log_path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="corrupt rejection log"):
        read_rejections(log_path=log_path)
