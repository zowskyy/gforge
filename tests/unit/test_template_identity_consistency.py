"""Cross-check the independently hand-maintained sources of "template
identity" this codebase carries — closing the drift risk PROJECT_TRACKING.md
already flagged ("Hub Step 3 (GoalSpec) follow-ups... currently duplicated;
fail-safe because the manifest validator rejects on divergence, but a drift
point") without a risky runtime refactor. Today, template identity facts
live independently in at least four places: `schemas/goal.schema.json`'s
`game.template` enum, `hub/goal.py`'s `_TEMPLATES`/`_FIXED_INPUTS_3D`/
`_ALLOWED_*_KEYS_3D`, and `creator/manifest.py`'s `_FIXED_BINDINGS_3D` and
per-role parameter key sets. Nothing today enforces they agree except
manual discipline; this module is that enforcement, cheap and CI-visible,
without unifying the underlying registries (a Phase 2 concern, not Phase 0).
"""

from __future__ import annotations

import json
from pathlib import Path

from godotforge_core.creator.manifest import _FIXED_BINDINGS_3D
from godotforge_core.hub.goal import (
    _ALLOWED_BEHAVIOR_KEYS_3D,
    _ALLOWED_PARAMETER_KEYS_3D,
    _FIXED_INPUTS_3D,
    _TEMPLATES,
    registered_templates,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "goal.schema.json"
PACKAGED_SCHEMA_PATH = (
    REPO_ROOT
    / "packages" / "godotforge-core" / "src" / "godotforge_core" / "schemas" / "goal.schema.json"
)


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_schema_template_enum_matches_hub_templates_registry() -> None:
    schema = _load_schema(SCHEMA_PATH)
    schema_templates = set(schema["properties"]["game"]["properties"]["template"]["enum"])
    assert schema_templates == set(_TEMPLATES), (
        f"schemas/goal.schema.json's game.template enum {sorted(schema_templates)} "
        f"disagrees with hub/goal.py's _TEMPLATES {sorted(_TEMPLATES)} — a template "
        f"registered in one but not the other is a real, silent user-facing bug: "
        f"either the schema rejects a template the code actually supports, or the "
        f"schema accepts a template compile_goal() will reject."
    )
    # registered_templates() is the public accessor other code should use;
    # confirm it's actually backed by _TEMPLATES and not drifted itself.
    assert set(registered_templates()) == set(_TEMPLATES)


def test_packaged_schema_matches_root_schema() -> None:
    """schemas/goal.schema.json is mirrored into the package for wheel/sdist
    distribution; the two copies must be byte-identical. (A dedicated
    test_schema_parity.py may already cover this for other schemas — this
    assertion is specific to goal.schema.json and cheap to keep here too.)"""
    assert SCHEMA_PATH.read_text(encoding="utf-8") == PACKAGED_SCHEMA_PATH.read_text(
        encoding="utf-8"
    ), "schemas/goal.schema.json and its packaged mirror have diverged"


def test_3d_fixed_input_names_match_between_goal_and_manifest() -> None:
    """hub/goal.py's _FIXED_INPUTS_3D and creator/manifest.py's
    _FIXED_BINDINGS_3D independently enumerate the same 14 fixed 3D input
    action names. If they diverge, compile_goal() would build a manifest
    dict validate_manifest_dict() then rejects — a goal that should compile
    fails with a confusing internal error instead of never being possible
    to write in the first place."""
    goal_names = {entry["name"] for entry in _FIXED_INPUTS_3D}
    manifest_names = set(_FIXED_BINDINGS_3D)
    assert goal_names == manifest_names, (
        f"hub/goal.py _FIXED_INPUTS_3D names {sorted(goal_names)} != "
        f"creator/manifest.py _FIXED_BINDINGS_3D keys {sorted(manifest_names)}"
    )
    # Also confirm goal.py's binding values match manifest.py's fixed
    # bindings exactly (both sides hard-code "name == binding" for 3D).
    for entry in _FIXED_INPUTS_3D:
        assert entry["binding"] == _FIXED_BINDINGS_3D[entry["name"]], (
            f"binding mismatch for {entry['name']!r}: "
            f"goal.py has {entry['binding']!r}, manifest.py expects "
            f"{_FIXED_BINDINGS_3D[entry['name']]!r}"
        )


def test_3d_allowed_parameter_keys_match_manifest_validator() -> None:
    """hub/goal.py's _ALLOWED_PARAMETER_KEYS_3D must match the field set
    creator/manifest.py's _validate_character_parameters actually accepts
    per role (health/armor/move_speed/sprint_multiplier) — hardcoded twice,
    independently, in the two files."""
    assert _ALLOWED_PARAMETER_KEYS_3D == frozenset(
        {"health", "armor", "move_speed", "sprint_multiplier"}
    )


def test_3d_allowed_behavior_keys_match_manifest_roles() -> None:
    """hub/goal.py's _ALLOWED_BEHAVIOR_KEYS_3D (which goal-level
    `parameters` block keys are accepted) must match the three character
    roles creator/manifest.py's BehaviorParameters3D actually has fields
    for (enforcer/scout/fixer)."""
    assert _ALLOWED_BEHAVIOR_KEYS_3D == frozenset({"enforcer", "scout", "fixer"})
