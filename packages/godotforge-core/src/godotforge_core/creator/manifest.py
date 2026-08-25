"""Creator manifest validation — deterministic, offline, AI-free.

The manifest is an internal contract produced by forms/templates/fixtures,
never by an LLM at runtime. All generation after this point is offline.

No AI, network, telemetry, model runtime, or generated source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FIXED_BINDINGS: dict[str, str] = {
    "move_left": "ui_left",
    "move_right": "ui_right",
    "jump": "ui_accept",
}
_REQUIRED_NAMES = frozenset(_FIXED_BINDINGS.keys())
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _-]+$")
_TEMPLATE_CONST = "2d-platformer-minimal"


class CreatorPreflightError(ValueError):
    """Root or manifest fails empty/template preflight (states A/B/C)."""


@dataclass(frozen=True)
class CreatorInput:
    """CreatorInput — production class."""
    name: str
    binding: str


@dataclass(frozen=True)
class CreatorManifest:
    """CreatorManifest — production class."""
    schema_version: int
    game_name: str
    template: str
    inputs: tuple[CreatorInput, ...]

    def as_dict(self) -> dict:
        """as_dict — production method."""
        return {
            "schema_version": self.schema_version,
            "game": {"name": self.game_name, "template": self.template},
            "input": [{"name": i.name, "binding": i.binding} for i in self.inputs],
        }


def _validate_game_name(name: str) -> None:
    """_validate_game_name — production helper."""
    if not isinstance(name, str) or not name:
        raise ValueError("game.name must be non-empty string")
    if len(name) > 64:
        raise ValueError(f"game.name too long ({len(name)} > 64): {name!r}")
    if "\r" in name or "\n" in name or "\x00" in name:
        raise ValueError(f"game.name must not contain CR/LF/NUL: {name!r}")
    if not _NAME_PATTERN.match(name):
        raise ValueError(f"game.name must match ^[A-Za-z0-9 _-]+$: {name!r}")


def validate_manifest_dict(data: dict) -> CreatorManifest:
    """Validate raw dict per schema and fixed v1 rules; return frozen CreatorManifest.

    Enforces:
      - schema_version == 1
      - game.name pattern / length / no CR/LF/NUL
      - template == 2d-platformer-minimal
      - input exactly 3 entries, names exactly {move_left, move_right, jump} each once
      - fixed bindings per name (no duplicates/omissions/unknowns)
    """
    if not isinstance(data, dict):
        raise ValueError("manifest must be dict")
    if data.get("schema_version") != 1:
        raise ValueError(f"schema_version must be 1, got {data.get('schema_version')!r}")
    game = data.get("game")
    if not isinstance(game, dict):
        raise ValueError("game must be object")
    name = game.get("name")
    template = game.get("template")
    _validate_game_name(name)  # type: ignore[arg-type]
    if template != _TEMPLATE_CONST:
        raise ValueError(f"game.template must be {_TEMPLATE_CONST!r}, got {template!r}")
    raw_inputs = data.get("input")
    if not isinstance(raw_inputs, list) or len(raw_inputs) != 3:
        raise ValueError(f"input must be array of exactly 3, got {raw_inputs!r}")
    seen: set[str] = set()
    inputs: list[CreatorInput] = []
    for entry in raw_inputs:
        if not isinstance(entry, dict):
            raise ValueError(f"input entry must be object, got {entry!r}")
        iname = entry.get("name")
        binding = entry.get("binding")
        if not isinstance(iname, str) or iname not in _FIXED_BINDINGS:
            raise ValueError(
                f"unknown or missing input name {iname!r}; "
                f"required {sorted(_REQUIRED_NAMES)}"
            )
        if not isinstance(binding, str):
            raise ValueError(f"binding must be string for {iname!r}, got {binding!r}")
        if iname in seen:
            raise ValueError(f"duplicate input name {iname!r}")
        seen.add(iname)
        expected = _FIXED_BINDINGS[iname]
        if binding != expected:
            raise ValueError(f"fixed binding for {iname!r} must be {expected!r}, got {binding!r}")
        inputs.append(CreatorInput(name=iname, binding=binding))
    if seen != _REQUIRED_NAMES:
        raise ValueError(
            f"input must contain exactly {sorted(_REQUIRED_NAMES)}, "
            f"got {sorted(seen)}"
        )
    # Sort inputs by canonical order move_left, move_right, jump for determinism
    order = {"move_left": 0, "move_right": 1, "jump": 2}
    inputs.sort(key=lambda x: order[x.name])
    assert isinstance(name, str)
    assert isinstance(template, str)
    return CreatorManifest(
        schema_version=1,
        game_name=name,
        template=template,
        inputs=tuple(inputs),
    )


def parse_creator_manifest(data: dict) -> CreatorManifest:
    """Alias for validate_manifest_dict (read-only, no I/O)."""
    return validate_manifest_dict(data)
