"""Behavior registry hash-consistency guard.

Regression test for the PINNED_HASHES-vs-actual-bytes mismatch discovered
on HEAD (the three original 2D behavior hashes were transcribed wrong,
breaking every test that touched plan_creator_manifest). Protects every
allowlisted id — the 3 original 2D ones and the 24 added for the 3D
tactical-shooter template — against the same class of transcription error.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import importlib.resources

from godotforge_core.behaviors.registry import (
    allowed_behavior_ids,
    load_behavior,
    pinned_hash,
)


def _raw_bytes(behavior_id: str) -> bytes:
    """Read the resource bytes independently of load_behavior's own hash check."""
    from godotforge_core.behaviors.registry import _ALLOWLIST  # noqa: SLF001

    filename = _ALLOWLIST[behavior_id]
    pkg = importlib.resources.files("godotforge_core.behaviors.resources").joinpath(filename)
    return pkg.read_bytes()


def test_every_allowlisted_id_hash_matches_pinned() -> None:
    ids = allowed_behavior_ids()
    assert len(ids) >= 27
    for behavior_id in ids:
        raw = _raw_bytes(behavior_id)
        actual = hashlib.sha256(raw).hexdigest()
        assert actual == pinned_hash(behavior_id), (
            f"{behavior_id}: pinned hash {pinned_hash(behavior_id)} does not match "
            f"actual bytes hash {actual}"
        )


def test_every_allowlisted_id_loads_without_raising() -> None:
    for behavior_id in allowed_behavior_ids():
        data = load_behavior(behavior_id)
        assert len(data) > 0


def test_3d_behavior_ids_present() -> None:
    ids = set(allowed_behavior_ids())
    expected = {
        "event_bus", "character_data", "weapon_data", "ability_data",
        "game_manager", "input_manager", "damageable", "ability_system",
        "district_zone_behavior", "bot_state_machine", "weapon_controller",
        "hud_controller", "player_controller_3d",
        "external/world_generator/map_generator",
        "external/world_generator/city_noise_generator",
        "external/world_generator/terrain_utils",
        "external/spritebrew/asset_import_pipeline",
        "external/spritebrew/texture_processor_3d",
        "external/spritebrew/decals_and_labels",
        "external/powerups/ability_base",
        "external/powerups/ability_manager",
        "external/powerups/ability_effects",
        "external/powerups/ability_pickup",
        "external/signal_generator/signal_macros",
    }
    assert expected <= ids


def test_game_event_signals_not_shipped() -> None:
    """game_event_signals.gd was dropped as redundant with event_bus.gd
    (which already implements subscribe/publish; game_event_signals.gd
    never did)."""
    ids = allowed_behavior_ids()
    assert not any("game_event_signals" in bid for bid in ids)


def test_allowlist_and_pinned_hashes_agree_on_ids() -> None:
    """_ALLOWLIST and PINNED_HASHES are two independently hand-maintained
    dicts keyed by the same ids. Catches drift in either direction: an id
    added to one but not the other (a KeyError at runtime that would
    otherwise only surface the first time someone actually requests that
    specific behavior)."""
    from godotforge_core.behaviors.registry import _ALLOWLIST, PINNED_HASHES  # noqa: SLF001

    allowlist_ids = set(_ALLOWLIST)
    pinned_ids = set(PINNED_HASHES)
    assert allowlist_ids == pinned_ids, (
        f"_ALLOWLIST/PINNED_HASHES key drift: "
        f"in _ALLOWLIST only: {sorted(allowlist_ids - pinned_ids)}; "
        f"in PINNED_HASHES only: {sorted(pinned_ids - allowlist_ids)}"
    )


def test_no_orphaned_resource_files() -> None:
    """Every .gd file actually present under behaviors/resources/ is
    registered in _ALLOWLIST — catches the opposite drift direction from
    test_every_allowlisted_id_hash_matches_pinned: a file added to the
    resources directory (e.g. copy-pasted in during development) but never
    wired into the registry, which would otherwise sit there silently,
    unreachable and untested, indefinitely."""
    from godotforge_core.behaviors.registry import _ALLOWLIST  # noqa: SLF001

    registered_filenames = set(_ALLOWLIST.values())

    # tests/unit/test_behaviors_registry.py -> repo root is two parents up.
    repo_root = Path(__file__).resolve().parent.parent.parent
    resources_root = (
        repo_root
        / "packages" / "godotforge-core" / "src" / "godotforge_core"
        / "behaviors" / "resources"
    )
    assert resources_root.is_dir(), f"expected resources dir not found: {resources_root}"

    on_disk = {
        p.relative_to(resources_root).as_posix()
        for p in resources_root.rglob("*.gd")
    }
    orphaned = on_disk - registered_filenames
    assert not orphaned, (
        f".gd files present on disk but not registered in _ALLOWLIST: {sorted(orphaned)} "
        f"— run tools/register_behavior.py to register them"
    )
