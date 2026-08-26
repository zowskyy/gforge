"""Six-op slice — ordering, no-op, preflight A/B/C, positions, UID, determinism."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from godotforge_core.creator.manifest import CreatorPreflightError
from godotforge_core.creator.plan import (
    COIN_POS,
    COIN_RADIUS,
    GROUND_POS,
    GROUND_SIZE,
    PLAYER_POS,
    PLAYER_RADIUS,
    plan_creator_manifest,
)
from godotforge_core.patch.hashing import compute_plan_hash, hash_bytes


def _manifest_dict(name: str = "Dodge Hop") -> dict:
    return {
        "schema_version": 1,
        "game": {"name": name, "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }


# --- operation ordering (single rule) ---


def test_six_ops_in_kind_then_path_order(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict())
    assert patch.plan is not None
    ops = patch.plan.operations
    assert len(ops) == 6
    assert [(o.kind.value, o.path) for o in ops] == [
        ("mkdir", "scenes"),
        ("mkdir", "scripts"),
        ("create", "project.godot"),
        ("create", "scenes/main.tscn"),
        ("create", "scripts/coin.gd"),
        ("create", "scripts/player_controller.gd"),
    ]
    # Invariant: mkdir before create, each sorted lexicographically
    assert [o.path for o in ops[:2]] == sorted(o.path for o in ops[:2])
    assert [o.path for o in ops[2:]] == sorted(o.path for o in ops[2:])


def test_desired_hash_matches_bytes(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict())
    assert patch.plan is not None
    for op in patch.plan.operations:
        if op.kind.value == "create":
            assert op.desired_hash == hash_bytes(patch.desired_contents[op.path])


# --- no-op — separated file/dir checks ---


def test_no_op_requires_both_files_and_dirs(tmp_path: Path) -> None:
    d = _manifest_dict()
    patch = plan_creator_manifest(tmp_path, d)
    assert patch.plan is not None
    # Materialize files (parent mkdir creates dirs)
    for rel, data in patch.desired_contents.items():
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    # Dirs exist now, so should be no-op
    patch2 = plan_creator_manifest(tmp_path, d)
    assert patch2.plan is None
    # Remove one file — files_ok false → plan not None even though dirs_ok true
    (tmp_path / "scripts/coin.gd").unlink()
    patch3 = plan_creator_manifest(tmp_path, d)
    assert patch3.plan is not None
    (tmp_path / "scripts/coin.gd").write_bytes(patch.desired_contents["scripts/coin.gd"])
    patch4 = plan_creator_manifest(tmp_path, d)
    assert patch4.plan is None
    # Remove a dir — dirs_ok false → plan not None
    import shutil

    shutil.rmtree(tmp_path / "scripts")
    patch5 = plan_creator_manifest(tmp_path, d)
    assert patch5.plan is not None


# --- preflight A/B/C ---


def test_preflight_state_a_empty_root(tmp_path: Path) -> None:
    d = _manifest_dict()
    patch = plan_creator_manifest(tmp_path, d)
    assert patch.plan is not None


def test_preflight_state_b_skeleton_and_empty_dirs(tmp_path: Path) -> None:
    (tmp_path / ".godotforge").mkdir()
    (tmp_path / ".godotforge/project.yaml").write_text("name: test\n")
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scripts").mkdir()
    d = _manifest_dict()
    patch = plan_creator_manifest(tmp_path, d)
    assert patch.plan is not None


def test_preflight_state_b_with_lock(tmp_path: Path) -> None:
    (tmp_path / ".godotforge").mkdir()
    (tmp_path / ".godotforge/project.yaml").write_text("name: test\n")
    (tmp_path / ".godotforge/project.lock").write_text('{"version":"4.7"}\n')
    (tmp_path / "scenes").mkdir()
    d = _manifest_dict()
    patch = plan_creator_manifest(tmp_path, d)
    assert patch.plan is not None


def test_preflight_state_c_exact_hash_no_op(tmp_path: Path) -> None:
    d = _manifest_dict()
    patch = plan_creator_manifest(tmp_path, d)
    assert patch.plan is not None
    for rel, data in patch.desired_contents.items():
        fp = tmp_path / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    (tmp_path / ".godotforge").mkdir(exist_ok=True)
    (tmp_path / ".godotforge/project.yaml").write_text("name: preserved\n")
    patch2 = plan_creator_manifest(tmp_path, d)
    assert patch2.plan is None
    # Skeleton preserved check: yaml still there and not overwritten (no plan => no write)
    assert (tmp_path / ".godotforge/project.yaml").read_text() == "name: preserved\n"


def test_preflight_rejects_unexpected_file(tmp_path: Path) -> None:
    (tmp_path / "unexpected.txt").write_text("oops")
    with pytest.raises(CreatorPreflightError, match="unexpected file"):
        plan_creator_manifest(tmp_path, _manifest_dict())


def test_preflight_rejects_gd_uid_without_policy(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/foo.gd.uid").write_text("uid://abc\n")
    with pytest.raises(CreatorPreflightError, match="unexpected file"):
        plan_creator_manifest(tmp_path, _manifest_dict())


def test_preflight_rejects_non_empty_scenes_with_stray_file(tmp_path: Path) -> None:
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes/extra.tscn").write_text("[gd_scene]\n")
    with pytest.raises(CreatorPreflightError, match="unexpected file"):
        plan_creator_manifest(tmp_path, _manifest_dict())


# --- Hub control-plane preflight exemption (remediation for the confirmed
# path-safety defect: the exemption is now an exact allowlist delegated to
# godotforge_core.hub_control_plane, not a `.startswith()` prefix) ---


def test_preflight_accepts_exact_hub_metadata_files(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    (hub_dir / "run-records.jsonl").write_text('{"seq":1}\n')
    (hub_dir / "spoke-ledger.jsonl").write_text('{"seq":1}\n')
    patch = plan_creator_manifest(tmp_path, _manifest_dict())
    assert patch.plan is not None


def test_preflight_rejects_arbitrary_hub_file(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    (hub_dir / "foo.txt").write_text("nope\n")
    with pytest.raises(CreatorPreflightError, match="unexpected Hub control-plane entry"):
        plan_creator_manifest(tmp_path, _manifest_dict())


def test_preflight_rejects_nested_hub_file(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    nested = hub_dir / "sub"
    nested.mkdir(parents=True)
    (nested / "run-records.jsonl").write_text("{}\n")
    with pytest.raises(CreatorPreflightError, match="unexpected Hub control-plane entry"):
        plan_creator_manifest(tmp_path, _manifest_dict())


@pytest.mark.parametrize(
    "rel",
    [
        ".godotforge/hubris.txt",
        ".godotforge/backupsExtra",
        ".godotforge/reportsFake",
        ".godotforge/cacheOverflow",
    ],
)
def test_preflight_rejects_prefix_confusable_godotforge_names(tmp_path: Path, rel: str) -> None:
    """These share a string prefix with an exempted path but are not inside
    it — the old `.startswith()` check (no trailing slash) silently let them
    through; the anchored replacement must reject them."""
    fp = tmp_path / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("oops\n")
    with pytest.raises(CreatorPreflightError, match="unexpected file"):
        plan_creator_manifest(tmp_path, _manifest_dict())


def test_preflight_rejects_hub_metadata_target_symlink_real(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    real_target = tmp_path / "project.godot"
    real_target.write_text("config_version=5\n")
    link = hub_dir / "run-records.jsonl"
    try:
        link.symlink_to(real_target)
    except OSError:
        pytest.skip("host cannot create symlinks (elevated privilege / Developer Mode required)")
    with pytest.raises(CreatorPreflightError, match="symlink"):
        plan_creator_manifest(tmp_path, _manifest_dict())


def test_preflight_rejects_hub_metadata_target_symlink_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import stat

    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    link = hub_dir / "run-records.jsonl"
    link.write_text("placeholder\n")
    real_lstat = os.lstat

    def _fake_lstat(path, *, dir_fd=None):  # noqa: ANN001
        if Path(path) == link:
            return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    monkeypatch.setattr(os, "lstat", _fake_lstat)
    with pytest.raises(CreatorPreflightError, match="symlink"):
        plan_creator_manifest(tmp_path, _manifest_dict())


def test_preflight_rejects_hub_dir_symlink_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import stat

    (tmp_path / ".godotforge").mkdir()
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir()
    real_lstat = os.lstat

    def _fake_lstat(path, *, dir_fd=None):  # noqa: ANN001
        if Path(path) == hub_dir:
            return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    monkeypatch.setattr(os, "lstat", _fake_lstat)
    with pytest.raises(CreatorPreflightError, match="symlink"):
        plan_creator_manifest(tmp_path, _manifest_dict())


def test_hub_metadata_excluded_from_plan_hash_and_g_files(tmp_path: Path) -> None:
    """Hub run-record presence must not affect planHash or G_file ownership."""
    from godotforge_core.patch.hashing import compute_plan_hash
    from godotforge_core.patch.models import OperationKind

    plain = tmp_path / "plain"
    plain.mkdir()
    with_hub = tmp_path / "with_hub"
    with_hub.mkdir()
    hub_dir = with_hub / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    (hub_dir / "run-records.jsonl").write_text('{"seq":1}\n')
    (hub_dir / "spoke-ledger.jsonl").write_text('{"seq":1}\n')

    patch_plain = plan_creator_manifest(plain, _manifest_dict())
    patch_hub = plan_creator_manifest(with_hub, _manifest_dict())
    assert patch_plain.plan is not None
    assert patch_hub.plan is not None
    assert compute_plan_hash(patch_plain.plan) == compute_plan_hash(patch_hub.plan)
    plan_plain, plan_hub = patch_plain.plan, patch_hub.plan
    assert plan_plain is not None
    assert plan_hub is not None
    for op in (*plan_plain.operations, *plan_hub.operations):
        assert op.kind is not OperationKind.CREATE or not (op.path or "").startswith(".godotforge")


def test_preflight_normal_project_unaffected_by_hub_state(tmp_path: Path) -> None:
    """Skeleton state B plus valid Hub metadata plans exactly as without it."""
    (tmp_path / ".godotforge").mkdir()
    (tmp_path / ".godotforge/project.yaml").write_text("name: test\n")
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir()
    (hub_dir / "run-records.jsonl").write_text('{"seq":1}\n')
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scripts").mkdir()
    patch = plan_creator_manifest(tmp_path, _manifest_dict())
    assert patch.plan is not None


# --- positions and collision dims ---


def test_positions_and_collision_constants() -> None:
    assert PLAYER_POS == (0, 48)
    assert GROUND_POS == (0, 128)
    assert GROUND_SIZE == (800, 32)
    assert PLAYER_RADIUS == 16
    assert COIN_RADIUS == 12
    assert COIN_POS == (160, 100)


def test_scene_bytes_contain_positions(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest_dict())
    tscn = patch.desired_contents["scenes/main.tscn"].decode()
    assert "position = Vector2(0, 48)" in tscn  # Player
    assert "position = Vector2(0, 128)" in tscn  # Ground
    assert "position = Vector2(160, 100)" in tscn  # Coin resting
    assert "radius = 16.0" in tscn
    assert "radius = 12.0" in tscn
    assert "size = Vector2(800, 32)" in tscn


# --- determinism and plan id ---


def test_repeat_generation_byte_equality(tmp_path: Path) -> None:
    d = _manifest_dict()
    p1 = plan_creator_manifest(tmp_path, d)
    p2 = plan_creator_manifest(Path(tempfile.mkdtemp()), d)
    assert p1.plan is not None and p2.plan is not None
    assert p1.plan.id == p2.plan.id
    assert compute_plan_hash(p1.plan) == compute_plan_hash(p2.plan)
    for rel in p1.desired_contents:
        assert p1.desired_contents[rel] == p2.desired_contents[rel]


def test_different_name_changes_plan_and_bytes(tmp_path: Path) -> None:
    p1 = plan_creator_manifest(tmp_path, _manifest_dict("Alpha"))
    p2 = plan_creator_manifest(Path(tempfile.mkdtemp()), _manifest_dict("Beta"))
    assert p1.plan is not None and p2.plan is not None
    assert p1.plan.id != p2.plan.id
    assert p1.desired_contents["project.godot"] != p2.desired_contents["project.godot"]
