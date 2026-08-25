"""UID — deterministic, pattern, repeat equality, no machine deps."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.creator.uid import deterministic_uid, is_valid_uid


def test_uid_pattern() -> None:
    uid = deterministic_uid("2d-platformer-minimal", 1, "scenes/main.tscn")
    assert is_valid_uid(uid)
    assert re.match(r"^uid://[a-z0-9]{13}$", uid)


def test_uid_deterministic_and_distinct_per_path() -> None:
    a = deterministic_uid("2d-platformer-minimal", 1, "scenes/main.tscn")
    b = deterministic_uid("2d-platformer-minimal", 1, "scenes/main.tscn")
    c = deterministic_uid("2d-platformer-minimal", 1, "scripts/player_controller.gd")
    assert a == b
    assert a != c


def test_uid_no_randomness_or_host_in_suffix() -> None:
    # 13 lower alphanum, never contains host-like path
    uid = deterministic_uid("2d-platformer-minimal", 1, "scenes/main.tscn")
    suffix = uid.removeprefix("uid://")
    assert suffix.isalnum() and suffix.islower()
    assert len(suffix) == 13


def test_scene_uid_in_tscn_is_valid(tmp_path: Path) -> None:
    manifest = {
        "schema_version": 1,
        "game": {"name": "X", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }
    patch = plan_creator_manifest(tmp_path, manifest)
    tscn = patch.desired_contents["scenes/main.tscn"].decode()
    m = re.search(r'uid="([^"]+)"', tscn)
    assert m is not None
    assert is_valid_uid(m.group(1))


def test_repeat_scene_uid_equal(tmp_path: Path) -> None:
    manifest = {
        "schema_version": 1,
        "game": {"name": "Repeat", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }
    p1 = plan_creator_manifest(tmp_path, manifest)
    p2 = plan_creator_manifest(Path(tempfile.mkdtemp()), manifest)
    t1 = p1.desired_contents["scenes/main.tscn"]
    t2 = p2.desired_contents["scenes/main.tscn"]
    assert t1 == t2
