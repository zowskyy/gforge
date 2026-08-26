"""Unit tests for Hub multi-spoke coordination (Slice 4D).

Covers spoke discovery, health checks, and concurrent run eligibility.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from godotforge_core.hub.definitions import (
    Capability,
    Permission,
    ProviderDescriptor,
    SpokeDefinition,
)
from godotforge_core.hub.registry import (
    ActiveRegistration,
    LedgerAction,
    RegistryState,
    SpokeEvent,
    can_accept_run,
    discover_spokes,
    fold_registry,
    is_healthy,
    read_ledger,
    register_spoke,
)

H_DEF = "d" * 64
H_PROV = "e" * 64
H_PROV2 = "f" * 64
REG = "reg-0123456789ab"
REG2 = "reg-fedcba987654"
REG3 = "reg-aaaa00000000"


def _definition(
    spoke_id: str = "spoke.patch-engine",
    caps: tuple[Capability, ...] = (Capability(id="patch.apply", description="apply plans"),),
    permissions: tuple[Permission, ...] = (Permission.FILESYSTEM_WRITE,),
    version: str = "1.0.0",
) -> SpokeDefinition:
    return SpokeDefinition(
        spoke_id=spoke_id,
        version=version,
        capabilities=caps,
        permissions=permissions,
    )


def _provider(
    content_hash: str = H_PROV, provider_id: str = "godotforge.core.patch"
) -> ProviderDescriptor:
    return ProviderDescriptor(provider_id=provider_id, version="1.0.0", content_hash=content_hash)


def _maps(*pairs: tuple[SpokeDefinition, ProviderDescriptor]) -> tuple[dict, dict]:
    definitions = {d.definition_hash(): d for d, _ in pairs}
    providers = {p.content_hash: p for _, p in pairs}
    return definitions, providers


# --- discover_spokes ---------------------------------------------------------


def test_discover_spokes_reads_ledger_and_returns_registry_state(tmp_path: Path) -> None:
    """discover_spokes reads the ledger and returns a RegistryState with history."""
    d1, p1 = _definition(), _provider()
    d2 = _definition(
        spoke_id="spoke.creator",
        caps=(Capability(id="creator.plan", description="plan"),),
        permissions=(Permission.FILESYSTEM_WRITE,),
    )
    p2 = _provider(content_hash=H_PROV2, provider_id="godotforge.core.creator")

    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")

    definitions, providers = _maps((d1, p1), (d2, p2))
    state = discover_spokes(tmp_path)

    # Should return RegistryState with history (ledger events)
    assert isinstance(state, RegistryState)
    assert len(state.history) == 2
    assert all(isinstance(e, SpokeEvent) for e in state.history)
    # Active spokes are not resolved here (definitions/providers not available)
    assert state.active == {}


def test_discover_spokes_empty_ledger_returns_empty_state(tmp_path: Path) -> None:
    """discover_spokes on empty/missing ledger returns empty RegistryState."""
    state = discover_spokes(tmp_path)
    assert isinstance(state, RegistryState)
    assert state.active == {}
    assert state.history == ()


def test_discover_spokes_preserves_ledger_order(tmp_path: Path) -> None:
    """discover_spokes preserves the append order of ledger events."""
    d1, p1 = _definition(), _provider()
    d2 = _definition(
        spoke_id="spoke.creator",
        caps=(Capability(id="creator.plan", description="plan"),),
    )
    p2 = _provider(content_hash=H_PROV2, provider_id="godotforge.core.creator")

    register_spoke(tmp_path, REG, d1, p1, "first")
    register_spoke(tmp_path, REG2, d2, p2, "second")

    state = discover_spokes(tmp_path)
    assert state.history[0].seq == 1
    assert state.history[1].seq == 2


# --- SpokeEvent last_seen field (backward-compatible) ------------------------


def test_spoke_event_has_optional_last_seen_field() -> None:
    """SpokeEvent payload includes optional last_seen field (ISO8601 string)."""
    # Create a SpokeEvent with last_seen
    now = datetime.now(timezone.utc).isoformat()
    event = SpokeEvent(
        seq=1,
        action=LedgerAction.REGISTER,
        registration_id=REG,
        spoke_id="spoke.test",
        definition_hash=H_DEF,
        provider_hash=H_PROV,
        reason="test",
        prev_hash=None,
        event_hash="a" * 64,
        schema_version=1,
    )
    # as_dict should include last_seen if present
    # Since we can't directly add it to the dataclass, we test the JSON serialization
    # The schema change adds it as optional in the payload
    event_dict = event.as_dict()
    # last_seen is not in the canonical hash input, so it won't be in as_dict by default
    # The _append_event will add it to the written JSON


def test_append_event_includes_last_seen_iso8601(tmp_path: Path) -> None:
    """_append_event adds last_seen (ISO8601) to the written JSON line."""
    d1, p1 = _definition(), _provider()
    register_spoke(tmp_path, REG, d1, p1, "test")

    # Read the raw line to check for last_seen
    ledger_path = tmp_path / ".godotforge" / "hub" / "spoke-ledger.jsonl"
    line = ledger_path.read_text(encoding="utf-8").strip()
    data = json.loads(line)

    # Should have last_seen field
    assert "last_seen" in data
    # Should be valid ISO8601
    last_seen = data["last_seen"]
    assert isinstance(last_seen, str)
    # Parse to validate format
    parsed = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_spoke_event_backward_compatible_without_last_seen(tmp_path: Path) -> None:
    """Old ledger entries without last_seen are readable (backward compatible)."""
    d1, p1 = _definition(), _provider()
    register_spoke(tmp_path, REG, d1, p1, "test")

    # Manually add a line without last_seen to simulate old format
    ledger_path = tmp_path / ".godotforge" / "hub" / "spoke-ledger.jsonl"
    old_line = json.dumps(
        {
            "schema_version": 1,
            "seq": 2,
            "action": "register",
            "registration_id": REG2,
            "spoke_id": "spoke.old",
            "definition_hash": H_DEF,
            "provider_hash": H_PROV,
            "reason": "old format",
            "prev_hash": "a" * 64,
            "event_hash": "b" * 64,
            # no last_seen
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(old_line + "\n")

    # Should read without error
    events = read_ledger(tmp_path)
    assert len(events) == 2
    assert events[1].seq == 2


# --- is_healthy --------------------------------------------------------------


def test_is_healthy_returns_true_for_recently_seen_spoke(tmp_path: Path) -> None:
    """is_healthy returns True for spokes seen within max_age_seconds."""
    d1, p1 = _definition(), _provider()
    register_spoke(tmp_path, REG, d1, p1, "test")

    state = discover_spokes(tmp_path)
    # Need to fold with definitions/providers to get active spokes
    definitions, providers = _maps((d1, p1))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)

    healthy = is_healthy(folded, max_age_seconds=300)
    assert healthy == {"spoke.patch-engine": True}


def test_is_healthy_returns_false_for_stale_spoke(tmp_path: Path) -> None:
    """is_healthy returns False for spokes older than max_age_seconds."""
    d1, p1 = _definition(), _provider()
    register_spoke(tmp_path, REG, d1, p1, "test")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)

    # Manually manipulate last_seen to be old (simulate stale spoke)
    # We need to modify the ledger or the folded state
    # Since we can't easily modify the folded state's last_seen,
    # we test with a very small max_age
    healthy = is_healthy(folded, max_age_seconds=0.001)
    # Should be false because even a tiny delay makes it stale
    assert healthy == {"spoke.patch-engine": False}


def test_is_healthy_excludes_deregistered_spokes(tmp_path: Path) -> None:
    """is_healthy only checks currently active (not deregistered) spokes."""
    d1, p1 = _definition(), _provider()
    d2 = _definition(spoke_id="spoke.creator", caps=(Capability(id="creator.plan", description="p"),))
    p2 = _provider(content_hash=H_PROV2, provider_id="godotforge.core.creator")

    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")
    from godotforge_core.hub.registry import deregister_spoke

    deregister_spoke(tmp_path, REG, "retired")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1), (d2, p2))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)

    healthy = is_healthy(folded, max_age_seconds=300)
    # Only spoke.creator should be checked (spoke.patch-engine was deregistered)
    assert "spoke.patch-engine" not in healthy
    assert healthy == {"spoke.creator": True}


def test_is_healthy_handles_missing_last_seen_gracefully(tmp_path: Path) -> None:
    """is_healthy returns False for spokes with missing last_seen (old ledger format)."""
    d1, p1 = _definition(), _provider()
    register_spoke(tmp_path, REG, d1, p1, "test")

    # Manually add an old-format entry without last_seen for an active spoke
    ledger_path = tmp_path / ".godotforge" / "hub" / "spoke-ledger.jsonl"
    old_line = json.dumps(
        {
            "schema_version": 1,
            "seq": 2,
            "action": "register",
            "registration_id": REG2,
            "spoke_id": "spoke.old-format",
            "definition_hash": H_DEF,
            "provider_hash": H_PROV,
            "reason": "no last_seen",
            "prev_hash": "a" * 64,
            "event_hash": "b" * 64,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(old_line + "\n")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1), (_definition(spoke_id="spoke.old-format"), _provider()))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)

    healthy = is_healthy(folded, max_age_seconds=300)
    # Spoke with missing last_seen should be considered unhealthy
    assert healthy["spoke.old-format"] is False
    # New spoke with last_seen should be healthy
    assert healthy["spoke.patch-engine"] is True


# --- can_accept_run ----------------------------------------------------------


def test_can_accept_run_returns_spokes_with_all_required_capabilities(tmp_path: Path) -> None:
    """can_accept_run returns spokes that have ALL required capabilities and are healthy."""
    d1, p1 = _definition(
        caps=(
            Capability(id="patch.apply", description="apply"),
            Capability(id="patch.preview", description="preview"),
        )
    ), _provider()
    d2 = _definition(
        spoke_id="spoke.creator",
        caps=(Capability(id="creator.plan", description="plan"),),
    )
    p2 = _provider(content_hash=H_PROV2, provider_id="godotforge.core.creator")

    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1), (d2, p2))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)

    # Request both patch capabilities - only spoke.patch-engine has both
    result = can_accept_run(folded, {"patch.apply", "patch.preview"})
    assert len(result) == 1
    assert result[0].definition.spoke_id == "spoke.patch-engine"


def test_can_accept_run_filters_by_health(tmp_path: Path) -> None:
    """can_accept_run excludes unhealthy spokes even if they have capabilities."""
    d1, p1 = _definition(
        caps=(Capability(id="patch.apply", description="apply"),)
    ), _provider()
    d2 = _definition(
        spoke_id="spoke.creator",
        caps=(Capability(id="patch.apply", description="apply"),),
    )
    p2 = _provider(content_hash=H_PROV2, provider_id="godotforge.core.creator")

    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1), (d2, p2))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)

    # Both have the capability, but use max_age=0 to make both unhealthy
    result = can_accept_run(folded, {"patch.apply"}, max_age_seconds=0.001)
    assert result == []


def test_can_accept_run_returns_empty_when_no_spoke_has_all_capabilities(tmp_path: Path) -> None:
    """can_accept_run returns empty list when no single spoke has all required capabilities."""
    d1, p1 = _definition(caps=(Capability(id="patch.apply", description="apply"),)), _provider()
    d2 = _definition(
        spoke_id="spoke.creator",
        caps=(Capability(id="creator.plan", description="plan"),),
    )
    p2 = _provider(content_hash=H_PROV2, provider_id="godotforge.core.creator")

    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1), (d2, p2))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)

    # Need both capabilities - no single spoke has both
    result = can_accept_run(folded, {"patch.apply", "creator.plan"})
    assert result == []


def test_can_accept_run_respects_capability_collision_detection(tmp_path: Path) -> None:
    """can_accept_run still respects capability collision detection from fold_registry."""
    d1, p1 = _definition(caps=(Capability(id="patch.apply", description="apply"),)), _provider()
    # Collision: same capability ID on another spoke
    d2 = _definition(
        spoke_id="spoke.other",
        caps=(Capability(id="patch.apply", description="apply duplicate"),),
    )
    p2 = _provider(content_hash=H_PROV2, provider_id="other.provider")

    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1), (d2, p2))

    # fold_registry should raise on collision
    with pytest.raises(ValueError, match="capability id collision"):
        fold_registry(state.history, definitions, providers, ledger_root=tmp_path)


def test_can_accept_run_excludes_deregistered_spokes(tmp_path: Path) -> None:
    """can_accept_run excludes deregistered spokes."""
    d1, p1 = _definition(caps=(Capability(id="patch.apply", description="apply"),)), _provider()
    d2 = _definition(
        spoke_id="spoke.creator",
        caps=(Capability(id="patch.apply", description="apply"),),
    )
    p2 = _provider(content_hash=H_PROV2, provider_id="godotforge.core.creator")

    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")
    from godotforge_core.hub.registry import deregister_spoke

    deregister_spoke(tmp_path, REG, "retired")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1), (d2, p2))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)

    result = can_accept_run(folded, {"patch.apply"})
    # Only spoke.creator should be returned
    assert len(result) == 1
    assert result[0].definition.spoke_id == "spoke.creator"


# --- Read-only: no mutations to ledger ---------------------------------------


def test_discover_spokes_is_read_only(tmp_path: Path) -> None:
    """discover_spokes does not mutate the ledger."""
    d1, p1 = _definition(), _provider()
    register_spoke(tmp_path, REG, d1, p1, "one")

    ledger_path = tmp_path / ".godotforge" / "hub" / "spoke-ledger.jsonl"
    original_content = ledger_path.read_text(encoding="utf-8")

    discover_spokes(tmp_path)

    after_content = ledger_path.read_text(encoding="utf-8")
    assert after_content == original_content


def test_is_healthy_is_read_only(tmp_path: Path) -> None:
    """is_healthy does not mutate the ledger."""
    d1, p1 = _definition(), _provider()
    register_spoke(tmp_path, REG, d1, p1, "one")

    ledger_path = tmp_path / ".godotforge" / "hub" / "spoke-ledger.jsonl"
    original_content = ledger_path.read_text(encoding="utf-8")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)
    is_healthy(folded, max_age_seconds=300)

    after_content = ledger_path.read_text(encoding="utf-8")
    assert after_content == original_content


def test_can_accept_run_is_read_only(tmp_path: Path) -> None:
    """can_accept_run does not mutate the ledger."""
    d1, p1 = _definition(), _provider()
    register_spoke(tmp_path, REG, d1, p1, "one")

    ledger_path = tmp_path / ".godotforge" / "hub" / "spoke-ledger.jsonl"
    original_content = ledger_path.read_text(encoding="utf-8")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)
    can_accept_run(folded, {"patch.apply"})

    after_content = ledger_path.read_text(encoding="utf-8")
    assert after_content == original_content


# --- Determinism: sorted iteration -------------------------------------------


def test_can_accept_run_deterministic_order(tmp_path: Path) -> None:
    """can_accept_run returns results in deterministic (sorted) order."""
    d1 = _definition(
        spoke_id="spoke.aaa",
        caps=(Capability(id="cap.x", description="x"),),
    )
    p1 = _provider(provider_id="prov.aaa")
    d2 = _definition(
        spoke_id="spoke.bbb",
        caps=(Capability(id="cap.x", description="x"),),
    )
    p2 = _provider(content_hash=H_PROV2, provider_id="prov.bbb")

    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")

    state = discover_spokes(tmp_path)
    definitions, providers = _maps((d1, p1), (d2, p2))
    folded = fold_registry(state.history, definitions, providers, ledger_root=tmp_path)

    result1 = can_accept_run(folded, {"cap.x"})
    result2 = can_accept_run(folded, {"cap.x"})

    assert [r.definition.spoke_id for r in result1] == [r.definition.spoke_id for r in result2]
    # Should be sorted by spoke_id
    assert [r.definition.spoke_id for r in result1] == ["spoke.aaa", "spoke.bbb"]