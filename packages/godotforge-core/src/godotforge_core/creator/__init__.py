"""Creator package — deterministic, offline, AI-free.

PATCH-0012 Creator Manifest Planning Slice only produces read-only plans.
No LLM, network, telemetry, model runtime, or generated source is used.
"""

from .manifest import (
    CreatorInput,
    CreatorManifest,
    CreatorPreflightError,
    parse_creator_manifest,
    validate_manifest_dict,
)
from .plan import CreatorPatch, plan_creator_manifest
from .uid import deterministic_uid

__all__ = [
    "CreatorInput",
    "CreatorManifest",
    "CreatorPatch",
    "CreatorPreflightError",
    "deterministic_uid",
    "parse_creator_manifest",
    "plan_creator_manifest",
    "validate_manifest_dict",
]
