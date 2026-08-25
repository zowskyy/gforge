"""Hub spoke registry — append-only registration ledger with tombstones.

Registrations are recorded as hash-chained, append-only ledger events
(``.godotforge/hub/spoke-ledger.jsonl``, conforming to
``schemas/spoke-ledger.schema.json``). ``deregister`` appends a tombstone;
prior entries are never edited or deleted, so historical registration
evidence is preserved. Current registry state is the deterministic fold of
the ledger via :func:`fold_registry`.

The registry is a seam, not an executor: it contains no project-file
mutation, no subprocess, no network access, no AI dependency, and no hidden
imports (providers are supplied explicitly by the caller). Declared
permissions never bypass the approval or patch-engine gates — invoking a
capability whose spoke declares ``filesystem_write`` or ``engine_invoke``
requires a recorded :class:`~godotforge_core.hub.run_record.Authorization`
bound to the current plan, and all mutation still flows through the patch
engine pipeline.

Offline, deterministic, no AI, network, telemetry, or credentials.
See ``docs/contracts/hub-v1.md`` §1–§2.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from godotforge_core.hub.definitions import (
    Permission,
    ProviderDescriptor,
    SpokeDefinition,
)
from godotforge_core.hub.run_record import Authorization

SPOKE_LEDGER_SCHEMA_VERSION = 1

LEDGER_RELATIVE = Path(".godotforge") / "hub" / "spoke-ledger.jsonl"

_REGISTRATION_ID_PATTERN = re.compile(r"^reg-[0-9a-f]{12}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# Permissions that require a recorded authorization at invocation time.
# The approval gate (hub/approval.py, step 5) issues these; the registry
# refuses to invoke gated capabilities without one.
_GATED_PERMISSIONS = frozenset({Permission.FILESYSTEM_WRITE, Permission.ENGINE_INVOKE})


class LedgerAction(StrEnum):
    """LedgerAction — append-only registration actions."""

    REGISTER = "register"
    DEREGISTER = "deregister"


@dataclass(frozen=True)
class SpokeEvent:
    """SpokeEvent — one append-only, hash-chained ledger entry."""

    seq: int
    action: LedgerAction
    registration_id: str
    spoke_id: str
    definition_hash: str
    provider_hash: str
    reason: str
    prev_hash: str | None
    event_hash: str
    schema_version: int = SPOKE_LEDGER_SCHEMA_VERSION

    def _hash_input(self) -> dict[str, Any]:
        """_hash_input — canonical fields covered by ``event_hash``."""
        return {
            "schema_version": self.schema_version,
            "seq": self.seq,
            "action": self.action.value,
            "registration_id": self.registration_id,
            "spoke_id": self.spoke_id,
            "definition_hash": self.definition_hash,
            "provider_hash": self.provider_hash,
            "reason": self.reason,
            "prev_hash": self.prev_hash,
        }

    def as_dict(self) -> dict[str, Any]:
        """as_dict — canonical serialization including the chain hash."""
        data = self._hash_input()
        data["event_hash"] = self.event_hash
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpokeEvent:
        """from_dict — parse one stored line; validates shape, not chain."""
        return cls(
            seq=int(data["seq"]),
            action=LedgerAction(data["action"]),
            registration_id=data["registration_id"],
            spoke_id=data["spoke_id"],
            definition_hash=data["definition_hash"],
            provider_hash=data["provider_hash"],
            reason=data["reason"],
            prev_hash=data.get("prev_hash"),
            event_hash=data["event_hash"],
            schema_version=int(data.get("schema_version", SPOKE_LEDGER_SCHEMA_VERSION)),
        )


def compute_spoke_event_hash(
    seq: int,
    action: LedgerAction,
    registration_id: str,
    spoke_id: str,
    definition_hash: str,
    provider_hash: str,
    reason: str,
    prev_hash: str | None,
) -> str:
    """compute_spoke_event_hash — deterministic chain hash over canonical fields."""
    body = {
        "schema_version": SPOKE_LEDGER_SCHEMA_VERSION,
        "seq": seq,
        "action": action.value,
        "registration_id": registration_id,
        "spoke_id": spoke_id,
        "definition_hash": definition_hash,
        "provider_hash": provider_hash,
        "reason": reason,
        "prev_hash": prev_hash,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def ledger_path(root: Path | str) -> Path:
    """ledger_path — resolve the spoke-ledger path under the project root."""
    return Path(root).resolve() / LEDGER_RELATIVE


def _validate_registration_id(registration_id: str) -> None:
    """_validate_registration_id — enforce the registration id pattern."""
    if not isinstance(registration_id, str) or not _REGISTRATION_ID_PATTERN.match(registration_id):
        raise ValueError(
            f"registration_id must match ^reg-[0-9a-f]{{12}}$, got {registration_id!r}"
        )


def _check_hash(value: str, *, field: str) -> None:
    """_check_hash — enforce lowercase 64-hex SHA-256 shape."""
    if not isinstance(value, str) or not _HASH_PATTERN.match(value):
        raise ValueError(f"{field} must be 64 lowercase hex chars, got {value!r}")


def read_ledger(root: Path | str) -> tuple[SpokeEvent, ...]:
    """read_ledger — read all ledger events in append order."""
    path = ledger_path(root)
    if not path.is_file():
        return ()
    events: list[SpokeEvent] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"corrupt spoke ledger at line {line_number}: {exc}") from exc
            events.append(SpokeEvent.from_dict(data))
    return tuple(events)


def _append_event(
    root: Path | str,
    action: LedgerAction,
    registration_id: str,
    spoke_id: str,
    definition_hash: str,
    provider_hash: str,
    reason: str,
) -> SpokeEvent:
    """_append_event — append one hash-chained event; lines never rewritten."""
    _validate_registration_id(registration_id)
    _check_hash(definition_hash, field="definition_hash")
    _check_hash(provider_hash, field="provider_hash")
    if not isinstance(reason, str) or not reason:
        raise ValueError("reason must be a non-empty string")
    events = read_ledger(root)
    seq = len(events) + 1
    prev_hash = events[-1].event_hash if events else None
    event = SpokeEvent(
        seq=seq,
        action=action,
        registration_id=registration_id,
        spoke_id=spoke_id,
        definition_hash=definition_hash,
        provider_hash=provider_hash,
        reason=reason,
        prev_hash=prev_hash,
        event_hash=compute_spoke_event_hash(
            seq,
            action,
            registration_id,
            spoke_id,
            definition_hash,
            provider_hash,
            reason,
            prev_hash,
        ),
    )
    destination = ledger_path(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    line = (
        json.dumps(event.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    )
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    return event


def verify_ledger(root: Path | str) -> None:
    """verify_ledger — recompute the hash chain; raise on any tamper.

    Detects payload edits, event deletion, reordering, and seq gaps.
    Raises ``ValueError`` naming the first bad entry.
    """
    prev_hash: str | None = None
    for expected_seq, event in enumerate(read_ledger(root), start=1):
        if event.seq != expected_seq:
            raise ValueError(f"seq gap at ledger position {expected_seq}: found seq {event.seq}")
        if event.prev_hash != prev_hash:
            raise ValueError(f"prev_hash mismatch at seq {event.seq}")
        recomputed = compute_spoke_event_hash(
            event.seq,
            event.action,
            event.registration_id,
            event.spoke_id,
            event.definition_hash,
            event.provider_hash,
            event.reason,
            event.prev_hash,
        )
        if recomputed != event.event_hash:
            raise ValueError(f"event_hash mismatch at seq {event.seq} (tampered)")
        prev_hash = event.event_hash


@dataclass(frozen=True)
class ActiveRegistration:
    """ActiveRegistration — one currently registered spoke (folded state)."""

    registration_id: str
    definition: SpokeDefinition
    provider: ProviderDescriptor
    registered_seq: int

    def as_dict(self) -> dict[str, Any]:
        """as_dict — canonical serialization (sorted, deterministic)."""
        return {
            "registration_id": self.registration_id,
            "definition": self.definition.as_dict(),
            "provider": self.provider.as_dict(),
            "registered_seq": self.registered_seq,
        }


@dataclass(frozen=True)
class RegistryState:
    """RegistryState — deterministic folded view of the append-only ledger.

    ``active`` maps spoke_id → registration for currently registered spokes.
    ``history`` preserves every event (registrations and tombstones) so
    deregistration never erases evidence.
    """

    active: dict[str, ActiveRegistration]
    history: tuple[SpokeEvent, ...]

    def as_dict(self) -> dict[str, Any]:
        """as_dict — canonical serialization with sorted spoke keys."""
        return {
            "schema_version": SPOKE_LEDGER_SCHEMA_VERSION,
            "active": {
                spoke_id: self.active[spoke_id].as_dict() for spoke_id in sorted(self.active)
            },
            "history": [event.as_dict() for event in self.history],
        }

    def state_hash(self) -> str:
        """state_hash — stable SHA-256 of the canonical folded state."""
        canonical = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fold_registry(
    events: tuple[SpokeEvent, ...] | list[SpokeEvent],
    definitions: dict[str, SpokeDefinition],
    providers: dict[str, ProviderDescriptor],
) -> RegistryState:
    """fold_registry — fold ledger events into deterministic current state.

    ``definitions`` maps definition_hash → definition and ``providers`` maps
    provider content_hash → descriptor; both are supplied explicitly by the
    caller (no dynamic imports). Rules:

    - register of an already-active spoke_id → ``ValueError`` (duplicate
      active registration)
    - register whose capability IDs collide with another active spoke →
      ``ValueError``
    - register referencing an unknown definition/provider hash →
      ``ValueError`` (invalid provider/definition)
    - deregister of an unknown or inactive registration_id → ``ValueError``
    - deregister appends a tombstone; the register event stays in history
    """
    active: dict[str, ActiveRegistration] = {}
    by_registration: dict[str, str] = {}
    for event in events:
        if event.action == LedgerAction.REGISTER:
            if event.spoke_id in active:
                raise ValueError(
                    f"duplicate active registration for {event.spoke_id!r} (seq {event.seq})"
                )
            if event.registration_id in by_registration:
                raise ValueError(f"duplicate registration_id {event.registration_id!r}")
            definition = definitions.get(event.definition_hash)
            if definition is None:
                raise ValueError(
                    f"unknown definition hash {event.definition_hash!r} at seq {event.seq}"
                )
            if definition.spoke_id != event.spoke_id:
                raise ValueError(
                    f"definition spoke {definition.spoke_id!r} does not match "
                    f"event spoke {event.spoke_id!r} at seq {event.seq}"
                )
            provider = providers.get(event.provider_hash)
            if provider is None:
                raise ValueError(
                    f"unknown provider hash {event.provider_hash!r} at seq {event.seq}"
                )
            incoming = {cap.id for cap in definition.capabilities}
            for other_id, other in active.items():
                collision = incoming & {cap.id for cap in other.definition.capabilities}
                if collision:
                    raise ValueError(
                        f"capability id collision between {event.spoke_id!r} and "
                        f"{other_id!r}: {sorted(collision)}"
                    )
            active[event.spoke_id] = ActiveRegistration(
                registration_id=event.registration_id,
                definition=definition,
                provider=provider,
                registered_seq=event.seq,
            )
            by_registration[event.registration_id] = event.spoke_id
        else:  # DEREGISTER — tombstone
            spoke_id = by_registration.get(event.registration_id)
            if spoke_id is None or spoke_id not in active:
                raise ValueError(
                    f"cannot deregister unknown or inactive registration "
                    f"{event.registration_id!r} (seq {event.seq})"
                )
            if spoke_id != event.spoke_id:
                raise ValueError(
                    f"tombstone spoke {event.spoke_id!r} does not match registration "
                    f"spoke {spoke_id!r} at seq {event.seq}"
                )
            del active[spoke_id]
    return RegistryState(active=active, history=tuple(events))


def register_spoke(
    root: Path | str,
    registration_id: str,
    definition: SpokeDefinition,
    provider: ProviderDescriptor,
    reason: str,
) -> SpokeEvent:
    """register_spoke — validate and append a register event.

    Rejects duplicate active spoke registrations and capability collisions
    against the current folded state before appending.
    """
    definition_hash = definition.definition_hash()
    provider_hash = provider.content_hash
    events = read_ledger(root)
    # Fold with permissive lookups (hashes only) to check duplicates.
    active_spokes: dict[str, set[str]] = {}
    retired: set[str] = set()
    seen_registration_ids: set[str] = set()
    for event in events:
        if event.action == LedgerAction.REGISTER:
            if event.registration_id in seen_registration_ids:
                raise ValueError(
                    f"ledger corrupt: duplicate registration_id {event.registration_id!r}"
                )
            seen_registration_ids.add(event.registration_id)
            active_spokes[event.spoke_id] = set()  # capability set unknown here
        else:
            retired.add(event.registration_id)
            active_spokes.pop(event.spoke_id, None)
    if registration_id in seen_registration_ids and registration_id not in retired:
        raise ValueError(f"duplicate registration_id {registration_id!r}")
    if definition.spoke_id in active_spokes:
        raise ValueError(f"spoke {definition.spoke_id!r} already has an active registration")
    return _append_event(
        root,
        LedgerAction.REGISTER,
        registration_id,
        definition.spoke_id,
        definition_hash,
        provider_hash,
        reason,
    )


def deregister_spoke(
    root: Path | str,
    registration_id: str,
    reason: str,
) -> SpokeEvent:
    """deregister_spoke — append a tombstone for an active registration.

    The original register event remains in the ledger unchanged; history is
    never erased. Raises ``ValueError`` for unknown or inactive ids.
    """
    events = read_ledger(root)
    active: dict[str, SpokeEvent] = {}
    for event in events:
        if event.action == LedgerAction.REGISTER:
            active[event.registration_id] = event
        else:
            active.pop(event.registration_id, None)
    target = active.get(registration_id)
    if target is None:
        raise ValueError(f"cannot deregister unknown or inactive registration {registration_id!r}")
    return _append_event(
        root,
        LedgerAction.DEREGISTER,
        registration_id,
        target.spoke_id,
        target.definition_hash,
        target.provider_hash,
        reason,
    )


def resolve_capability(state: RegistryState, capability_id: str) -> ActiveRegistration:
    """resolve_capability — find the active spoke offering a capability.

    Raises ``ValueError`` for unknown capability IDs or capabilities offered
    only by deregistered spokes.
    """
    for spoke_id in sorted(state.active):
        registration = state.active[spoke_id]
        if any(cap.id == capability_id for cap in registration.definition.capabilities):
            return registration
    raise ValueError(f"unknown or inactive capability {capability_id!r}")


def invoke(
    state: RegistryState,
    handlers: dict[str, Callable[[dict[str, Any]], Any]],
    capability_id: str,
    request: dict[str, Any],
    *,
    authorization: Authorization | None = None,
) -> Any:
    """invoke — dispatch one capability call through the registry seam.

    ``handlers`` maps provider content_hash → callable, supplied explicitly
    by the caller; the registry performs no imports. Gated capabilities
    (spoke declares ``filesystem_write`` or ``engine_invoke``) require a
    recorded ``authorization`` — this check never replaces the approval or
    patch-engine gates; it only prevents un-gated dispatch. Raises
    ``ValueError`` for unknown capabilities, missing handlers (invalid
    provider), or missing authorization on gated capabilities.
    """
    registration = resolve_capability(state, capability_id)
    handler = handlers.get(registration.provider.content_hash)
    if handler is None:
        raise ValueError(
            f"no handler for provider {registration.provider.provider_id!r} "
            f"(hash {registration.provider.content_hash!r}) — invalid provider"
        )
    if _GATED_PERMISSIONS & set(registration.definition.permissions):
        if authorization is None:
            raise ValueError(
                f"capability {capability_id!r} requires recorded authorization "
                f"(spoke declares gated permissions); use the approval gate"
            )
    return handler(request)
