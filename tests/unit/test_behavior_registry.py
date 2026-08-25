"""Registry — allowlist, version, pinned hashes, resource parity, no arbitrary scripts."""

from __future__ import annotations

import hashlib
import importlib.resources
import pathlib
import tarfile
import zipfile

import pytest
from godotforge_core.behaviors.registry import (
    BEHAVIOR_VERSION,
    PINNED_HASHES,
    allowed_behavior_ids,
    behavior_version,
    is_allowlisted,
    load_behavior,
    pinned_hash,
)

# Immutable baseline — old plan.py literals preserved here, not depending on plan.py remaining
BASELINE_PLAYER = (
    b"extends CharacterBody2D\n"
    b"\n"
    b"const SPEED := 200.0\n"
    b"const JUMP_VELOCITY := -350.0\n"
    b"\n"
    b"func _physics_process(_delta: float) -> void:\n"
    b"\tvar direction := 0\n"
    b"\tif Input.is_action_pressed(\"move_left\"):\n"
    b"\t\tdirection -= 1\n"
    b"\tif Input.is_action_pressed(\"move_right\"):\n"
    b"\t\tdirection += 1\n"
    b"\tvelocity.x = direction * SPEED\n"
    b"\tif Input.is_action_just_pressed(\"jump\") and is_on_floor():\n"
    b"\t\tvelocity.y = JUMP_VELOCITY\n"
    b"\tvelocity.y += 980.0 * _delta\n"
    b"\tmove_and_slide()\n"
)
BASELINE_COIN = (
    b"extends Area2D\n"
    b"\n"
    b"func _on_body_entered(_body: Node) -> void:\n"
    b"\tqueue_free()\n"
)


def test_allowlist_exactly_two() -> None:
    """Allowlist contains exactly platformer_controller and collectible, sorted."""
    ids = allowed_behavior_ids()
    assert ids == ("collectible", "platformer_controller")
    assert is_allowlisted("platformer_controller") is True
    assert is_allowlisted("collectible") is True
    assert is_allowlisted("evil") is False


def test_version_pinned() -> None:
    """Behavior version stable at 1."""
    assert behavior_version() == 1
    assert BEHAVIOR_VERSION == 1


def test_pinned_hashes_match_baseline() -> None:
    """Pinned hashes must equal baseline bytes hashes."""
    assert pinned_hash("platformer_controller") == hashlib.sha256(BASELINE_PLAYER).hexdigest()
    assert pinned_hash("collectible") == hashlib.sha256(BASELINE_COIN).hexdigest()
    assert PINNED_HASHES["platformer_controller"] == "59449f62b5371e7c255583f2932a75e88ebc91531c1986113c518c824ae9ee0e"  # noqa: E501
    assert PINNED_HASHES["collectible"] == "c80b9f8d4463739bb9db90b0d5caf4b05ff34db22b84a625774da63a0b6b8f16"  # noqa: E501


def test_load_unknown_rejected() -> None:
    """Unknown behavior ID must raise ValueError (exit 2)."""
    with pytest.raises(ValueError, match="unknown behavior"):
        load_behavior("evil")
    with pytest.raises(ValueError, match="unknown behavior"):
        pinned_hash("evil")
    with pytest.raises(ValueError, match="unknown behavior"):
        load_behavior("../traversal")
    with pytest.raises(ValueError, match="unknown behavior"):
        load_behavior("platformer_controller; rm -rf")


def test_load_returns_baseline_bytes() -> None:
    """Registry load must return baseline-identical bytes (byte identity)."""
    assert load_behavior("platformer_controller") == BASELINE_PLAYER
    assert load_behavior("collectible") == BASELINE_COIN


def test_resource_presence_source_checkout() -> None:
    """Source checkout resource lookup via importlib.resources.files must succeed."""
    pkg = importlib.resources.files("godotforge_core.behaviors.resources")
    for fid, fname in [("platformer_controller", "platformer_controller.gd"), ("collectible", "collectible.gd")]:  # noqa: E501
        res = pkg.joinpath(fname)
        assert res.is_file(), f"missing resource {fname} in source checkout"
        data = res.read_bytes()  # type: ignore[attr-defined]
        assert hashlib.sha256(data).hexdigest() == PINNED_HASHES[fid]


def test_resource_presence_installed_wheel() -> None:
    """Installed wheel resource lookup via as_file must succeed with same hash."""
    pkg = importlib.resources.files("godotforge_core.behaviors.resources")
    import importlib.resources as res

    for fid, fname in [("platformer_controller", "platformer_controller.gd"), ("collectible", "collectible.gd")]:  # noqa: E501
        traversable = pkg.joinpath(fname)
        with res.as_file(traversable) as p:
            assert pathlib.Path(p).is_file()
            assert hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() == PINNED_HASHES[fid]


def test_sdist_resource_parity() -> None:
    """Sdist must contain same resources (checked via built sdist tar)."""
    # Find latest sdist for godotforge-core
    dist = pathlib.Path("dist")
    sdists = sorted(dist.glob("godotforge_core-*.tar.gz"), key=lambda p: p.stat().st_mtime)
    if not sdists:
        pytest.skip("no sdist built")
    sdist = sdists[-1]
    with tarfile.open(sdist, "r:gz") as tf:
        names = tf.getnames()
        # sdist contains src/godotforge_core/behaviors/resources/*.gd
        for fname in ["platformer_controller.gd", "collectible.gd"]:
            assert any(f.endswith(f"behaviors/resources/{fname}") for f in names), f"missing {fname} in sdist"  # noqa: E501


def test_wheel_resource_parity() -> None:
    """Wheel must contain same resources."""
    dist = pathlib.Path("dist")
    wheels = sorted(dist.glob("godotforge_core-*.whl"), key=lambda p: p.stat().st_mtime)
    if not wheels:
        pytest.skip("no wheel built")
    wheel = wheels[-1]
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        for fname in ["platformer_controller.gd", "collectible.gd"]:
            assert f"godotforge_core/behaviors/resources/{fname}" in names


def test_no_arbitrary_script_path() -> None:
    """Manifest must not accept arbitrary script paths — registry only."""
    # This is enforced by manifest having no script field; registry is the only source
    # Attempt to load with traversal should be rejected as unknown ID
    with pytest.raises(ValueError, match="unknown"):
        load_behavior("res://evil.gd")
    with pytest.raises(ValueError, match="unknown"):
        load_behavior("../../../etc/passwd")


def test_injection_rejection() -> None:
    """GDScript injection via behavior ID must be rejected (no eval)."""
    for evil in ["platformer_controller; DROP", "collectible\nqueue_free", "platformer_controller\x00"]:  # noqa: E501
        with pytest.raises(ValueError, match="unknown"):
            load_behavior(evil)
