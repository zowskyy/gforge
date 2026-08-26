"""Phase 2a drift guard — templates/<id>.spec.yaml is the single declarative
source `hub/goal.py`'s per-template constants are now derived from (see
`creator/template_spec.py`'s module docstring), but `creator/manifest.py`'s
`Decimal` MIN/MAX/DEFAULT constants deliberately remain hand-authored and
runtime-authoritative (range/precision enforcement is their job, not the
spec's — re-deriving validation logic from YAML would be a much riskier
change than Phase 2a's "lower risk, do first" scope). This module is what
keeps the two from silently disagreeing: a spec value drifting from
manifest.py's real enforced range would otherwise let a goal claim a wider
range than compile_goal() actually accepts, or vice versa.

Also verifies the two other Phase 2a codegen targets named in the roadmap
plan: schemas/goal.schema.json's game.template enum, and every template's
declared GDScript behavior_resource_ids existing in the hash registry.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from godotforge_core.behaviors.registry import _ALLOWLIST, PINNED_HASHES
from godotforge_core.creator.manifest import (
    _ABILITY_COOLDOWN_MAX,
    _ABILITY_COOLDOWN_MIN,
    _ABILITY_DURATION_MAX,
    _ABILITY_DURATION_MIN,
    _ABILITY_IDS,
    _ABILITY_MAGNITUDE_MAX,
    _ABILITY_MAGNITUDE_MIN,
    _ABILITY_RADIUS_MAX,
    _ABILITY_RADIUS_MIN,
    _ENFORCER_ARMOR_DEFAULT,
    _ENFORCER_ARMOR_MAX,
    _ENFORCER_ARMOR_MIN,
    _ENFORCER_HEALTH_DEFAULT,
    _ENFORCER_HEALTH_MAX,
    _ENFORCER_HEALTH_MIN,
    _ENFORCER_MOVE_SPEED_DEFAULT,
    _ENFORCER_MOVE_SPEED_MAX,
    _ENFORCER_MOVE_SPEED_MIN,
    _ENFORCER_SPRINT_DEFAULT,
    _ENFORCER_SPRINT_MAX,
    _ENFORCER_SPRINT_MIN,
    _FIXER_ARMOR_DEFAULT,
    _FIXER_ARMOR_MAX,
    _FIXER_ARMOR_MIN,
    _FIXER_HEALTH_DEFAULT,
    _FIXER_HEALTH_MAX,
    _FIXER_HEALTH_MIN,
    _FIXER_MOVE_SPEED_DEFAULT,
    _FIXER_MOVE_SPEED_MAX,
    _FIXER_MOVE_SPEED_MIN,
    _FIXER_SPRINT_DEFAULT,
    _FIXER_SPRINT_MAX,
    _FIXER_SPRINT_MIN,
    _JUMP_DEFAULT,
    _JUMP_MAX,
    _JUMP_MIN,
    _SCOUT_ARMOR_DEFAULT,
    _SCOUT_ARMOR_MAX,
    _SCOUT_ARMOR_MIN,
    _SCOUT_HEALTH_DEFAULT,
    _SCOUT_HEALTH_MAX,
    _SCOUT_HEALTH_MIN,
    _SCOUT_MOVE_SPEED_DEFAULT,
    _SCOUT_MOVE_SPEED_MAX,
    _SCOUT_MOVE_SPEED_MIN,
    _SCOUT_SPRINT_DEFAULT,
    _SCOUT_SPRINT_MAX,
    _SCOUT_SPRINT_MIN,
    _SPEED_DEFAULT,
    _SPEED_MAX,
    _SPEED_MIN,
    _WEAPON_DAMAGE_MAX,
    _WEAPON_DAMAGE_MIN,
    _WEAPON_FIRE_RATE_MAX,
    _WEAPON_FIRE_RATE_MIN,
    _WEAPON_IDS,
    _WEAPON_MAGAZINE_SIZE_MAX,
    _WEAPON_MAGAZINE_SIZE_MIN,
    _WEAPON_PELLET_COUNT_MAX,
    _WEAPON_PELLET_COUNT_MIN,
    _WEAPON_RELOAD_TIME_MAX,
    _WEAPON_RELOAD_TIME_MIN,
)
from godotforge_core.creator.template_spec import (
    ParamRange,
    load_template_spec,
    registered_template_ids,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "goal.schema.json"


def _range(min_: Decimal | int, max_: Decimal | int, default: Decimal | int | None = None) -> ParamRange:
    return ParamRange(min=min_, max=max_, default=default)


def test_2d_spec_matches_manifest_authority() -> None:
    spec = load_template_spec("2d-platformer-minimal")
    params = spec.behaviors["platformer_controller"].parameters
    assert params["speed"] == _range(_SPEED_MIN, _SPEED_MAX, _SPEED_DEFAULT)
    assert params["jump_velocity"] == _range(_JUMP_MIN, _JUMP_MAX, _JUMP_DEFAULT)


def test_3d_character_spec_matches_manifest_authority() -> None:
    spec = load_template_spec("3d-tactical-shooter")
    expected = {
        "enforcer": {
            "health": _range(_ENFORCER_HEALTH_MIN, _ENFORCER_HEALTH_MAX, _ENFORCER_HEALTH_DEFAULT),
            "armor": _range(_ENFORCER_ARMOR_MIN, _ENFORCER_ARMOR_MAX, _ENFORCER_ARMOR_DEFAULT),
            "move_speed": _range(
                _ENFORCER_MOVE_SPEED_MIN, _ENFORCER_MOVE_SPEED_MAX, _ENFORCER_MOVE_SPEED_DEFAULT
            ),
            "sprint_multiplier": _range(
                _ENFORCER_SPRINT_MIN, _ENFORCER_SPRINT_MAX, _ENFORCER_SPRINT_DEFAULT
            ),
        },
        "scout": {
            "health": _range(_SCOUT_HEALTH_MIN, _SCOUT_HEALTH_MAX, _SCOUT_HEALTH_DEFAULT),
            "armor": _range(_SCOUT_ARMOR_MIN, _SCOUT_ARMOR_MAX, _SCOUT_ARMOR_DEFAULT),
            "move_speed": _range(
                _SCOUT_MOVE_SPEED_MIN, _SCOUT_MOVE_SPEED_MAX, _SCOUT_MOVE_SPEED_DEFAULT
            ),
            "sprint_multiplier": _range(_SCOUT_SPRINT_MIN, _SCOUT_SPRINT_MAX, _SCOUT_SPRINT_DEFAULT),
        },
        "fixer": {
            "health": _range(_FIXER_HEALTH_MIN, _FIXER_HEALTH_MAX, _FIXER_HEALTH_DEFAULT),
            "armor": _range(_FIXER_ARMOR_MIN, _FIXER_ARMOR_MAX, _FIXER_ARMOR_DEFAULT),
            "move_speed": _range(
                _FIXER_MOVE_SPEED_MIN, _FIXER_MOVE_SPEED_MAX, _FIXER_MOVE_SPEED_DEFAULT
            ),
            "sprint_multiplier": _range(_FIXER_SPRINT_MIN, _FIXER_SPRINT_MAX, _FIXER_SPRINT_DEFAULT),
        },
    }
    for role, fields in expected.items():
        for field, want in fields.items():
            got = spec.behaviors[role].parameters[field]
            assert got == want, f"{role}.{field}: spec has {got}, manifest.py has {want}"


def test_weapon_spec_matches_manifest_authority() -> None:
    spec = load_template_spec("3d-tactical-shooter")
    assert spec.weapons is not None
    assert set(spec.weapons.ids) == _WEAPON_IDS
    params = spec.weapons.parameters
    assert params["damage"] == _range(_WEAPON_DAMAGE_MIN, _WEAPON_DAMAGE_MAX)
    assert params["fire_rate"] == _range(_WEAPON_FIRE_RATE_MIN, _WEAPON_FIRE_RATE_MAX)
    assert params["magazine_size"] == _range(_WEAPON_MAGAZINE_SIZE_MIN, _WEAPON_MAGAZINE_SIZE_MAX)
    assert params["pellet_count"] == _range(_WEAPON_PELLET_COUNT_MIN, _WEAPON_PELLET_COUNT_MAX)
    assert params["reload_time"] == _range(_WEAPON_RELOAD_TIME_MIN, _WEAPON_RELOAD_TIME_MAX)


def test_ability_spec_matches_manifest_authority() -> None:
    spec = load_template_spec("3d-tactical-shooter")
    assert spec.abilities is not None
    assert set(spec.abilities.ids) == _ABILITY_IDS
    params = spec.abilities.parameters
    assert params["cooldown"] == _range(_ABILITY_COOLDOWN_MIN, _ABILITY_COOLDOWN_MAX)
    assert params["duration"] == _range(_ABILITY_DURATION_MIN, _ABILITY_DURATION_MAX)
    assert params["magnitude"] == _range(_ABILITY_MAGNITUDE_MIN, _ABILITY_MAGNITUDE_MAX)
    assert params["radius"] == _range(_ABILITY_RADIUS_MIN, _ABILITY_RADIUS_MAX)


def test_schema_template_enum_matches_registered_spec_ids() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schema_templates = set(schema["properties"]["game"]["properties"]["template"]["enum"])
    assert schema_templates == set(registered_template_ids()), (
        f"schemas/goal.schema.json's game.template enum {sorted(schema_templates)} "
        f"disagrees with the registered template specs {registered_template_ids()}"
    )


def test_behavior_resource_ids_are_registered() -> None:
    """Every GDScript behavior id a template spec declares it emits must
    exist in behaviors/registry.py's _ALLOWLIST/PINNED_HASHES — this is
    Phase 2a's "hash-registry skeleton" codegen target: for the two
    existing templates this closes the loop retroactively; for a future
    third template, this test is what would catch a spec claiming a
    behavior id nobody ran tools/register_behavior.py for yet."""
    violations: list[str] = []
    for template_id in registered_template_ids():
        spec = load_template_spec(template_id)
        for behavior_id in spec.behavior_resource_ids:
            if behavior_id not in _ALLOWLIST or behavior_id not in PINNED_HASHES:
                violations.append(f"{template_id}: {behavior_id!r}")
    assert not violations, (
        "template spec declares behavior_resource_ids with no registry entry "
        "(run tools/register_behavior.py to add one): " + ", ".join(violations)
    )
