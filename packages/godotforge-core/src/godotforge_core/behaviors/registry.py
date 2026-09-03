"""Behavior registry — allowlisted, versioned, pinned hashes, deterministic."""

from __future__ import annotations

import hashlib
import importlib.resources
from pathlib import Path

BEHAVIOR_VERSION = 1

_ALLOWLIST: dict[str, str] = {
    "platformer_controller": "platformer_controller.gd",
    "platformer_controller_v2": "platformer_controller_v2.gd",
    "collectible": "collectible.gd",
    # 3D tactical-shooter template — core District Kings behaviors.
    "event_bus": "event_bus.gd",
    "character_data": "character_data.gd",
    "weapon_data": "weapon_data.gd",
    "ability_data": "ability_data.gd",
    "game_manager": "game_manager.gd",
    "input_manager": "input_manager.gd",
    "damageable": "damageable.gd",
    "ability_system": "ability_system.gd",
    "district_zone_behavior": "district_zone_behavior.gd",
    "bot_state_machine": "bot_state_machine.gd",
    "weapon_controller": "weapon_controller.gd",
    "hud_controller": "hud_controller.gd",
    "player_controller_3d": "player_controller_3d.gd",
    "level_setup": "level_setup.gd",
    # 3D tactical-shooter template — ported/fixed external systems.
    "external/world_generator/map_generator": "external/world_generator/map_generator.gd",
    "external/world_generator/city_noise_generator": "external/world_generator/city_noise_generator.gd",
    "external/world_generator/terrain_utils": "external/world_generator/terrain_utils.gd",
    "external/spritebrew/asset_import_pipeline": "external/spritebrew/asset_import_pipeline.gd",
    "external/spritebrew/texture_processor_3d": "external/spritebrew/texture_processor_3d.gd",
    "external/spritebrew/decals_and_labels": "external/spritebrew/decals_and_labels.gd",
    "external/powerups/ability_base": "external/powerups/ability_base.gd",
    "external/powerups/ability_manager": "external/powerups/ability_manager.gd",
    "external/powerups/ability_effects": "external/powerups/ability_effects.gd",
    "external/powerups/ability_pickup": "external/powerups/ability_pickup.gd",
    "external/signal_generator/signal_macros": "external/signal_generator/signal_macros.gd",
}

PINNED_HASHES: dict[str, str] = {
    "platformer_controller": "59449f62b5371e7c255583f2932a75e88ebc91531c1986113c518c824ae9ee0e",
    "platformer_controller_v2": "1a7f8aa5c7ebd8bcf23a6ff818de6faa58a534722b7e3983b8b1b01fd532e1a0",
    "collectible": "c80b9f8d4463739bb9db90b0d5caf4b05ff34db22b84a625774da63a0b6b8f16",
    "event_bus": "e89bfd74fa96cbbd9b12430a08be61fa4b638405179afaa24faf3ebf4fefaac1",
    "character_data": "d71a6fcf76e72a38017b2533eff3e7cc478a080c30d7e772157baf15acad2123",
    "weapon_data": "87f329d71ac9d42b8598f1b72a0915d94421321c883853117c1f25c78a986440",
    "ability_data": "3b0be6f77d8bd6c44b8af030fbb8ab3697fa66f0099b3fed2213d457b751e80b",
    "game_manager": "a995b8eece640bcdf8974de77c5907442194acca2c53096e6c6bd1814bad8018",
    "input_manager": "8cab00e29ffa07abc84af4fdabb5350fd8ed8deb3cfc5b72f7b318f8fa770e18",
    "damageable": "c6c264edc532c3fddf5bf25edeecbed9e3f407aa0bd9c4a693aa04e08ef8d1f8",
    "ability_system": "3f3c94a13d05d86a7c1d7bf5a2990eaaad82a5ca7b1d4781507f74846df3ab4b",
    "district_zone_behavior": "09b459d3b2ccf8fb9119f2f4a8ab48f3ac02ceaa7897b116686505ec836adde4",
    "bot_state_machine": "41cadad55ebbdc1bcd41705c5da43b4dd0cb0041e12154a8a472be683025e95a",
    "weapon_controller": "f303dbfcc0b9bd3a40f0f1290d357ef1f180409a7f71ee6af184bd0bface5137",
    "hud_controller": "fab946be7423880ab7968edb222ff08807b5497a1313a322559de9a64fc67db2",
    "player_controller_3d": "8ec3ca4cef9ed41d6b5eb918484560fa0e5b5730ba0567b2de5ed4c7765c2281",
    "level_setup": "2daae5420f03f01f6bdd866f91fb3991cae1b41653c001c80d05119b4c45c19b",
    "external/world_generator/map_generator": "c780672ad0f3dbd313ce0c81aa194e31549dcc7df532fe9e05fc4266c7c1470a",
    "external/world_generator/city_noise_generator": "f530545e0bc8518827ea1791dc5b36fa82761935cac6d622cf6133cea225f50c",
    "external/world_generator/terrain_utils": "de620b967e539ec0070e869521ed8da11a69050dddd44d487af40a6027112787",
    "external/spritebrew/asset_import_pipeline": "0e0e640ef2321186921c6f737971ec51da45cbab093a2527091290ef3cdc019f",
    "external/spritebrew/texture_processor_3d": "f82d81367e066364f6035cf129a6363bb50054fe1b30313de22bbfd03d7d2cff",
    "external/spritebrew/decals_and_labels": "5e9afe6b201dfc6a149a89f45034e016611a995d82a169f1da8ac5e048b60d68",
    "external/powerups/ability_base": "2e38ba5817cd544e0d96e8756f14c96e80e3d7c4166f22b35f22b4156d3cf1bc",
    "external/powerups/ability_manager": "65aa72b5abf15d0afc85f985a3091e34fd02e6c1ba02317e880131506e08c678",
    "external/powerups/ability_effects": "1ee45e947ac45be587d29135c3346afbc06fb29be17b9ce0a1914dc5365ce13e",
    "external/powerups/ability_pickup": "501a1630f830419c1ad0f08689d472ddb3ad8e9c56bdb54db06b9faf6cc840d6",
    "external/signal_generator/signal_macros": "752892e9778edda57870234470e2be96c50b04b0908e2c1501b5318d9983f4b6",
}


def allowed_behavior_ids() -> tuple[str, ...]:
    """Return sorted tuple of allowlisted behavior IDs."""
    return tuple(sorted(_ALLOWLIST.keys()))


def behavior_version() -> int:
    """Return stable behavior version."""
    return BEHAVIOR_VERSION


def pinned_hash(behavior_id: str) -> str:
    """Return pinned SHA-256 for behavior ID.

    Raises ValueError for unknown IDs.
    """
    if behavior_id not in PINNED_HASHES:
        raise ValueError(f"unknown behavior ID {behavior_id!r}")
    return PINNED_HASHES[behavior_id]


def _resource_path(behavior_id: str) -> Path:
    """Return package resource path for behavior ID, validating allowlist."""
    if behavior_id not in _ALLOWLIST:
        raise ValueError(f"unknown behavior ID {behavior_id!r}")
    filename = _ALLOWLIST[behavior_id]
    # Explicit package resources path per corrected contract
    pkg = importlib.resources.files("godotforge_core.behaviors.resources").joinpath(filename)
    # For wheel/sdist, use as_file to get real path
    import importlib.resources as res

    try:
        # Try direct check if traversable
        if hasattr(pkg, "is_file"):
            # pkg is Traversable, check via as_file
            with res.as_file(pkg) as p:
                if Path(p).is_file():
                    return Path(p)
        # Fallback for source checkout
        candidate = Path(__file__).with_name("resources") / filename
        if candidate.is_file():
            return candidate
    except Exception:
        pass
    # Return traversable as Path fallback (for reading via read_bytes)
    # Use importlib.resources path as string fallback
    return Path(str(pkg))


def load_behavior(behavior_id: str) -> bytes:
    """Load behavior GDScript bytes for allowlisted ID, verifying pinned hash.

    Raises FileNotFoundError if resource missing, ValueError if hash mismatch or unknown ID.
    """
    if behavior_id not in _ALLOWLIST:
        raise ValueError(f"unknown behavior ID {behavior_id!r}")
    filename = _ALLOWLIST[behavior_id]
    expected = PINNED_HASHES[behavior_id]
    pkg = importlib.resources.files("godotforge_core.behaviors.resources").joinpath(filename)
    import importlib.resources as res

    data: bytes
    try:
        # Handle both source and wheel via as_file or read_bytes directly
        if hasattr(pkg, "read_bytes"):
            data = pkg.read_bytes()  # type: ignore[attr-defined]
        else:
            with res.as_file(pkg) as p:
                data = Path(p).read_bytes()
    except FileNotFoundError:
        raise FileNotFoundError(f"behavior resource missing: {behavior_id} ({filename})") from None
    except Exception as exc:
        raise FileNotFoundError(f"behavior resource missing: {behavior_id}: {exc}") from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(
            f"behavior hash mismatch for {behavior_id!r}: expected {expected}, got {actual}"
        )  # noqa: E501
    return data


def is_allowlisted(behavior_id: str) -> bool:
    """Return whether behavior ID is allowlisted."""
    return behavior_id in _ALLOWLIST
