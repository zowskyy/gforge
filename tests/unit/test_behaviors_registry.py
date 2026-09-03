"""Behavior registry hash-consistency guard.

Regression test for the PINNED_HASHES-vs-actual-bytes mismatch discovered
on HEAD (the three original 2D behavior hashes were transcribed wrong,
breaking every test that touched plan_creator_manifest). Protects every
allowlisted id — the 3 original 2D ones and the 24 added for the 3D
tactical-shooter template — against the same class of transcription error.
"""

from __future__ import annotations

import hashlib
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
        "event_bus",
        "character_data",
        "weapon_data",
        "ability_data",
        "game_manager",
        "input_manager",
        "damageable",
        "ability_system",
        "district_zone_behavior",
        "bot_state_machine",
        "weapon_controller",
        "hud_controller",
        "player_controller_3d",
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
