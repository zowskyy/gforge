"""Template identity spec loader — Phase 2a of
``~/.claude/plans/claude-district-reactive-bear.md``.

Before this module existed, "what templates exist, what fixed inputs and
parameter keys each one has" was hand-duplicated in at least two independent
places (``hub/goal.py``'s ``_TEMPLATES``/``_ALLOWED_*_KEYS_*``/``_FIXED_INPUTS*``,
and ``creator/manifest.py``'s parallel constants), enforced to agree only by
``tests/unit/test_template_identity_consistency.py``'s drift checks.

This module makes ``templates/<id>.spec.yaml`` the single declarative
source for that identity data: ``hub/goal.py`` now derives its constants
from :func:`load_template_spec` instead of hand-typing them a second time.
It is deliberately *not* the numeric-range validation authority —
``creator/manifest.py``'s ``Decimal`` MIN/MAX/DEFAULT constants remain that
(per that module's own docstring: "Range, precision, and canonical-format
enforcement stay with ``validate_manifest_dict``"). The spec's min/max/
default fields exist so a drift test
(``tests/unit/test_template_spec_consistency.py``) can catch the two ever
disagreeing, without re-deriving runtime validation logic from YAML.

No AI, network, or filesystem mutation — pure, read-only parsing of
packaged data files.
"""

from __future__ import annotations

import importlib.resources
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from typing import Any

import yaml

_TEMPLATES_PACKAGE = "godotforge_core.templates"


@dataclass(frozen=True)
class ParamRange:
    """ParamRange — one parameter's informational min/max/default, as
    declared in a template spec. ``default`` is ``None`` for parameter
    families (weapon/ability stats) that have no fixed template default —
    an omitted override simply keeps the template's built-in stat."""

    min: Decimal | int
    max: Decimal | int
    default: Decimal | int | None = None


@dataclass(frozen=True)
class FixedInput:
    """FixedInput — one always-present input action binding."""

    name: str
    binding: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "binding": self.binding}


@dataclass(frozen=True)
class BehaviorSpec:
    """BehaviorSpec — one goal-level behavior/role's tunable parameters."""

    parameters: dict[str, ParamRange]


@dataclass(frozen=True)
class WeaponSpec:
    """WeaponSpec — the weapon id list and shared per-field ranges for a
    template that supports ``weapon_overrides``."""

    ids: tuple[str, ...]
    parameters: dict[str, ParamRange]


@dataclass(frozen=True)
class AbilitySpec:
    """AbilitySpec — the ability id list and shared per-field ranges for a
    template that supports ``ability_overrides``."""

    ids: tuple[str, ...]
    parameters: dict[str, ParamRange]


@dataclass(frozen=True)
class TemplateSpec:
    """TemplateSpec — one template's full declarative identity, parsed from
    ``templates/<template_id>.spec.yaml``."""

    template_id: str
    schema_version: int
    fixed_inputs: tuple[FixedInput, ...]
    behaviors: dict[str, BehaviorSpec]
    behavior_resource_ids: tuple[str, ...]
    weapons: WeaponSpec | None = None
    abilities: AbilitySpec | None = None

    def allowed_behavior_keys(self) -> frozenset[str]:
        """allowed_behavior_keys — goal-level ``parameters`` block keys this
        template accepts (its role/behavior ids)."""
        return frozenset(self.behaviors)

    def allowed_parameter_keys(self) -> frozenset[str]:
        """allowed_parameter_keys — the parameter field names accepted
        within *any* of this template's behaviors. Every behavior in a
        template shares the same field set today (enforced by
        :func:`_parse_template_spec`); this is the union, matching how
        ``hub/goal.py``'s single ``_ALLOWED_PARAMETER_KEYS_*`` constant is
        used regardless of which role is being resolved."""
        keys: set[str] = set()
        for behavior in self.behaviors.values():
            keys |= set(behavior.parameters)
        return frozenset(keys)


def _parse_param_range(raw: dict[str, Any], *, field: str) -> ParamRange:
    if "min" not in raw or "max" not in raw:
        raise ValueError(f"{field}: spec parameter range must have 'min' and 'max'")
    is_int_range = isinstance(raw["min"], int) and isinstance(raw["max"], int)
    if is_int_range:
        default = raw.get("default")
        if default is not None and not isinstance(default, int):
            raise ValueError(f"{field}: int-ranged parameter must have an int default")
        return ParamRange(min=raw["min"], max=raw["max"], default=default)
    default_raw = raw.get("default")
    return ParamRange(
        min=Decimal(str(raw["min"])),
        max=Decimal(str(raw["max"])),
        default=Decimal(str(default_raw)) if default_raw is not None else None,
    )


def _parse_template_spec(raw: dict[str, Any], *, source: str) -> TemplateSpec:
    template_id = raw.get("template_id")
    if not isinstance(template_id, str) or not template_id:
        raise ValueError(f"{source}: template_id is required")
    schema_version = raw.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError(f"{source}: schema_version must be an int")

    fixed_inputs = tuple(
        FixedInput(name=entry["name"], binding=entry["binding"])
        for entry in raw.get("fixed_inputs", [])
    )

    behaviors_raw = raw.get("behaviors")
    if not isinstance(behaviors_raw, dict) or not behaviors_raw:
        raise ValueError(f"{source}: at least one behavior is required")
    behaviors: dict[str, BehaviorSpec] = {}
    field_sets: set[frozenset[str]] = set()
    for behavior_id, behavior_raw in behaviors_raw.items():
        params_raw = behavior_raw.get("parameters", {})
        parameters = {
            name: _parse_param_range(spec, field=f"{source}:{behavior_id}.{name}")
            for name, spec in params_raw.items()
        }
        behaviors[behavior_id] = BehaviorSpec(parameters=parameters)
        field_sets.add(frozenset(parameters))
    if len(field_sets) > 1:
        raise ValueError(
            f"{source}: all behaviors must share the same parameter field set "
            f"(hub/goal.py's _ALLOWED_PARAMETER_KEYS_* is not per-role); got {field_sets}"
        )

    weapons_raw = raw.get("weapons")
    weapons = None
    if weapons_raw is not None:
        weapons = WeaponSpec(
            ids=tuple(weapons_raw["ids"]),
            parameters={
                name: _parse_param_range(spec, field=f"{source}:weapons.{name}")
                for name, spec in weapons_raw.get("parameters", {}).items()
            },
        )

    abilities_raw = raw.get("abilities")
    abilities = None
    if abilities_raw is not None:
        abilities = AbilitySpec(
            ids=tuple(abilities_raw["ids"]),
            parameters={
                name: _parse_param_range(spec, field=f"{source}:abilities.{name}")
                for name, spec in abilities_raw.get("parameters", {}).items()
            },
        )

    behavior_resource_ids = tuple(raw.get("behavior_resource_ids", ()))

    return TemplateSpec(
        template_id=template_id,
        schema_version=schema_version,
        fixed_inputs=fixed_inputs,
        behaviors=behaviors,
        behavior_resource_ids=behavior_resource_ids,
        weapons=weapons,
        abilities=abilities,
    )


@cache
def registered_template_ids() -> tuple[str, ...]:
    """registered_template_ids — sorted tuple of template ids with a spec
    file, discovered from the packaged ``templates/`` resource directory."""
    package = importlib.resources.files(_TEMPLATES_PACKAGE)
    ids = sorted(
        entry.name.removesuffix(".spec.yaml")
        for entry in package.iterdir()
        if entry.name.endswith(".spec.yaml")
    )
    return tuple(ids)


@cache
def load_template_spec(template_id: str) -> TemplateSpec:
    """load_template_spec — parse and cache one template's spec file.

    Raises ``FileNotFoundError`` if no spec exists for *template_id*, or
    ``ValueError`` if the spec file is malformed.
    """
    resource = importlib.resources.files(_TEMPLATES_PACKAGE).joinpath(
        f"{template_id}.spec.yaml"
    )
    try:
        text = resource.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"no template spec for {template_id!r}; registered: {registered_template_ids()}"
        ) from None
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise ValueError(f"{template_id}.spec.yaml: expected a mapping at the top level")
    return _parse_template_spec(raw, source=f"{template_id}.spec.yaml")


def load_all_template_specs() -> dict[str, TemplateSpec]:
    """load_all_template_specs — every registered template's spec, keyed by
    id."""
    return {tid: load_template_spec(tid) for tid in registered_template_ids()}
