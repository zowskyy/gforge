"""Unit tests for creator verify — isolated copy, validator, immutability, cleanup."""

from __future__ import annotations

import hashlib
import importlib.resources
from pathlib import Path

import pytest
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.creator.verify import (
    PINNED_VALIDATOR_SHA256,
    _hash_source_files,
    _inject_validator,
    _secure_copy,
    _validator_source_path,
    verify_creator_project,
)

MANIFEST = {
    "schema_version": 1,
    "game": {"name": "VerifyTest", "template": "2d-platformer-minimal"},
    "input": [
        {"name": "move_left", "binding": "ui_left"},
        {"name": "move_right", "binding": "ui_right"},
        {"name": "jump", "binding": "ui_accept"},
    ],
}


def test_validator_source_package_and_hash() -> None:
    """Package-owned validator must be found via importlib.resources and hash pinned."""
    path = _validator_source_path()
    assert path.is_file()
    data = path.read_bytes()
    assert b"extends SceneTree" in data
    assert hashlib.sha256(data).hexdigest() == PINNED_VALIDATOR_SHA256


def test_validator_pin_unchanged_by_patch_0016() -> None:
    """PATCH-0016 §10: PINNED_VALIDATOR_SHA256 holds its pre-PATCH-0016 value.

    v2 parameter inspection uses the temporary-project harness
    (tests/integration/test_creator_v2_godot.py), never validate_boot.gd.
    Changing this literal requires an explicit validator version/hash update
    per the contract amendment procedure.
    """
    assert PINNED_VALIDATOR_SHA256 == (
        "1e01c7a59baa856ebeb4a14d2f39d143640e2162f1fc31aee2d80df69cbd525c"
    )


def test_validator_installed_lookup() -> None:
    """Installed-package lookup via importlib.resources.files must succeed."""
    pkg = importlib.resources.files("godotforge_core.engine") / "validate_boot.gd"
    # Use as_file to handle wheel vs source
    import importlib.resources as res

    with res.as_file(pkg) as p:
        assert Path(p).is_file()
        assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == PINNED_VALIDATOR_SHA256


def test_secure_copy_rejects_symlink_root(tmp_path: Path) -> None:
    """Symlink project root must be rejected."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "project.godot").write_text('config_version=5\n[application]\nconfig/name="X"\n', encoding="utf-8")  # noqa: E501
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create symlinks (elevated privilege / Developer Mode required)")  # noqa: E501
    dst = tmp_path / "dst"
    dst.mkdir()
    with pytest.raises(ValueError, match="symlink project root"):
        _secure_copy(link, dst)


def test_secure_copy_rejects_symlink_root_before_resolve(tmp_path: Path) -> None:
    """F-002: the root symlink check must run on the *unresolved* path.

    Simulated via a Path subclass so this regression runs on hosts without
    symlink privileges; real-symlink coverage is in
    ``test_secure_copy_rejects_symlink_root``.
    """

    class _FakeSymlinkRoot(Path):
        """Simulated symlink root: is_symlink() True without OS support."""

        def is_symlink(self) -> bool:  # type: ignore[override]
            return True

    src = _FakeSymlinkRoot(tmp_path / "link")
    dst = tmp_path / "dst"
    dst.mkdir()
    with pytest.raises(ValueError, match="symlink project root rejected"):
        _secure_copy(src, dst)


def test_secure_copy_rejects_nested_symlink(tmp_path: Path) -> None:
    """Nested symlink inside project must be rejected."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "project.godot").write_text('config_version=5\n', encoding="utf-8")
    (src / "scenes").mkdir()
    target = src / "real.txt"
    target.write_text("real", encoding="utf-8")
    link = src / "scenes" / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("host cannot create symlinks (elevated privilege / Developer Mode required)")  # noqa: E501
    dst = tmp_path / "dst"
    dst.mkdir()
    with pytest.raises(ValueError, match="symlink"):
        _secure_copy(src, dst)


def test_secure_copy_size_limits(tmp_path: Path) -> None:
    """File count and total size limits must be enforced."""
    from godotforge_core.creator.verify import MAX_COPY_BYTES

    src = tmp_path / "src"
    src.mkdir()
    # Create many files to exceed count
    for i in range(10):
        (src / f"file{i}.txt").write_text("x", encoding="utf-8")
    dst = tmp_path / "dst"
    dst.mkdir()
    # Temporarily patch limit to 5
    import godotforge_core.creator.verify as mod

    orig = mod.MAX_COPY_FILES
    mod.MAX_COPY_FILES = 5
    try:
        with pytest.raises(ValueError, match="file count limit"):
            _secure_copy(src, dst)
    finally:
        mod.MAX_COPY_FILES = orig

    # Size limit
    src2 = tmp_path / "src2"
    src2.mkdir()
    big = src2 / "big.bin"
    big.write_bytes(b"x" * 1024)
    mod.MAX_COPY_BYTES = 512
    try:
        with pytest.raises(ValueError, match="total size limit"):
            _secure_copy(src2, dst / "dst2")
    finally:
        mod.MAX_COPY_BYTES = MAX_COPY_BYTES
        mod.MAX_COPY_FILES = orig


def test_secure_copy_prunes_managed(tmp_path: Path) -> None:
    """Managed .godot, cache, backups, reports must not be copied."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "project.godot").write_text('config_version=5\n', encoding="utf-8")
    (src / ".godot").mkdir()
    (src / ".godot" / "cache.bin").write_text("cache", encoding="utf-8")
    (src / ".godotforge").mkdir()
    (src / ".godotforge" / "project.yaml").write_text("name: test\n", encoding="utf-8")
    (src / ".godotforge" / "cache").mkdir()
    (src / ".godotforge" / "cache" / "a.bin").write_text("a", encoding="utf-8")
    (src / ".godotforge" / "backups").mkdir()
    (src / ".godotforge" / "backups" / "tx").write_text("b", encoding="utf-8")
    dst = tmp_path / "dst"
    dst.mkdir()
    _secure_copy(src, dst)
    assert not (dst / ".godot").exists()
    assert not (dst / ".godotforge" / "cache").exists()
    assert not (dst / ".godotforge" / "backups").exists()
    assert (dst / "project.godot").is_file()
    assert (dst / ".godotforge" / "project.yaml").is_file()


def test_inject_validator(tmp_path: Path) -> None:
    """Validator must be injected at .godotforge/validate_boot.gd with pinned hash."""
    dst = tmp_path / "dst"
    dst.mkdir()
    _inject_validator(dst)
    dest = dst / ".godotforge" / "validate_boot.gd"
    assert dest.is_file()
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == PINNED_VALIDATOR_SHA256


def test_source_immutability_and_temp_removed(tmp_path: Path) -> None:
    """Verify leaves source unchanged, no .godot/.gd.uid, temp removed."""
    src = tmp_path / "proj"
    src.mkdir()
    (src / ".godotforge").mkdir()
    (src / ".godotforge" / "project.yaml").write_text("name: test\n", encoding="utf-8")
    # Materialize to State C
    patch = plan_creator_manifest(src, MANIFEST)
    for rel, data in patch.desired_contents.items():
        fp = src / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    before = _hash_source_files(src)
    # Verify with mocked engine (no Godot) — should still copy and inject validator, then fail gracefully (engine missing)  # noqa: E501
    result = verify_creator_project(src, MANIFEST, engine_path=None, timeout=1, mode="import")
    assert result.source_unchanged is True
    assert result.source_before_hash == before
    assert result.source_after_hash == before
    assert result.temp_removed is True
    assert not (src / ".godot").exists()
    assert not any(src.rglob("*.gd.uid"))
    assert not (src / ".godotforge" / "validate_boot.gd").exists()
    # Backups not created by verify
    assert not (src / ".godotforge" / "backups").exists() or not any((src / ".godotforge" / "backups").iterdir())  # noqa: E501


def test_verify_plan_id_and_hash_null(tmp_path: Path) -> None:
    """planId manifest-derived, planHash null for verify."""
    src = tmp_path / "proj"
    src.mkdir()
    result = verify_creator_project(src, MANIFEST, engine_path=None, timeout=1, mode="import")
    assert result.plan_id.startswith("cr-")
    assert result.plan_hash is None
    assert result.source_unchanged is True


def test_verify_rejects_symlink_root_cli_level(tmp_path: Path) -> None:
    """Verify should reject symlink root even before copy."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "project.godot").write_text('config_version=5\n', encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create symlinks (elevated privilege / Developer Mode required)")  # noqa: E501
    with pytest.raises(ValueError, match="symlink"):
        verify_creator_project(link, MANIFEST, engine_path=None, timeout=1, mode="import")


def test_verify_rejects_symlink_root_before_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-002: core verify rejects a symlinked root before resolve()/copy/Godot.

    ``is_symlink`` is simulated via monkeypatch so this regression runs on
    hosts without symlink privileges; real-symlink coverage is in
    ``test_verify_rejects_symlink_root_cli_level``.
    """
    real = tmp_path / "real"
    real.mkdir()
    (real / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    link = tmp_path / "link"
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == link)
    with pytest.raises(ValueError, match="symlink project root rejected"):
        verify_creator_project(link, MANIFEST, engine_path=None, timeout=1, mode="import")
