"""Manifest ingestion boundary — Decimal-preserving YAML/JSON loaders.

Numeric scalars must reach ``creator.numfmt`` without passing through binary
``float``: ``yaml.safe_load`` would turn ``speed: 250.0`` into a Python
``float`` and the canonical serializer would then reject the manifest's own
documented format. This module defines the single ingestion boundary:

- YAML: safe loader only; a custom numeric scalar constructor preserves the
  original scalar text as :class:`~decimal.Decimal`; no arbitrary YAML tags
  or constructors are allowed (``SafeLoader`` rejects them).
- JSON: ``parse_float=Decimal`` (integers stay ``int``, which is exact);
  ``parse_constant`` rejects ``NaN``/``Infinity``/``-Infinity``.
- Duplicate mapping keys are rejected in both formats (fail at load, never
  last-wins), per the PATCH-0016 manifest contract.

Exponent notation (``2.5e2``) is accepted as input when valid and is never
emitted in canonical output (``250.0``); that normalization lives in
``creator.numfmt``.

No AI, network, or telemetry dependency.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

import yaml

_NEGATIVE_ZERO_SCALAR_RE = re.compile(r"^-0+(\.0*)?([eE][+-]?0+)?$")


class _DecimalSafeLoader(yaml.SafeLoader):
    """Safe YAML loader that preserves float scalars as Decimal.

    Only ``tag:yaml.org,2002:float`` construction is overridden; all other
    tags keep the strict ``SafeLoader`` behavior, and unknown tags still
    raise ``ConstructorError``.
    """


def _construct_decimal_float(loader: _DecimalSafeLoader, node: yaml.nodes.ScalarNode) -> Decimal:
    """Construct a float-tagged scalar as Decimal from its original text.

    The raw scalar (e.g. ``250.0``, ``2.5e2``) is converted directly via
    :class:`~decimal.Decimal`, never via binary ``float``. YAML-only forms
    that are not plain ASCII numeric literals (``.inf``, ``.nan``,
    sexagesimal) raise ``ValueError`` here at the ingestion boundary.
    """
    scalar = loader.construct_scalar(node)
    try:
        return Decimal(scalar)
    except Exception as exc:
        raise ValueError(f"not a plain ASCII numeric scalar: {scalar!r}") from exc


def _construct_int_preserving_negative_zero(
    loader: _DecimalSafeLoader, node: yaml.nodes.ScalarNode
) -> int | Decimal:
    """Construct int scalars normally, but keep ``-0`` as Decimal for rejection.

    Binary ``int`` cannot represent negative zero, so a ``-0`` scalar is
    returned as ``Decimal("-0")`` to let ``creator.numfmt`` reject it with
    the contract-mandated negative-zero error.
    """
    scalar = loader.construct_scalar(node)
    if _NEGATIVE_ZERO_SCALAR_RE.match(scalar):
        return Decimal(scalar)
    return yaml.SafeLoader.construct_yaml_int(loader, node)


def _construct_mapping_no_duplicates(
    loader: _DecimalSafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    """Construct a mapping, rejecting duplicate keys instead of last-wins."""
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise ValueError(f"duplicate key in manifest mapping: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_DecimalSafeLoader.add_constructor("tag:yaml.org,2002:float", _construct_decimal_float)
_DecimalSafeLoader.add_constructor("tag:yaml.org,2002:int", _construct_int_preserving_negative_zero)
_DecimalSafeLoader.add_constructor("tag:yaml.org,2002:map", _construct_mapping_no_duplicates)


def _json_reject_constant(value: str) -> None:
    """Reject JSON NaN/Infinity/-Infinity constants at parse time."""
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


def _json_object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build a JSON object, rejecting duplicate keys instead of last-wins."""
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError(f"duplicate key in manifest object: {key!r}")
        mapping[key] = value
    return mapping


def load_yaml_manifest(text: str) -> dict[str, Any]:
    """Parse a YAML manifest, preserving numeric scalars as Decimal.

    Returns the top-level mapping. Raises ``ValueError`` for non-mapping
    documents, duplicate keys, or non-plain numeric scalars, and
    ``yaml.YAMLError`` for malformed YAML.
    """
    data = yaml.load(text, Loader=_DecimalSafeLoader)  # noqa: S506 — custom SafeLoader
    if not isinstance(data, dict):
        raise ValueError("manifest must be a mapping")
    return data


def load_json_manifest(text: str) -> dict[str, Any]:
    """Parse a JSON manifest with ``parse_float=Decimal`` and duplicate rejection.

    Integers parse as exact ``int``; fractional numbers parse as
    :class:`~decimal.Decimal`; ``NaN``/``Infinity`` constants are rejected.
    """
    data = json.loads(
        text,
        parse_float=Decimal,
        parse_constant=_json_reject_constant,
        object_pairs_hook=_json_object_no_duplicates,
    )
    if not isinstance(data, dict):
        raise ValueError("manifest must be a mapping")
    return data
