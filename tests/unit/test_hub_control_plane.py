"""Unit tests for the Hub control-plane path policy (sole authority).

Covers the exact-allowlist semantics of ``godotforge_core.hub_control_plane``:
only the two known Hub metadata files are ever recognized, every parent in
the chain must be a real (non-symlink) directory, every target must be a
real (non-symlink) regular file, and nothing escapes the project root.

Real symlinks are exercised where the host supports them (skipped
otherwise, matching the existing ``test_creator_verify.py`` convention);
each real-symlink test is paired with an ``os.lstat``-monkeypatched
simulation so the regression always runs, including on hosts (such as
unprivileged Windows) that cannot create symlinks.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from godotforge_core.hub_control_plane import (
    HUB_METADATA_FILES,
    PLAN_CACHE_RELATIVE,
    RUN_RECORDS_RELATIVE,
    SPOKE_LEDGER_RELATIVE,
    HubPathSafetyError,
    ensure_hub_metadata_parents,
    is_hub_metadata_relpath,
    resolve_hub_metadata_path,
    validate_hub_metadata_dir,
)


def _fake_symlink_lstat(monkeypatch: pytest.MonkeyPatch, *targets: Path) -> None:
    """Make ``os.lstat`` report a symlink for exactly `targets`, real otherwise."""
    real_lstat = os.lstat
    resolved_targets = {Path(t) for t in targets}

    def _lstat(path, *, dir_fd=None):  # noqa: ANN001
        if Path(path) in resolved_targets:
            return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    monkeypatch.setattr(os, "lstat", _lstat)


# --- constants / classification ---


def test_exact_three_control_plane_files() -> None:
    assert HUB_METADATA_FILES == (RUN_RECORDS_RELATIVE, SPOKE_LEDGER_RELATIVE, PLAN_CACHE_RELATIVE)
    assert RUN_RECORDS_RELATIVE == ".godotforge/hub/run-records.jsonl"
    assert SPOKE_LEDGER_RELATIVE == ".godotforge/hub/spoke-ledger.jsonl"
    assert PLAN_CACHE_RELATIVE == ".godotforge/hub/plan-cache.jsonl"


def test_is_hub_metadata_relpath_exact_only() -> None:
    assert is_hub_metadata_relpath(RUN_RECORDS_RELATIVE)
    assert is_hub_metadata_relpath(SPOKE_LEDGER_RELATIVE)
    assert is_hub_metadata_relpath(PLAN_CACHE_RELATIVE)
    assert not is_hub_metadata_relpath(".godotforge/hub/foo.txt")
    assert not is_hub_metadata_relpath(".godotforge/hub/run-records.jsonl.bak")
    assert not is_hub_metadata_relpath(".godotforge/hubris.txt")


# --- validate_hub_metadata_dir ---


def test_validate_hub_metadata_dir_no_godotforge_is_empty(tmp_path: Path) -> None:
    assert validate_hub_metadata_dir(tmp_path) == frozenset()


def test_validate_hub_metadata_dir_no_hub_subdir_is_empty(tmp_path: Path) -> None:
    (tmp_path / ".godotforge").mkdir()
    (tmp_path / ".godotforge" / "project.yaml").write_text("name: x\n")
    assert validate_hub_metadata_dir(tmp_path) == frozenset()


def test_validate_hub_metadata_dir_accepts_all_three_exact_files(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    (hub_dir / "run-records.jsonl").write_text("{}\n")
    (hub_dir / "spoke-ledger.jsonl").write_text("{}\n")
    (hub_dir / "plan-cache.jsonl").write_text("{}\n")
    assert validate_hub_metadata_dir(tmp_path) == frozenset(HUB_METADATA_FILES)


def test_validate_hub_metadata_dir_accepts_one_exact_file(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    (hub_dir / "run-records.jsonl").write_text("{}\n")
    assert validate_hub_metadata_dir(tmp_path) == frozenset({RUN_RECORDS_RELATIVE})


def test_validate_hub_metadata_dir_rejects_arbitrary_file(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    (hub_dir / "foo.txt").write_text("nope\n")
    with pytest.raises(HubPathSafetyError, match="unexpected Hub control-plane entry"):
        validate_hub_metadata_dir(tmp_path)


def test_validate_hub_metadata_dir_rejects_nested_subdirectory(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    nested = hub_dir / "sub"
    nested.mkdir(parents=True)
    (nested / "run-records.jsonl").write_text("{}\n")
    with pytest.raises(HubPathSafetyError, match="unexpected Hub control-plane entry"):
        validate_hub_metadata_dir(tmp_path)


def test_validate_hub_metadata_dir_rejects_prefix_confusable_name(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    (hub_dir / "run-records.jsonl.bak").write_text("{}\n")
    with pytest.raises(HubPathSafetyError, match="unexpected Hub control-plane entry"):
        validate_hub_metadata_dir(tmp_path)


def test_validate_hub_metadata_dir_rejects_hub_path_as_file(tmp_path: Path) -> None:
    (tmp_path / ".godotforge").mkdir()
    (tmp_path / ".godotforge" / "hub").write_text("not a directory\n")
    with pytest.raises(HubPathSafetyError, match="not a directory"):
        validate_hub_metadata_dir(tmp_path)


def test_validate_hub_metadata_dir_rejects_godotforge_path_as_file(tmp_path: Path) -> None:
    (tmp_path / ".godotforge").write_text("not a directory\n")
    with pytest.raises(HubPathSafetyError, match="not a directory"):
        validate_hub_metadata_dir(tmp_path)


def test_validate_hub_metadata_dir_rejects_target_symlink_real(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    real_target = tmp_path / "project.godot"
    real_target.write_text("config_version=5\n")
    link = hub_dir / "run-records.jsonl"
    try:
        link.symlink_to(real_target)
    except OSError:
        pytest.skip("host cannot create symlinks (elevated privilege / Developer Mode required)")
    with pytest.raises(HubPathSafetyError, match="symlink"):
        validate_hub_metadata_dir(tmp_path)


def test_validate_hub_metadata_dir_rejects_target_symlink_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    link = hub_dir / "run-records.jsonl"
    link.write_text("placeholder\n")  # real file so it exists for the simulation
    _fake_symlink_lstat(monkeypatch, link)
    with pytest.raises(HubPathSafetyError, match="symlink"):
        validate_hub_metadata_dir(tmp_path)


def test_validate_hub_metadata_dir_rejects_hub_dir_symlink_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".godotforge").mkdir()
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir()  # real dir so Path.is_dir() still reports True post-fake-lstat
    _fake_symlink_lstat(monkeypatch, hub_dir)
    with pytest.raises(HubPathSafetyError, match="symlink"):
        validate_hub_metadata_dir(tmp_path)


def test_validate_hub_metadata_dir_rejects_godotforge_symlink_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    godotforge_dir = tmp_path / ".godotforge"
    godotforge_dir.mkdir()
    _fake_symlink_lstat(monkeypatch, godotforge_dir)
    with pytest.raises(HubPathSafetyError, match="symlink"):
        validate_hub_metadata_dir(tmp_path)


# --- resolve_hub_metadata_path ---


def test_resolve_hub_metadata_path_rejects_non_allowlisted_relative(tmp_path: Path) -> None:
    with pytest.raises(HubPathSafetyError, match="not an allowed Hub metadata path"):
        resolve_hub_metadata_path(tmp_path, ".godotforge/hub/foo.txt")


def test_resolve_hub_metadata_path_accepts_nonexistent_target(tmp_path: Path) -> None:
    target = resolve_hub_metadata_path(tmp_path, RUN_RECORDS_RELATIVE)
    assert target == tmp_path / ".godotforge" / "hub" / "run-records.jsonl"
    assert not target.exists()


def test_resolve_hub_metadata_path_rejects_existing_non_regular_target(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    (hub_dir / "run-records.jsonl").mkdir()  # a directory where a file is expected
    with pytest.raises(HubPathSafetyError, match="not a regular file"):
        resolve_hub_metadata_path(tmp_path, RUN_RECORDS_RELATIVE)


def test_resolve_hub_metadata_path_rejects_target_symlink_real(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    real_target = tmp_path / "project.godot"
    real_target.write_text("config_version=5\n")
    link = hub_dir / "run-records.jsonl"
    try:
        link.symlink_to(real_target)
    except OSError:
        pytest.skip("host cannot create symlinks (elevated privilege / Developer Mode required)")
    with pytest.raises(HubPathSafetyError, match="symlink"):
        resolve_hub_metadata_path(tmp_path, RUN_RECORDS_RELATIVE)


def test_resolve_hub_metadata_path_rejects_target_symlink_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    link = hub_dir / "run-records.jsonl"
    link.write_text("placeholder\n")
    _fake_symlink_lstat(monkeypatch, link)
    with pytest.raises(HubPathSafetyError, match="symlink"):
        resolve_hub_metadata_path(tmp_path, RUN_RECORDS_RELATIVE)


def test_resolve_hub_metadata_path_rejects_parent_symlink_real(tmp_path: Path) -> None:
    real_hub_dir = tmp_path / "elsewhere"
    real_hub_dir.mkdir()
    (tmp_path / ".godotforge").mkdir()
    link = tmp_path / ".godotforge" / "hub"
    try:
        link.symlink_to(real_hub_dir, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create symlinks (elevated privilege / Developer Mode required)")
    with pytest.raises(HubPathSafetyError, match="symlink"):
        resolve_hub_metadata_path(tmp_path, RUN_RECORDS_RELATIVE)


def test_resolve_hub_metadata_path_rejects_parent_symlink_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".godotforge").mkdir()
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir()
    _fake_symlink_lstat(monkeypatch, hub_dir)
    with pytest.raises(HubPathSafetyError, match="symlink"):
        resolve_hub_metadata_path(tmp_path, RUN_RECORDS_RELATIVE)


def test_resolve_hub_metadata_path_rejects_in_root_resolving_symlink_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symlink whose target resolves *inside* root is still rejected.

    The generic project-wide symlink-escape scan only raises when a
    symlink's target resolves *outside* root, so an in-root-resolving
    symlink at the Hub metadata path would slip past it. This policy's own
    symlink check is unconditional — it never even reaches ``resolve()`` —
    so an in-root target is rejected exactly the same as an escaping one.
    """
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    other_in_root = tmp_path / "project.godot"
    other_in_root.write_text("config_version=5\n")
    link = hub_dir / "run-records.jsonl"
    link.write_text("placeholder\n")
    _fake_symlink_lstat(monkeypatch, link)
    # Prove the rejection does not depend on where the symlink points: even
    # a target that would resolve safely inside root is rejected.
    monkeypatch.setattr(Path, "resolve", lambda self: other_in_root if self == link else self)
    with pytest.raises(HubPathSafetyError, match="symlink"):
        resolve_hub_metadata_path(tmp_path, RUN_RECORDS_RELATIVE)


# --- ensure_hub_metadata_parents ---


def test_ensure_hub_metadata_parents_creates_dirs_and_returns_target(tmp_path: Path) -> None:
    target = ensure_hub_metadata_parents(tmp_path, RUN_RECORDS_RELATIVE)
    assert target == tmp_path / ".godotforge" / "hub" / "run-records.jsonl"
    assert (tmp_path / ".godotforge" / "hub").is_dir()
    assert not target.exists()  # ensure_* never creates the file itself


def test_ensure_hub_metadata_parents_rejects_symlinked_hub_dir_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".godotforge").mkdir()
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir()
    _fake_symlink_lstat(monkeypatch, hub_dir)
    with pytest.raises(HubPathSafetyError, match="symlink"):
        ensure_hub_metadata_parents(tmp_path, RUN_RECORDS_RELATIVE)
