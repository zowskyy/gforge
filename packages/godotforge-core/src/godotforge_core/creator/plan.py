"""Deterministic creator planner — six-operation planning-only slice.

Produces a read-only CreatorPatch (plan + desired bytes) for an empty/template
root. No backup, apply, engine invocation, network, telemetry, LLM, or generated
source. The scene emitter, project.godot emitter, script emitters, UID, and
ordering are all deterministic.

No AI dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from godotforge_core.hub_control_plane import HubPathSafetyError, validate_hub_metadata_dir
from godotforge_core.patch.hashing import hash_bytes
from godotforge_core.patch.models import OperationKind, PatchOperation, PatchPlan

from .manifest import CreatorManifest, CreatorPreflightError, validate_manifest_dict
from .uid import deterministic_uid

TEMPLATE_ID = "2d-platformer-minimal"
_TEMPLATE_3D = "3d-tactical-shooter"
SCHEMA_VERSION = 1

# Deterministic scene geometry — single source of truth for tests
GROUND_POS = (0, 128)
GROUND_SIZE = (800, 32)  # RectangleShape2D size
GROUND_TOP = GROUND_POS[1] - GROUND_SIZE[1] // 2  # 112
PLAYER_POS = (0, 48)  # center 64px above top: 112-48=64
PLAYER_RADIUS = 16
COIN_POS = (160, 100)  # resting: 112 - 12 = 100
COIN_RADIUS = 12

# Fixed v1 input emissions — canonical Godot literals (no free-form)
# noqa: E501 — literals must match Godot's exact InputEventKey serialization
_INPUT_LITERAL: dict[str, str] = {
    "move_left": '{\n"deadzone": 0.5,\n"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194319,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)\n]\n}',  # noqa: E501
    "move_right": '{\n"deadzone": 0.5,\n"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194321,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)\n]\n}',  # noqa: E501
    "jump": '{\n"deadzone": 0.5,\n"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":32,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)\n]\n}',  # noqa: E501
}

# Allowed skeleton files (State B)
_SKELETON_FILES = {".godotforge/project.yaml", ".godotforge/project.lock"}
_ALLOWED_DIR_PREFIXES = ("scenes/", "scripts/", ".godotforge/")

_G_FILES_2D = (
    "project.godot",
    "scenes/main.tscn",
    "scripts/coin.gd",
    "scripts/player_controller.gd",
)
_G_DIRS_2D = ("scenes", "scripts")

# Backward-compatible aliases for callers written before the 3D template
# existed (tests/unit/test_hub_performance.py exercises the 2D path
# specifically and imports these bare names).
_G_FILES = _G_FILES_2D
_G_DIRS = _G_DIRS_2D

# 3D tactical-shooter template — deterministic geometry for the graybox level
FLOOR_SIZE = (60.0, 1.0, 60.0)
FLOOR_POS = (0.0, -0.5, 0.0)
PLAYER_SPAWN_POS = (0.0, 1.0, 5.0)
ZONE_A_POS = (-10.0, 0.5, -10.0)
ZONE_B_POS = (10.0, 0.5, -10.0)
ZONE_RADIUS = 4.0
SPAWN_TEAM0_POS = (0.0, 0.5, 20.0)
SPAWN_TEAM1_POS = (0.0, 0.5, -20.0)

_EXTERNAL_BEHAVIOR_IDS: tuple[tuple[str, str], ...] = (
    ("external/world_generator/map_generator", "scripts/external/world_generator/map_generator.gd"),
    ("external/world_generator/city_noise_generator", "scripts/external/world_generator/city_noise_generator.gd"),
    ("external/world_generator/terrain_utils", "scripts/external/world_generator/terrain_utils.gd"),
    ("external/spritebrew/asset_import_pipeline", "scripts/external/spritebrew/asset_import_pipeline.gd"),
    ("external/spritebrew/texture_processor_3d", "scripts/external/spritebrew/texture_processor_3d.gd"),
    ("external/spritebrew/decals_and_labels", "scripts/external/spritebrew/decals_and_labels.gd"),
    ("external/powerups/ability_base", "scripts/external/powerups/ability_base.gd"),
    ("external/powerups/ability_manager", "scripts/external/powerups/ability_manager.gd"),
    ("external/powerups/ability_effects", "scripts/external/powerups/ability_effects.gd"),
    ("external/powerups/ability_pickup", "scripts/external/powerups/ability_pickup.gd"),
    ("external/signal_generator/signal_macros", "scripts/external/signal_generator/signal_macros.gd"),
)

_G_FILES_3D = (
    "project.godot",
    "scenes/player_3d.tscn",
    "scenes/weapon_base.tscn",
    "scenes/ability_base.tscn",
    "scenes/district_zone.tscn",
    "scenes/graybox_district.tscn",
    "scenes/hud.tscn",
    "scripts/game_manager.gd",
    "scripts/input_manager.gd",
    "scripts/player_controller.gd",
    "scripts/hud_controller.gd",
    "scripts/weapon_controller.gd",
    "scripts/damageable.gd",
    "scripts/ability_system.gd",
    "scripts/district_zone.gd",
    "scripts/bot_state_machine.gd",
    "scripts/event_bus.gd",
    "scripts/character_data.gd",
    "scripts/weapon_data.gd",
    "scripts/ability_data.gd",
    "scripts/level_setup.gd",
    "data/characters/enforcer.tres",
    "data/characters/scout.tres",
    "data/characters/fixer.tres",
    "data/weapons/rifle.tres",
    "data/weapons/shotgun.tres",
    "data/weapons/sniper.tres",
    "data/abilities/dash.tres",
    "data/abilities/shield.tres",
    "data/abilities/heal.tres",
    "PROJECT_TRACKING.md",
) + tuple(path for _, path in _EXTERNAL_BEHAVIOR_IDS)

_G_DIRS_3D = (
    "scenes",
    "scripts",
    "scripts/external",
    "scripts/external/world_generator",
    "scripts/external/spritebrew",
    "scripts/external/powerups",
    "scripts/external/signal_generator",
    "data",
    "data/characters",
    "data/weapons",
    "data/abilities",
)


def _g_files_for(manifest: CreatorManifest) -> tuple[str, ...]:
    """_g_files_for — template-parameterized managed-file set."""
    return _G_FILES_3D if manifest.template == _TEMPLATE_3D else _G_FILES_2D


def _g_dirs_for(manifest: CreatorManifest) -> tuple[str, ...]:
    """_g_dirs_for — template-parameterized managed-directory set."""
    return _G_DIRS_3D if manifest.template == _TEMPLATE_3D else _G_DIRS_2D


def all_managed_files() -> tuple[str, ...]:
    """Union of every template's managed G_FILES.

    hub/cache.py's project_root_hash is computed from a bare root path
    before the cached entry's manifest/template is known, so it must hash
    against every template's file set, not just one — a change to either
    template's managed files still invalidates correctly.
    """
    return tuple(sorted(set(_G_FILES_2D) | set(_G_FILES_3D)))


def all_managed_dirs() -> tuple[str, ...]:
    """Union of every template's managed G_DIRS — see all_managed_files."""
    return tuple(sorted(set(_G_DIRS_2D) | set(_G_DIRS_3D)))


def _canonical_manifest_json(manifest: CreatorManifest) -> str:
    """_canonical_manifest_json — production helper."""
    payload = manifest.as_dict()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _plan_id_for(manifest: CreatorManifest) -> str:
    """_plan_id_for — production helper."""
    canon = _canonical_manifest_json(manifest)
    short = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:8]
    return f"cr-{short}"


def plan_id_for(manifest: CreatorManifest) -> str:
    """plan_id_for — public manifest-derived plan id for Hub/CLI seams."""
    return _plan_id_for(manifest)


def canonical_manifest_hash(manifest: CreatorManifest) -> str:
    """canonical_manifest_hash — SHA-256 of the canonical manifest JSON.

    This is the ``manifestHash`` recorded in Hub run records (hub-v1 §4).
    """
    return hashlib.sha256(_canonical_manifest_json(manifest).encode("utf-8")).hexdigest()


def _emit_project_godot(manifest: CreatorManifest) -> bytes:
    """_emit_project_godot — production helper."""
    lines = [
        "; Engine configuration file.",
        "; It's best edited using the editor UI; changes to this file may cause errors.",
        "",
        "config_version=5",
        "",
        "[application]",
        "",
        f'config/name="{manifest.game_name}"',
        'config/features=PackedStringArray("4.7")',
        'run/main_scene="res://scenes/main.tscn"',
        "",
        "[input]",
        "",
    ]
    for name in ("move_left", "move_right", "jump"):
        lines.append(f"{name}={_INPUT_LITERAL[name]}")
    lines.append("")
    text = "\n".join(lines)
    # Ensure final newline (deterministic LF)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


# --- 3D tactical-shooter template ---------------------------------------

_RENDERER_GODOT_KEY: dict[str, str] = {
    "forward_plus": "forward_plus",
    "mobile": "mobile",
    "compatibility": "gl_compatibility",
}
_RENDERER_FEATURE_TAG: dict[str, str] = {
    "forward_plus": "Forward Plus",
    "mobile": "Mobile",
    "compatibility": "GL Compatibility",
}

# Godot 4 Key enum (physical_keycode values) for the fixed keyboard
# vocabulary used by the 3D template's default input_map bindings.
_KEY_PHYSICAL_KEYCODE: dict[str, int] = {
    "W": 87, "A": 65, "S": 83, "D": 68,
    "Q": 81, "E": 69, "R": 82, "F": 70,
    "Space": 32,
    "Shift": 4194325,
}
# Godot 4 MouseButton enum.
_MOUSE_BUTTON_INDEX: dict[str, int] = {
    "mouse_left": 1,
    "mouse_right": 2,
}
# Godot 4 JoyButton enum.
_JOY_BUTTON_INDEX: dict[str, int] = {
    "gamepad_button_a": 0,
    "gamepad_button_b": 1,
    "gamepad_button_x": 2,
    "gamepad_button_y": 3,
    "gamepad_button_left_stick": 7,
}
# Godot 4 JoyAxis enum + direction, for stick/trigger bindings.
_JOY_MOTION_AXIS: dict[str, tuple[int, float]] = {
    "gamepad_left_stick_up": (1, -1.0),
    "gamepad_left_stick_down": (1, 1.0),
    "gamepad_left_stick_left": (0, -1.0),
    "gamepad_left_stick_right": (0, 1.0),
    "gamepad_trigger_left": (4, 1.0),
    "gamepad_trigger_right": (5, 1.0),
}


def _key_event_literal(physical_keycode: int) -> str:
    return (
        'Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"",'
        '"device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,'
        '"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,'
        f'"physical_keycode":{physical_keycode},"key_label":0,"unicode":0,'
        '"location":0,"echo":false,"script":null)'
    )


def _mouse_button_event_literal(button_index: int) -> str:
    return (
        'Object(InputEventMouseButton,"resource_local_to_scene":false,"resource_name":"",'
        '"device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,'
        '"ctrl_pressed":false,"meta_pressed":false,"button_mask":0,'
        '"position":Vector2(0, 0),"global_position":Vector2(0, 0),"factor":1.0,'
        f'"button_index":{button_index},"canceled":false,"pressed":false,'
        '"double_click":false,"script":null)'
    )


def _joy_button_event_literal(button_index: int) -> str:
    return (
        'Object(InputEventJoypadButton,"resource_local_to_scene":false,"resource_name":"",'
        f'"device":-1,"window_id":0,"button_index":{button_index},"pressed":false,'
        '"pressure":0.0,"script":null)'
    )


def _joy_motion_event_literal(axis: int, axis_value: float) -> str:
    return (
        'Object(InputEventJoypadMotion,"resource_local_to_scene":false,"resource_name":"",'
        f'"device":-1,"window_id":0,"axis":{axis},"axis_value":{axis_value},"script":null)'
    )


def _binding_event_literal(binding: str) -> str | None:
    """Translate one manifest input_map binding string to a Godot
    InputEvent resource literal. Returns None for bindings with no
    discrete-action representation (e.g. raw mouse motion for "aim" —
    handled instead by a dedicated mouse-button binding, see
    _emit_project_godot_3d)."""
    if binding in _KEY_PHYSICAL_KEYCODE:
        return _key_event_literal(_KEY_PHYSICAL_KEYCODE[binding])
    if binding in _MOUSE_BUTTON_INDEX:
        return _mouse_button_event_literal(_MOUSE_BUTTON_INDEX[binding])
    if binding in _JOY_BUTTON_INDEX:
        return _joy_button_event_literal(_JOY_BUTTON_INDEX[binding])
    if binding in _JOY_MOTION_AXIS:
        axis, value = _JOY_MOTION_AXIS[binding]
        return _joy_motion_event_literal(axis, value)
    return None


def _emit_input_action_literal(action: str, bindings: tuple[str, ...]) -> str:
    events: list[str] = []
    for binding in bindings:
        literal = _binding_event_literal(binding)
        if literal is not None:
            events.append(literal)
    if action == "aim" and not events:
        # "aim" defaults to raw mouse-motion look, which has no discrete
        # InputMap event representation. Bind it to a hold-to-aim mouse
        # button (right-click ADS) instead of shipping an empty action —
        # actual look/turn is driven by InputEventMouseMotion directly in
        # player_controller.gd's _unhandled_input, not through this action.
        events.append(_mouse_button_event_literal(_MOUSE_BUTTON_INDEX["mouse_right"]))
    events_joined = ", ".join(events)
    return f'{{\n"deadzone": 0.5,\n"events": [{events_joined}]\n}}'


def _emit_project_godot_3d(manifest: CreatorManifest) -> bytes:
    """_emit_project_godot_3d — production helper. Forward+/Mobile/GL
    Compatibility renderer, 60Hz physics, 14 fixed input actions, and the
    EventBus/GameManager/InputManager autoloads."""
    assert manifest.renderer is not None
    assert manifest.physics_3d is not None
    assert manifest.input_map is not None
    from godotforge_core.creator.numfmt import format_canonical

    renderer_key = _RENDERER_GODOT_KEY[manifest.renderer]
    feature_tag = _RENDERER_FEATURE_TAG[manifest.renderer]
    gravity = format_canonical(manifest.physics_3d.gravity, name="gravity")

    lines = [
        "; Engine configuration file.",
        "; It's best edited using the editor UI; changes to this file may cause errors.",
        "",
        "config_version=5",
        "",
        "[application]",
        "",
        f'config/name="{manifest.game_name}"',
        f'config/features=PackedStringArray("4.7", "{feature_tag}")',
        'run/main_scene="res://scenes/graybox_district.tscn"',
        "",
        "[autoload]",
        "",
        'EventBus="*res://scripts/event_bus.gd"',
        'GameManager="*res://scripts/game_manager.gd"',
        'InputManager="*res://scripts/input_manager.gd"',
        "",
        "[physics]",
        "",
        "common/physics_ticks_per_second=60",
        f"3d/default_gravity={gravity}",
        "",
        "[rendering]",
        "",
        f'renderer/rendering_method="{renderer_key}"',
        "",
        "[input]",
        "",
    ]
    for i in manifest.inputs:
        bindings = manifest.input_map.bindings.get(i.name, ())
        lines.append(f"{i.name}={_emit_input_action_literal(i.name, bindings)}")
    lines.append("")
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _emit_behavior_3d(behavior_id: str) -> bytes:
    """_emit_behavior_3d — delegate .gd byte emission to the pinned-hash
    registry, exactly mirroring _emit_player_controller/_emit_coin. No
    generated/free-form script source."""
    from godotforge_core.behaviors.registry import load_behavior

    return load_behavior(behavior_id)


def _emit_player_controller(manifest: CreatorManifest) -> bytes:
    """_emit_player_controller — production helper.

    v1 manifests emit the pinned v1 resource bytes unchanged; v2 manifests
    emit the pinned v2 resource bytes unchanged. The planner never alters
    script source bytes — v2 parameter values live in ``scenes/main.tscn``
    as ``@export`` property assignments, so the v2 script hash is constant
    across all valid parameter values. No generated source, no substitution.
    """
    from godotforge_core.behaviors.registry import load_behavior

    if manifest.schema_version == 2:
        return load_behavior("platformer_controller_v2")
    return load_behavior("platformer_controller")


def _emit_coin() -> bytes:
    """_emit_coin — production helper."""
    from godotforge_core.behaviors.registry import load_behavior

    return load_behavior("collectible")


def _emit_scene_tscn(manifest: CreatorManifest) -> bytes:
    """_emit_scene_tscn — production helper.

    v1 scenes are byte-identical to the PATCH-0012 baseline. v2 scenes
    additionally carry the canonical ``speed`` / ``jump_velocity`` property
    assignments on the ``Player`` node (values for the fixed v2 script's
    ``@export`` properties) and use the manifest's schema version in the
    deterministic scene UID. No other scene content changes.
    """
    from godotforge_core.creator.numfmt import format_canonical

    uid = deterministic_uid(TEMPLATE_ID, manifest.schema_version, "scenes/main.tscn")
    # load_steps = 1 + ext_resource_count(2) + sub_resource_count(3) = 6
    lines: list[str] = []
    lines.append(f'[gd_scene load_steps=6 format=3 uid="{uid}"]')
    lines.append("")
    lines.append(
        '[ext_resource type="Script" path="res://scripts/player_controller.gd" id="1_script"]'  # noqa: E501
    )
    lines.append('[ext_resource type="Script" path="res://scripts/coin.gd" id="2_coin"]')
    lines.append("")
    lines.append('[sub_resource type="CircleShape2D" id="CircleShape2D_player"]')
    lines.append(f"radius = {float(PLAYER_RADIUS):.1f}")
    lines.append("")
    lines.append('[sub_resource type="RectangleShape2D" id="RectangleShape2D_ground"]')
    lines.append(f"size = Vector2({GROUND_SIZE[0]}, {GROUND_SIZE[1]})")
    lines.append("")
    lines.append('[sub_resource type="CircleShape2D" id="CircleShape2D_coin"]')
    lines.append(f"radius = {float(COIN_RADIUS):.1f}")
    lines.append("")
    # Nodes in deterministic order: Main, Player, Camera2D,
    # Player/Polygon2D, Player/CollisionShape2D, Ground,
    # Ground/CollisionShape2D, Ground/Polygon2D, Coin,
    # Coin/CollisionShape2D, Coin/Polygon2D
    lines.append('[node name="Main" type="Node2D"]')
    lines.append("")
    lines.append('[node name="Player" type="CharacterBody2D" parent="."]')
    lines.append(f"position = Vector2({PLAYER_POS[0]}, {PLAYER_POS[1]})")
    lines.append('script = ExtResource("1_script")')
    if manifest.schema_version == 2:
        assert manifest.parameters is not None
        lines.append(f"speed = {format_canonical(manifest.parameters.speed, name='speed')}")
        lines.append(
            "jump_velocity = "
            f"{format_canonical(manifest.parameters.jump_velocity, name='jump_velocity')}"
        )
    lines.append("")
    lines.append('[node name="Camera2D" type="Camera2D" parent="Player"]')
    lines.append("current = true")
    lines.append("")
    lines.append('[node name="Polygon2D" type="Polygon2D" parent="Player"]')
    lines.append("polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)")
    lines.append("color = Color(0.26, 0.53, 0.96, 1)")
    lines.append("")
    lines.append('[node name="CollisionShape2D" type="CollisionShape2D" parent="Player"]')
    lines.append('shape = SubResource("CircleShape2D_player")')
    lines.append("")
    lines.append('[node name="Ground" type="StaticBody2D" parent="."]')
    lines.append(f"position = Vector2({GROUND_POS[0]}, {GROUND_POS[1]})")
    lines.append("")
    lines.append('[node name="CollisionShape2D" type="CollisionShape2D" parent="Ground"]')
    lines.append('shape = SubResource("RectangleShape2D_ground")')
    lines.append("")
    lines.append('[node name="Polygon2D" type="Polygon2D" parent="Ground"]')
    lines.append("polygon = PackedVector2Array(-400, -16, 400, -16, 400, 16, -400, 16)")
    lines.append("color = Color(0.4, 0.26, 0.13, 1)")
    lines.append("")
    lines.append('[node name="Coin" type="Area2D" parent="."]')
    lines.append(f"position = Vector2({COIN_POS[0]}, {COIN_POS[1]})")
    lines.append('script = ExtResource("2_coin")')
    lines.append("")
    lines.append('[node name="CollisionShape2D" type="CollisionShape2D" parent="Coin"]')
    lines.append('shape = SubResource("CircleShape2D_coin")')
    lines.append("")
    lines.append('[node name="Polygon2D" type="Polygon2D" parent="Coin"]')
    lines.append(
        "polygon = PackedVector2Array(12, 0, 8.49, 8.49, 0, 12, "  # noqa: E501
        "-8.49, 8.49, -12, 0, -8.49, -8.49, 0, -12, 8.49, -8.49)"
    )
    lines.append("color = Color(0.96, 0.78, 0.2, 1)")
    lines.append("")
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _character_tres(manifest: CreatorManifest, role: str) -> bytes:
    """Emit data/characters/<role>.tres from the validated
    BehaviorParameters3D.<role> CharacterParameters — the goal/manifest
    parameter surface has real effect on these bytes (unlike the fixed
    weapon/ability .tres content below)."""
    from godotforge_core.creator.numfmt import format_canonical

    assert manifest.parameters is not None
    params = getattr(manifest.parameters, role)
    uid = deterministic_uid(_TEMPLATE_3D, manifest.schema_version, f"data/characters/{role}.tres")
    lines = [
        f'[gd_resource type="Resource" script_class="CharacterData" load_steps=2 format=3 uid="{uid}"]',
        "",
        '[ext_resource type="Script" path="res://scripts/character_data.gd" id="1_script"]',
        "",
        "[resource]",
        'script = ExtResource("1_script")',
        f'role = "{role}"',
        f"health = {format_canonical(params.health, name='health')}",
        f"armor = {format_canonical(params.armor, name='armor')}",
        f"move_speed = {format_canonical(params.move_speed, name='move_speed')}",
        f"sprint_multiplier = {format_canonical(params.sprint_multiplier, name='sprint_multiplier')}",
        "",
    ]
    text = "\n".join(lines)
    return text.encode("utf-8")


def _weapon_tres(manifest: CreatorManifest, name: str, stats: dict) -> bytes:
    """Emit data/weapons/<name>.tres from the fixed default stats, with any
    manifest.weapon_overrides.<name> fields substituted in — mirrors
    _character_tres's "goal parameters flow into generated bytes" pattern,
    but per-field (a goal may tune only damage and leave fire_rate/
    magazine_size at their fixed defaults)."""
    from godotforge_core.creator.numfmt import format_canonical

    uid = deterministic_uid(_TEMPLATE_3D, manifest.schema_version, f"data/weapons/{name}.tres")
    override = manifest.weapon_overrides.overrides.get(name) if manifest.weapon_overrides else None

    damage_line = f"damage = {stats['damage']}"
    fire_rate_line = f"fire_rate = {stats['fire_rate']}"
    magazine_size_line = f"magazine_size = {stats['magazine_size']}"
    pellet_count_line = f"pellet_count = {stats['pellet_count']}"
    reload_time_line = f"reload_time = {stats['reload_time']}"
    if override is not None:
        if override.damage is not None:
            damage_line = f"damage = {format_canonical(override.damage, name='damage')}"
        if override.fire_rate is not None:
            fire_rate_line = f"fire_rate = {format_canonical(override.fire_rate, name='fire_rate')}"
        if override.magazine_size is not None:
            magazine_size_line = f"magazine_size = {override.magazine_size}"
        if override.pellet_count is not None:
            pellet_count_line = f"pellet_count = {override.pellet_count}"
        if override.reload_time is not None:
            reload_time_line = f"reload_time = {format_canonical(override.reload_time, name='reload_time')}"

    lines = [
        f'[gd_resource type="Resource" script_class="WeaponData" load_steps=2 format=3 uid="{uid}"]',
        "",
        '[ext_resource type="Script" path="res://scripts/weapon_data.gd" id="1_script"]',
        "",
        "[resource]",
        'script = ExtResource("1_script")',
        f'weapon_name = "{stats["weapon_name"]}"',
        damage_line,
        pellet_count_line,
        fire_rate_line,
        magazine_size_line,
        reload_time_line,
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _ability_tres(manifest: CreatorManifest, name: str, stats: dict) -> bytes:
    """Emit data/abilities/<name>.tres from the fixed default stats, with any
    manifest.ability_overrides.<name> fields substituted in — mirrors
    _weapon_tres's per-field override pattern."""
    from godotforge_core.creator.numfmt import format_canonical

    uid = deterministic_uid(_TEMPLATE_3D, manifest.schema_version, f"data/abilities/{name}.tres")
    override = manifest.ability_overrides.overrides.get(name) if manifest.ability_overrides else None

    cooldown_line = f"cooldown = {stats['cooldown']}"
    duration_line = f"duration = {stats['duration']}"
    magnitude_line = f"magnitude = {stats['magnitude']}"
    radius_line = f"radius = {stats['radius']}"
    if override is not None:
        if override.cooldown is not None:
            cooldown_line = f"cooldown = {format_canonical(override.cooldown, name='cooldown')}"
        if override.duration is not None:
            duration_line = f"duration = {format_canonical(override.duration, name='duration')}"
        if override.magnitude is not None:
            magnitude_line = f"magnitude = {format_canonical(override.magnitude, name='magnitude')}"
        if override.radius is not None:
            radius_line = f"radius = {format_canonical(override.radius, name='radius')}"

    lines = [
        f'[gd_resource type="Resource" script_class="AbilityData" load_steps=2 format=3 uid="{uid}"]',
        "",
        '[ext_resource type="Script" path="res://scripts/ability_data.gd" id="1_script"]',
        "",
        "[resource]",
        'script = ExtResource("1_script")',
        f'ability_name = "{stats["ability_name"]}"',
        cooldown_line,
        duration_line,
        magnitude_line,
        radius_line,
        "",
    ]
    return "\n".join(lines).encode("utf-8")


# Fixed weapon/ability defaults, goal-tunable per-field via
# manifest.weapon_overrides / manifest.ability_overrides (see
# _weapon_tres / _ability_tres).
_WEAPON_STATS: dict[str, dict] = {
    "rifle": {"weapon_name": "Rifle", "damage": 18.0, "pellet_count": 1, "fire_rate": 0.11, "magazine_size": 30, "reload_time": 1.8},
    "shotgun": {"weapon_name": "Shotgun", "damage": 8.0, "pellet_count": 8, "fire_rate": 0.75, "magazine_size": 6, "reload_time": 2.2},
    "sniper": {"weapon_name": "Sniper", "damage": 95.0, "pellet_count": 1, "fire_rate": 1.1, "magazine_size": 5, "reload_time": 2.6},
}
_ABILITY_STATS: dict[str, dict] = {
    "dash": {"ability_name": "Dash", "cooldown": 6.0, "duration": 0.25, "magnitude": 8.0, "radius": 0.0},
    "shield": {"ability_name": "Shield", "cooldown": 14.0, "duration": 6.0, "magnitude": 75.0, "radius": 0.0},
    "heal": {"ability_name": "Heal", "cooldown": 10.0, "duration": 0.0, "magnitude": 40.0, "radius": 4.0},
}


def _emit_scene_player_3d(manifest: CreatorManifest) -> bytes:
    from godotforge_core.creator.numfmt import format_canonical

    assert manifest.physics_3d is not None
    uid = deterministic_uid(_TEMPLATE_3D, manifest.schema_version, "scenes/player_3d.tscn")
    lines = [
        f'[gd_scene load_steps=6 format=3 uid="{uid}"]',
        "",
        '[ext_resource type="Script" path="res://scripts/player_controller.gd" id="1_script"]',
        '[ext_resource type="Resource" path="res://data/characters/enforcer.tres" id="2_chardata"]',
        '[ext_resource type="Script" path="res://scripts/damageable.gd" id="3_damageable"]',
        "",
        '[sub_resource type="CapsuleShape3D" id="CapsuleShape3D_player"]',
        "radius = 0.4",
        "height = 1.8",
        "",
        '[sub_resource type="CapsuleMesh" id="CapsuleMesh_player"]',
        "radius = 0.4",
        "height = 1.8",
        "",
        '[node name="Player" type="CharacterBody3D"]',
        'script = ExtResource("1_script")',
        'character_data = ExtResource("2_chardata")',
        f"gravity = {format_canonical(manifest.physics_3d.gravity, name='gravity')}",
        f"floor_snap_length = {format_canonical(manifest.physics_3d.floor_snap_length, name='floor_snap_length')}",
        "",
        '[node name="CollisionShape3D" type="CollisionShape3D" parent="."]',
        'shape = SubResource("CapsuleShape3D_player")',
        "",
        '[node name="MeshInstance3D" type="MeshInstance3D" parent="."]',
        'mesh = SubResource("CapsuleMesh_player")',
        "",
        '[node name="Camera3D" type="Camera3D" parent="."]',
        "position = Vector3(0, 2, 4)",
        "rotation_degrees = Vector3(-15, 0, 0)",
        "current = true",
        "",
        '[node name="Damageable" type="Node" parent="."]',
        'script = ExtResource("3_damageable")',
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _emit_scene_weapon_base(manifest: CreatorManifest) -> bytes:
    uid = deterministic_uid(_TEMPLATE_3D, manifest.schema_version, "scenes/weapon_base.tscn")
    lines = [
        f'[gd_scene load_steps=4 format=3 uid="{uid}"]',
        "",
        '[ext_resource type="Script" path="res://scripts/weapon_controller.gd" id="1_script"]',
        '[ext_resource type="Resource" path="res://data/weapons/rifle.tres" id="2_weapondata"]',
        "",
        '[sub_resource type="BoxMesh" id="BoxMesh_weapon"]',
        "size = Vector3(0.1, 0.1, 0.6)",
        "",
        '[node name="WeaponBase" type="Node3D"]',
        'script = ExtResource("1_script")',
        'weapon_data = ExtResource("2_weapondata")',
        "",
        '[node name="MeshInstance3D" type="MeshInstance3D" parent="."]',
        'mesh = SubResource("BoxMesh_weapon")',
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _emit_scene_ability_base(manifest: CreatorManifest) -> bytes:
    uid = deterministic_uid(_TEMPLATE_3D, manifest.schema_version, "scenes/ability_base.tscn")
    lines = [
        f'[gd_scene load_steps=3 format=3 uid="{uid}"]',
        "",
        '[ext_resource type="Script" path="res://scripts/ability_system.gd" id="1_script"]',
        '[ext_resource type="Resource" path="res://data/abilities/dash.tres" id="2_abilitydata"]',
        "",
        '[node name="AbilityBase" type="Node3D"]',
        'script = ExtResource("1_script")',
        'ability_data = ExtResource("2_abilitydata")',
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _emit_scene_district_zone(manifest: CreatorManifest) -> bytes:
    uid = deterministic_uid(_TEMPLATE_3D, manifest.schema_version, "scenes/district_zone.tscn")
    lines = [
        f'[gd_scene load_steps=4 format=3 uid="{uid}"]',
        "",
        '[ext_resource type="Script" path="res://scripts/district_zone.gd" id="1_script"]',
        "",
        '[sub_resource type="CylinderShape3D" id="CylinderShape3D_zone"]',
        f"radius = {ZONE_RADIUS}",
        "height = 2.0",
        "",
        '[sub_resource type="SphereMesh" id="SphereMesh_zone"]',
        f"radius = {ZONE_RADIUS}",
        f"height = {ZONE_RADIUS * 2}",
        "",
        '[node name="DistrictZone" type="Area3D"]',
        'script = ExtResource("1_script")',
        "",
        '[node name="CollisionShape3D" type="CollisionShape3D" parent="."]',
        'shape = SubResource("CylinderShape3D_zone")',
        "",
        '[node name="Label3D" type="Label3D" parent="."]',
        "position = Vector3(0, 2, 0)",
        'text = "District"',
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _emit_scene_hud(manifest: CreatorManifest) -> bytes:
    uid = deterministic_uid(_TEMPLATE_3D, manifest.schema_version, "scenes/hud.tscn")
    lines = [
        f'[gd_scene load_steps=2 format=3 uid="{uid}"]',
        "",
        '[ext_resource type="Script" path="res://scripts/hud_controller.gd" id="1_script"]',
        "",
        '[node name="HUD" type="CanvasLayer"]',
        "",
        '[node name="Control" type="Control" parent="."]',
        'script = ExtResource("1_script")',
        "anchor_right = 1.0",
        "anchor_bottom = 1.0",
        "",
        '[node name="HealthBar" type="ProgressBar" parent="Control"]',
        "offset_left = 24.0",
        "offset_top = 24.0",
        "offset_right = 224.0",
        "offset_bottom = 44.0",
        "max_value = 100.0",
        "value = 100.0",
        "",
        '[node name="HealthLabel" type="Label" parent="Control"]',
        "offset_left = 24.0",
        "offset_top = 48.0",
        "offset_right = 224.0",
        "offset_bottom = 68.0",
        'text = "100 / 100"',
        "",
        '[node name="AmmoLabel" type="Label" parent="Control"]',
        "offset_left = 24.0",
        "offset_top = 76.0",
        "offset_right = 224.0",
        "offset_bottom = 96.0",
        'text = "30 / 30"',
        "",
        '[node name="ZoneLabel" type="Label" parent="Control"]',
        "offset_left = 24.0",
        "offset_top = 104.0",
        "offset_right = 424.0",
        "offset_bottom = 124.0",
        'text = ""',
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _emit_scene_graybox_district(manifest: CreatorManifest) -> bytes:
    uid = deterministic_uid(_TEMPLATE_3D, manifest.schema_version, "scenes/graybox_district.tscn")
    lines = [
        f'[gd_scene load_steps=9 format=3 uid="{uid}"]',
        "",
        '[ext_resource type="Script" path="res://scripts/level_setup.gd" id="1_levelsetup"]',
        '[ext_resource type="PackedScene" path="res://scenes/player_3d.tscn" id="2_player"]',
        '[ext_resource type="PackedScene" path="res://scenes/district_zone.tscn" id="3_zone"]',
        '[ext_resource type="PackedScene" path="res://scenes/hud.tscn" id="4_hud"]',
        "",
        '[sub_resource type="Environment" id="Environment_1"]',
        "background_mode = 1",
        "background_color = Color(0.5, 0.6, 0.7, 1)",
        "",
        '[sub_resource type="BoxShape3D" id="BoxShape3D_floor"]',
        f"size = Vector3({FLOOR_SIZE[0]}, {FLOOR_SIZE[1]}, {FLOOR_SIZE[2]})",
        "",
        '[sub_resource type="BoxMesh" id="BoxMesh_floor"]',
        f"size = Vector3({FLOOR_SIZE[0]}, {FLOOR_SIZE[1]}, {FLOOR_SIZE[2]})",
        "",
        '[sub_resource type="NavigationMesh" id="NavigationMesh_1"]',
        "",
        '[node name="GrayboxDistrict" type="Node3D"]',
        'script = ExtResource("1_levelsetup")',
        "",
        '[node name="WorldEnvironment" type="WorldEnvironment" parent="."]',
        'environment = SubResource("Environment_1")',
        "",
        '[node name="DirectionalLight3D" type="DirectionalLight3D" parent="."]',
        "rotation_degrees = Vector3(-45, -30, 0)",
        "",
        '[node name="NavigationRegion3D" type="NavigationRegion3D" parent="."]',
        'navigation_mesh = SubResource("NavigationMesh_1")',
        "",
        '[node name="Floor" type="StaticBody3D" parent="."]',
        f"position = Vector3({FLOOR_POS[0]}, {FLOOR_POS[1]}, {FLOOR_POS[2]})",
        "",
        '[node name="CollisionShape3D" type="CollisionShape3D" parent="Floor"]',
        'shape = SubResource("BoxShape3D_floor")',
        "",
        '[node name="MeshInstance3D" type="MeshInstance3D" parent="Floor"]',
        'mesh = SubResource("BoxMesh_floor")',
        "",
        '[node name="Player" parent="." instance=ExtResource("2_player")]',
        f"position = Vector3({PLAYER_SPAWN_POS[0]}, {PLAYER_SPAWN_POS[1]}, {PLAYER_SPAWN_POS[2]})",
        "",
        '[node name="DistrictZoneA" parent="." instance=ExtResource("3_zone")]',
        f"position = Vector3({ZONE_A_POS[0]}, {ZONE_A_POS[1]}, {ZONE_A_POS[2]})",
        "zone_id = 0",
        "",
        '[node name="DistrictZoneB" parent="." instance=ExtResource("3_zone")]',
        f"position = Vector3({ZONE_B_POS[0]}, {ZONE_B_POS[1]}, {ZONE_B_POS[2]})",
        "zone_id = 1",
        "",
        '[node name="HUD" parent="." instance=ExtResource("4_hud")]',
        "",
        '[node name="SpawnPointTeam0" type="Node3D" parent="."]',
        f"position = Vector3({SPAWN_TEAM0_POS[0]}, {SPAWN_TEAM0_POS[1]}, {SPAWN_TEAM0_POS[2]})",
        'groups = ["spawn_team_0"]',
        "",
        '[node name="SpawnPointTeam1" type="Node3D" parent="."]',
        f"position = Vector3({SPAWN_TEAM1_POS[0]}, {SPAWN_TEAM1_POS[1]}, {SPAWN_TEAM1_POS[2]})",
        'groups = ["spawn_team_1"]',
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _emit_project_tracking_md() -> bytes:
    text = """# District Kings — Project Tracking

## Purpose
District Kings is a 3v3 gangster-themed tactical hero shooter (original IP —
no League/Riot or other third-party references), generated by godotforge's
"3d-tactical-shooter" template. Three roles (enforcer, scout, fixer), one
graybox district map, three weapons, three abilities, capture-zone
objectives, and a minimal bot AI skeleton.

## File inventory
| File | Purpose | Status |
|---|---|---|
| project.godot | Forward+/Mobile/GL renderer, 60Hz physics, 14 input actions, EventBus/GameManager/InputManager autoloads | complete |
| scenes/player_3d.tscn | CharacterBody3D player: collision, mesh, camera, Damageable | complete |
| scenes/weapon_base.tscn | Base weapon scene (Node3D + WeaponController) | complete |
| scenes/ability_base.tscn | Base ability scene (Node3D + AbilitySystem) | complete |
| scenes/district_zone.tscn | Capture-zone volume (Area3D + DistrictZone) | complete |
| scenes/graybox_district.tscn | Main playable level: floor, lighting, nav region, spawn points, player, two zones, HUD | complete |
| scenes/hud.tscn | HUD: health bar, ammo, zone capture labels | complete |
| scripts/game_manager.gd | Autoload: match state, scores, spawn point registry | complete |
| scripts/input_manager.gd | Autoload: normalized input queries | complete |
| scripts/event_bus.gd | Autoload: pub/sub event bus | complete |
| scripts/level_setup.gd | Registers spawn points, starts match | complete |
| scripts/player_controller.gd | WASD + mouse-look movement | complete |
| scripts/hud_controller.gd | Binds HUD widgets to EventBus | complete |
| scripts/weapon_controller.gd | Hitscan fire/reload | complete |
| scripts/damageable.gd | Health/armor component | complete |
| scripts/ability_system.gd | Generic ability cooldown component | complete |
| scripts/district_zone.gd | Capture-zone progress logic | complete |
| scripts/bot_state_machine.gd | idle/patrol/engage FSM | complete (minimal, not tuned) |
| scripts/character_data.gd, weapon_data.gd, ability_data.gd | Typed Resource classes backing data/*.tres | complete |
| scripts/external/world_generator/* | Adapted district/noise/terrain generators (Godot 4 FastNoiseLite fix applied) | complete |
| scripts/external/spritebrew/* | Adapted texture/decal/import tooling (asset_import_pipeline.gd editor-only-gated) | complete |
| scripts/external/powerups/* | Adapted generic ability base/manager/effects/pickup | complete |
| scripts/external/signal_generator/signal_macros.gd | EventBus subscription helpers | complete |
| data/characters/{enforcer,scout,fixer}.tres | Role stats, sourced from goal/manifest parameters | complete |
| data/weapons/{rifle,shotgun,sniper}.tres | Fixed weapon stats (not yet goal-tunable) | complete |
| data/abilities/{dash,shield,heal}.tres | Fixed ability stats (not yet goal-tunable) | complete |

## Open dependencies
- Weapon/ability stats are fixed literal content; no WeaponParameters/
  AbilityParameters manifest schema exists yet to make them goal-tunable.
- Goal-level character parameter overrides only reach the "enforcer" role
  (hub/goal.py's _resolve_parameters); scout/fixer overrides are only
  reachable by hand-authoring a v3 manifest directly.
- directory_structure/external_repos/resources GoalSpec fields are
  schema-validated but not consumed by the planner.

## Known gaps
- scripts/bot_state_machine.gd is a real, working idle/patrol/engage FSM
  but intentionally minimal — not balance-tuned.
- scenes/graybox_district.tscn's NavigationRegion3D ships with an empty
  NavigationMesh (no baked polygon data) — bake it in the editor
  (Navigation dock -> Bake NavigationMesh) before bot pathfinding will move.
- scripts/external/spritebrew/asset_import_pipeline.gd's import_fbx()
  requires the Godot editor/tools binary; it is gated with
  Engine.is_editor_hint() and no-ops in exported/runtime builds.
"""
    data = text.encode("utf-8")
    if not data.endswith(b"\n"):
        data += b"\n"
    return data


def _desired_contents_for_3d(manifest: CreatorManifest) -> dict[str, bytes]:
    contents: dict[str, bytes] = {
        "project.godot": _emit_project_godot_3d(manifest),
        "scenes/player_3d.tscn": _emit_scene_player_3d(manifest),
        "scenes/weapon_base.tscn": _emit_scene_weapon_base(manifest),
        "scenes/ability_base.tscn": _emit_scene_ability_base(manifest),
        "scenes/district_zone.tscn": _emit_scene_district_zone(manifest),
        "scenes/graybox_district.tscn": _emit_scene_graybox_district(manifest),
        "scenes/hud.tscn": _emit_scene_hud(manifest),
        "scripts/game_manager.gd": _emit_behavior_3d("game_manager"),
        "scripts/input_manager.gd": _emit_behavior_3d("input_manager"),
        "scripts/player_controller.gd": _emit_behavior_3d("player_controller_3d"),
        "scripts/hud_controller.gd": _emit_behavior_3d("hud_controller"),
        "scripts/weapon_controller.gd": _emit_behavior_3d("weapon_controller"),
        "scripts/damageable.gd": _emit_behavior_3d("damageable"),
        "scripts/ability_system.gd": _emit_behavior_3d("ability_system"),
        "scripts/district_zone.gd": _emit_behavior_3d("district_zone_behavior"),
        "scripts/bot_state_machine.gd": _emit_behavior_3d("bot_state_machine"),
        "scripts/event_bus.gd": _emit_behavior_3d("event_bus"),
        "scripts/character_data.gd": _emit_behavior_3d("character_data"),
        "scripts/weapon_data.gd": _emit_behavior_3d("weapon_data"),
        "scripts/ability_data.gd": _emit_behavior_3d("ability_data"),
        "scripts/level_setup.gd": _emit_behavior_3d("level_setup"),
        "data/characters/enforcer.tres": _character_tres(manifest, "enforcer"),
        "data/characters/scout.tres": _character_tres(manifest, "scout"),
        "data/characters/fixer.tres": _character_tres(manifest, "fixer"),
        "data/weapons/rifle.tres": _weapon_tres(manifest, "rifle", _WEAPON_STATS["rifle"]),
        "data/weapons/shotgun.tres": _weapon_tres(manifest, "shotgun", _WEAPON_STATS["shotgun"]),
        "data/weapons/sniper.tres": _weapon_tres(manifest, "sniper", _WEAPON_STATS["sniper"]),
        "data/abilities/dash.tres": _ability_tres(manifest, "dash", _ABILITY_STATS["dash"]),
        "data/abilities/shield.tres": _ability_tres(manifest, "shield", _ABILITY_STATS["shield"]),
        "data/abilities/heal.tres": _ability_tres(manifest, "heal", _ABILITY_STATS["heal"]),
        "PROJECT_TRACKING.md": _emit_project_tracking_md(),
    }
    for behavior_id, path in _EXTERNAL_BEHAVIOR_IDS:
        contents[path] = _emit_behavior_3d(behavior_id)
    return contents


def _is_empty_dir(path: Path) -> bool:
    """_is_empty_dir — production helper."""
    try:
        return path.is_dir() and not any(path.iterdir())
    except OSError:
        return False


def _check_preflight(root: Path, g_files: tuple[str, ...], g_dirs: tuple[str, ...]) -> None:
    """Enforce states A/B/C. Raise CreatorPreflightError otherwise.

    State A: empty root — no files at all (only root exists).
    State B: skeleton only — only .godotforge/project.yaml (+ optional .lock)
             plus optionally empty scenes/ and scripts/ dirs.
    State C: handled via no-op (caller compares hashes); preflight here
             allows B to pass; C is not a preflight reject but a plan=None case.

    Any creator_owned file outside these, or non-empty scenes/scripts with
    content, or stray files, or symlink escape, is rejected.
    """
    root = root.resolve()
    if not root.is_dir():
        raise CreatorPreflightError(f"root must be directory, got {root}")
    if (root / "project.godot").is_symlink() or any(
        p.is_symlink() for p in root.rglob("*") if p.is_symlink()
    ):
        # Symlink escape check — reuse scan/profile logic shape
        for p in sorted(root.rglob("*")):
            if p.is_symlink():
                try:
                    p.resolve().relative_to(root.resolve())
                except (OSError, ValueError) as exc:
                    raise CreatorPreflightError(f"symlink escapes root: {p}: {exc}") from exc
    # Hub control plane: the *only* authority for `.godotforge/hub` path
    # handling (godotforge_core.hub_control_plane). Validates `.godotforge`
    # and `.godotforge/hub` are real (non-symlink) directories and that every
    # entry directly under `.godotforge/hub` is one of the exact two known
    # control-plane files, each a real (non-symlink) regular file — never a
    # broad prefix. Anything else (nested files, wrong names, symlinks) is a
    # hard preflight rejection, not a silent skip.
    try:
        hub_metadata_files = validate_hub_metadata_dir(root)
    except HubPathSafetyError as exc:
        raise CreatorPreflightError(str(exc)) from exc
    # Collect relative posix for all files (not dirs)
    rel_files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip ignored .godot (inventory.py IGNORED_DIRS)
        dirnames[:] = [
            d
            for d in dirnames
            if d not in {".godot", ".git", ".pytest-tmp", "__pycache__", "build", "builds"}
        ]
        for fn in filenames:
            fp = Path(dirpath) / fn
            rel = fp.relative_to(root).as_posix()
            # Exactly the two validated Hub control-plane files (never a
            # broad `.godotforge/hub` prefix — see validate_hub_metadata_dir).
            if rel in hub_metadata_files:
                continue
            # Skip .godotforge/cache, /reports, /backups — managed Forge
            # state owned by other subsystems (graph cache, scan reports,
            # patch-engine backups). Anchored on the directory boundary, not
            # a bare string prefix: ".godotforge/cachex" must NOT match.
            if rel in (".godotforge/cache", ".godotforge/reports", ".godotforge/backups") or any(
                rel.startswith(f"{prefix}/")
                for prefix in (
                    ".godotforge/cache",
                    ".godotforge/reports",
                    ".godotforge/backups",
                )
            ):
                continue
            # Skip .godot dir entirely (already pruned but be safe)
            if rel.startswith(".godot/"):
                continue
            rel_files.append(rel)
    rel_files_sorted = sorted(rel_files)
    if not rel_files_sorted:
        # Check dirs: empty or only allowed empty dirs
        # State A — empty root (allow empty template dirs)
        allowed_empty_dirs = {root / d for d in g_dirs}
        for p in root.iterdir():
            if p.is_dir():
                if p in allowed_empty_dirs and _is_empty_dir(p):
                    continue
                # .godotforge may hold managed state only (any unmanaged file
                # inside it would have been collected into rel_files above).
                if p.name == ".godotforge":
                    continue
                # .godot allowed to exist empty or not
                if p.name == ".godot":
                    continue
                raise CreatorPreflightError(f"unexpected directory {p.name} in empty root")
            else:
                raise CreatorPreflightError(f"unexpected file {p.name} in empty root")
        return
    # Non-empty: must be subset of skeleton + optionally empty dirs, or skeleton + G_files
    allowed_files = set(_SKELETON_FILES)
    # Empty dirs allowed even when files present
    for rel in list(rel_files_sorted):
        if rel in allowed_files:
            continue
        # G_files are allowed only if they will be hash-checked as no-op; but preflight
        # must not reject them before hash check — so we permit them here and let caller
        # decide plan is None if hashes match. If hashes differ, that is also allowed
        # as a future overwrite, but PATCH-0012 restricts to empty/template only, so
        # any G_file present with differing content should still be considered
        # "non-empty unmanaged" and rejected unless it exactly matches.
        # To keep preflight distinct from no-op, we allow G_files through and defer
        # content check to the planner's files_ok/dir_ok logic.
        if rel in g_files:
            continue
        raise CreatorPreflightError(
            f"unexpected file {rel} — root must be empty or skeleton/G_files"
        )
    # Also ensure no unexpected top-level dirs with content
    # Empty template dirs are fine; non-empty but only containing G_files is
    # already covered. Stray empty dirs like 'foo/' with no files are caught
    # as unexpected dir containing nothing — but walk found no files there.
    # So check for stray dirs that are empty and not allowed. Only the
    # top-level segment of each g_dir is a direct child of root; nested
    # template dirs (e.g. "scripts/external") are reached by walking into
    # an already-allowed top-level dir, not by this direct-child check.
    allowed_top_level_dir_names = {".godotforge", ".godot"} | {
        d.split("/", 1)[0] for d in g_dirs
    }
    for p in root.iterdir():
        if p.is_dir() and p.name not in allowed_top_level_dir_names:
            # Could be .godotforge subdirs — already file-based check covers
            raise CreatorPreflightError(f"unexpected directory {p.name}")


@dataclass(frozen=True)
class CreatorPatch:
    """Read-only creator patch — plan + desired bytes. No I/O on creation."""

    plan: PatchPlan | None
    desired_contents: dict[str, bytes]
    manifest: CreatorManifest
    reason: str = "creator manifest"

    def content_provider(self):
        """content_provider — production method."""
        desired = self.desired_contents

        def _provider(op) -> bytes | None:
            # op.path for CREATE/MKDIR (mkdir returns None content)
            rel = op.path if op.path is not None else None
            if rel is None:
                return None
            return desired.get(rel)

        return _provider


def _desired_contents_for(manifest: CreatorManifest) -> dict[str, bytes]:
    """_desired_contents_for — dispatches on manifest.template; all
    template-awareness lives here, orchestrator.py needs no changes."""
    if manifest.template == _TEMPLATE_3D:
        return _desired_contents_for_3d(manifest)
    return {
        "project.godot": _emit_project_godot(manifest),
        "scenes/main.tscn": _emit_scene_tscn(manifest),
        "scripts/player_controller.gd": _emit_player_controller(manifest),
        "scripts/coin.gd": _emit_coin(),
    }


def plan_creator_manifest(root: Path | str, manifest_dict: dict) -> CreatorPatch:
    """Validate manifest and produce deterministic plan for empty/template root.

    No filesystem writes, no backup/apply, no engine invocation, no network/AI.
    Raises CreatorPreflightError or ValueError on invalid manifest or non-empty root.
    """
    manifest = validate_manifest_dict(manifest_dict)
    root = Path(root).resolve()
    g_files = _g_files_for(manifest)
    g_dirs = _g_dirs_for(manifest)
    _check_preflight(root, g_files, g_dirs)

    desired = _desired_contents_for(manifest)

    # Separate checks per amendment 7: files_ok vs dirs_ok
    files_ok = True
    for rel in g_files:
        p = root / rel
        if not p.is_file():
            files_ok = False
            break
        try:
            if hashlib.sha256(p.read_bytes()).hexdigest() != hash_bytes(desired[rel]):
                files_ok = False
                break
        except OSError:
            files_ok = False
            break
    dirs_ok = all((root / d).is_dir() and not (root / d).is_symlink() for d in g_dirs)

    if files_ok and dirs_ok:
        return CreatorPatch(plan=None, desired_contents=desired, manifest=manifest)

    # Build ops in (MKDIR=0, CREATE=1, path) order — MKDIR
    # suppressed for existing non-symlink dirs
    ops: list[PatchOperation] = []
    for d in sorted(g_dirs):
        dir_path = root / d
        if dir_path.is_dir() and not dir_path.is_symlink():
            continue
        ops.append(
            PatchOperation(
                kind=OperationKind.MKDIR,
                path=d,
                owner="godotforge",
                source="creator",
                reason="creator manifest",
            )
        )
    # CREATEs sorted lexicographically by path.
    for rel in sorted(g_files):
        ops.append(
            PatchOperation(
                kind=OperationKind.CREATE,
                path=rel,
                desired_hash=hash_bytes(desired[rel]),
                owner="godotforge",
                source="creator",
                reason="creator manifest",
            )
        )
    # Enforce ordering rule explicitly: MKDIR before CREATE, then lexicographic
    # Already built as such; assert invariant
    kind_rank = {OperationKind.MKDIR: 0, OperationKind.CREATE: 1}
    for a, b in zip(ops, ops[1:]):
        assert (kind_rank[a.kind], a.path) <= (
            kind_rank[b.kind],
            b.path,
        ), f"ordering violated: {a} before {b}"

    plan_id = _plan_id_for(manifest)
    plan = PatchPlan(id=plan_id, operations=tuple(ops))
    return CreatorPatch(plan=plan, desired_contents=desired, manifest=manifest)
