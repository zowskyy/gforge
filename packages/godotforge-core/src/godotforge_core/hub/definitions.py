"""Spoke definitions — frozen capability contracts for Hub plugins.

A :class:`SpokeDefinition` declares what a spoke *can do* (capabilities,
permissions) and attests determinism/offline operation. Definitions carry no
I/O and no behavior; providers (existing package code behind a registration
adapter) supply behavior. Identity hashes are derived from canonical
serialization only — never from Python object representations or memory
addresses.

Offline, deterministic, no AI, network, telemetry, or credentials.
See ``docs/contracts/hub-v1.md`` §1 and ``schemas/spoke-definition.schema.json``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

SPOKE_DEFINITION_SCHEMA_VERSION = 1

_SPOKE_ID_PATTERN = re.compile(r"^spoke\.[a-z0-9-]+$")
_CAPABILITY_ID_PATTERN = re.compile(r"^[a-z0-9]+(\.[a-z0-9-]+)+$")
_SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_CONFIG_KEY_PATTERN = re.compile(r"^[a-z0-9_.-]+$")


class Permission(StrEnum):
    """Permission — declared capability requirements, checked by gates.

    Registry permissions are *declarations only*. They never grant access:
    any capability whose spoke declares ``filesystem_write`` or
    ``engine_invoke`` may only be invoked through the Hub registry with a
    recorded authorization (see ``hub/registry.py``), and all filesystem
    mutation still flows through the patch engine's
    check_plan → backup → apply pipeline. The registry contains no apply,
    subprocess, or network code.
    """

    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"
    ENGINE_INVOKE = "engine_invoke"


@dataclass(frozen=True)
class Capability:
    """Capability — one namespaced, invocable capability of a spoke.

    Capability IDs are namespaced dotted paths (e.g. ``patch.apply``),
    unique within a definition and across all active spokes in a registry.
    """

    id: str
    description: str

    def __post_init__(self) -> None:
        """__post_init__ — enforce namespaced id and non-empty description."""
        if not isinstance(self.id, str) or not _CAPABILITY_ID_PATTERN.match(self.id):
            raise ValueError(
                f"capability id must be a namespaced dotted path "
                f"(^[a-z0-9]+(\\.[a-z0-9-]+)+$), got {self.id!r}"
            )
        if not isinstance(self.description, str) or not self.description:
            raise ValueError("capability description must be a non-empty string")

    def as_dict(self) -> dict[str, Any]:
        """as_dict — canonical serialization."""
        return {"id": self.id, "description": self.description}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Capability:
        """from_dict — parse and validate from a mapping."""
        return cls(id=data["id"], description=data["description"])


@dataclass(frozen=True)
class SpokeDefinition:
    """SpokeDefinition — immutable contract for one composable spoke.

    ``deterministic`` must be True and ``requires_network`` must be False:
    the Hub default package is offline and AI-free by contract, so a
    definition attesting otherwise is rejected at construction.
    """

    spoke_id: str
    version: str
    capabilities: tuple[Capability, ...]
    config_keys: tuple[str, ...] = ()
    permissions: tuple[Permission, ...] = ()
    deterministic: bool = True
    requires_network: bool = False
    schema_version: int = SPOKE_DEFINITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        """__post_init__ — validate identity, capabilities, and attestations."""
        if self.schema_version != SPOKE_DEFINITION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {SPOKE_DEFINITION_SCHEMA_VERSION}, "
                f"got {self.schema_version!r}"
            )
        if not isinstance(self.spoke_id, str) or not _SPOKE_ID_PATTERN.match(self.spoke_id):
            raise ValueError(f"spoke_id must match ^spoke\\.[a-z0-9-]+$, got {self.spoke_id!r}")
        if not isinstance(self.version, str) or not _SEMVER_PATTERN.match(self.version):
            raise ValueError(f"version must be semver (N.N.N), got {self.version!r}")
        if not self.capabilities:
            raise ValueError("spoke must declare at least one capability")
        capability_ids = [cap.id for cap in self.capabilities]
        if len(set(capability_ids)) != len(capability_ids):
            raise ValueError(
                f"duplicate capability id(s) in {self.spoke_id}: "
                f"{sorted({c for c in capability_ids if capability_ids.count(c) > 1})}"
            )
        for key in self.config_keys:
            if not isinstance(key, str) or not _CONFIG_KEY_PATTERN.match(key):
                raise ValueError(f"malformed config key {key!r}")
        for permission in self.permissions:
            if not isinstance(permission, Permission):
                raise ValueError(f"unknown permission {permission!r}")
        if self.deterministic is not True:
            raise ValueError("spoke definition must attest deterministic=True")
        if self.requires_network is not False:
            raise ValueError("spoke definition must attest requires_network=False")

    def as_dict(self) -> dict[str, Any]:
        """as_dict — canonical serialization matching spoke-definition schema."""
        return {
            "schema_version": self.schema_version,
            "spoke_id": self.spoke_id,
            "version": self.version,
            "capabilities": [cap.as_dict() for cap in self.capabilities],
            "config_keys": list(self.config_keys),
            "permissions": [permission.value for permission in self.permissions],
            "deterministic": self.deterministic,
            "requires_network": self.requires_network,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpokeDefinition:
        """from_dict — parse and validate from a mapping."""
        return cls(
            spoke_id=data["spoke_id"],
            version=data["version"],
            capabilities=tuple(Capability.from_dict(cap) for cap in data["capabilities"]),
            config_keys=tuple(data.get("config_keys", [])),
            permissions=tuple(Permission(p) for p in data.get("permissions", [])),
            deterministic=bool(data.get("deterministic", True)),
            requires_network=bool(data.get("requires_network", False)),
            schema_version=int(data.get("schema_version", SPOKE_DEFINITION_SCHEMA_VERSION)),
        )

    def definition_hash(self) -> str:
        """definition_hash — stable SHA-256 over the canonical serialization.

        Deterministic across processes and platforms; never derived from
        object identity, ``repr``, or memory addresses.
        """
        canonical = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderDescriptor:
    """ProviderDescriptor — explicit, stable provider identity.

    ``content_hash`` is an explicit build-time SHA-256 of the provider's
    shipped payload (source/resource bytes), supplied by the registrant and
    validated for shape. The registry never computes identity from Python
    objects, module reprs, or memory addresses.
    """

    provider_id: str
    version: str
    content_hash: str

    _PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
    _HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")

    def __post_init__(self) -> None:
        """__post_init__ — validate explicit identity fields."""
        if not isinstance(self.provider_id, str) or not self._PROVIDER_ID_PATTERN.match(
            self.provider_id
        ):
            raise ValueError(f"malformed provider_id {self.provider_id!r}")
        if not isinstance(self.version, str) or not _SEMVER_PATTERN.match(self.version):
            raise ValueError(f"provider version must be semver, got {self.version!r}")
        if not isinstance(self.content_hash, str) or not self._HASH_PATTERN.match(
            self.content_hash
        ):
            raise ValueError(
                f"provider content_hash must be 64 lowercase hex chars, got {self.content_hash!r}"
            )

    def as_dict(self) -> dict[str, Any]:
        """as_dict — canonical serialization."""
        return {
            "provider_id": self.provider_id,
            "version": self.version,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderDescriptor:
        """from_dict — parse and validate from a mapping."""
        return cls(
            provider_id=data["provider_id"],
            version=data["version"],
            content_hash=data["content_hash"],
        )
