"""Unit tests for Hub spoke definitions and the append-only registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from godotforge_core.hub.definitions import (
    Capability,
    Permission,
    ProviderDescriptor,
    SpokeDefinition,
)
from godotforge_core.hub.registry import (
    LedgerAction,
    compute_spoke_event_hash,
    deregister_spoke,
    fold_registry,
    invoke,
    ledger_path,
    read_ledger,
    register_spoke,
    resolve_capability,
    verify_ledger,
)
from godotforge_core.hub.run_record import Authorization

H_DEF = "d" * 64
H_PROV = "e" * 64
H_PROV2 = "f" * 64
H_PLAN = "1" * 64
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


# --- definitions -----------------------------------------------------------


def test_definition_roundtrip_and_hash_stability() -> None:
    definition = _definition()
    again = SpokeDefinition.from_dict(definition.as_dict())
    assert again == definition
    assert definition.definition_hash() == again.definition_hash()
    assert definition.definition_hash() == _definition().definition_hash()


def test_definition_schema_valid() -> None:
    from importlib.resources import files

    import jsonschema

    schema = json.loads(
        (files("godotforge_core") / "schemas" / "spoke-definition.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(_definition().as_dict(), schema)


def test_definition_immutable() -> None:
    definition = _definition()
    with pytest.raises(AttributeError):
        definition.version = "9.9.9"  # type: ignore[misc]


def test_definition_rejects_malformed() -> None:
    with pytest.raises(ValueError, match="spoke_id"):
        _definition(spoke_id="patch-engine")
    with pytest.raises(ValueError, match="semver"):
        _definition(version="1.0")
    with pytest.raises(ValueError, match="at least one capability"):
        _definition(caps=())
    with pytest.raises(ValueError, match="deterministic"):
        SpokeDefinition(
            spoke_id="spoke.x",
            version="1.0.0",
            capabilities=(Capability(id="x.y", description="y"),),
            deterministic=False,
        )
    with pytest.raises(ValueError, match="requires_network"):
        SpokeDefinition(
            spoke_id="spoke.x",
            version="1.0.0",
            capabilities=(Capability(id="x.y", description="y"),),
            requires_network=True,
        )


def test_capability_id_rules() -> None:
    with pytest.raises(ValueError, match="namespaced"):
        Capability(id="apply", description="no namespace")
    with pytest.raises(ValueError, match="namespaced"):
        Capability(id="Patch.Apply", description="uppercase")
    with pytest.raises(ValueError, match="non-empty"):
        Capability(id="a.b", description="")
    with pytest.raises(ValueError, match="duplicate capability"):
        _definition(
            caps=(
                Capability(id="a.b", description="1"),
                Capability(id="a.b", description="2"),
            )
        )


def test_provider_identity_explicit_and_stable() -> None:
    provider = _provider()
    assert provider.as_dict() == ProviderDescriptor.from_dict(provider.as_dict()).as_dict()
    with pytest.raises(ValueError, match="content_hash"):
        _provider(content_hash="not-a-hash")
    with pytest.raises(ValueError, match="provider_id"):
        _provider(provider_id="Bad Id")
    with pytest.raises(ValueError, match="semver"):
        ProviderDescriptor(provider_id="p", version="v1", content_hash=H_PROV)


# --- registry ledger --------------------------------------------------------


def test_register_and_fold(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")
    definitions, providers = _maps((definition, provider))
    state = fold_registry(read_ledger(tmp_path), definitions, providers)
    assert set(state.active) == {"spoke.patch-engine"}
    assert state.active["spoke.patch-engine"].registration_id == REG
    verify_ledger(tmp_path)


def test_deregister_appends_tombstone_preserving_history(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "initial")
    before = ledger_path(tmp_path).read_bytes()
    deregister_spoke(tmp_path, REG, "retired")
    after = ledger_path(tmp_path).read_bytes()
    assert after.startswith(before)  # prior entry untouched
    events = read_ledger(tmp_path)
    assert [e.action for e in events] == [LedgerAction.REGISTER, LedgerAction.DEREGISTER]
    definitions, providers = _maps((definition, provider))
    state = fold_registry(events, definitions, providers)
    assert state.active == {}
    assert len(state.history) == 2  # evidence preserved


def test_replay_deterministic(tmp_path: Path) -> None:
    d1, p1 = _definition(), _provider()
    d2 = _definition(
        spoke_id="spoke.creator",
        caps=(Capability(id="creator.plan", description="plan"),),
        permissions=(Permission.FILESYSTEM_WRITE,),
    )
    p2 = _provider(content_hash=H_PROV2, provider_id="godotforge.core.creator")
    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")
    deregister_spoke(tmp_path, REG, "retire")
    register_spoke(tmp_path, REG3, d1, p1, "re-register")
    definitions, providers = _maps((d1, p1), (d2, p2))
    events = read_ledger(tmp_path)
    first = fold_registry(events, definitions, providers)
    second = fold_registry(list(events), dict(definitions), dict(providers))
    assert first.state_hash() == second.state_hash()
    assert json.dumps(first.as_dict(), sort_keys=True) == json.dumps(
        second.as_dict(), sort_keys=True
    )
    assert set(first.active) == {"spoke.patch-engine", "spoke.creator"}
    verify_ledger(tmp_path)


def test_duplicate_active_registration_rejected(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "one")
    with pytest.raises(ValueError, match="already has an active registration"):
        register_spoke(tmp_path, REG2, definition, provider, "dup")
    with pytest.raises(ValueError, match="duplicate registration_id"):
        register_spoke(tmp_path, REG, definition, provider, "dup id")


def test_capability_collision_across_spokes_rejected(tmp_path: Path) -> None:
    d1, p1 = _definition(), _provider()
    d2 = _definition(spoke_id="spoke.other")
    p2 = _provider(content_hash=H_PROV2, provider_id="other.provider")
    register_spoke(tmp_path, REG, d1, p1, "one")
    register_spoke(tmp_path, REG2, d2, p2, "two")
    definitions, providers = _maps((d1, p1), (d2, p2))
    with pytest.raises(ValueError, match="capability id collision"):
        fold_registry(read_ledger(tmp_path), definitions, providers)


def test_fold_rejects_unknown_definition_and_provider(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "one")
    events = read_ledger(tmp_path)
    with pytest.raises(ValueError, match="unknown definition hash"):
        fold_registry(events, {}, {provider.content_hash: provider})
    with pytest.raises(ValueError, match="unknown provider hash"):
        fold_registry(events, {definition.definition_hash(): definition}, {})


def test_deregister_unknown_or_inactive_rejected(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    with pytest.raises(ValueError, match="unknown or inactive"):
        deregister_spoke(tmp_path, REG, "nope")
    register_spoke(tmp_path, REG, definition, provider, "one")
    deregister_spoke(tmp_path, REG, "retire")
    with pytest.raises(ValueError, match="unknown or inactive"):
        deregister_spoke(tmp_path, REG, "again")


def test_malformed_registration_inputs_rejected(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    with pytest.raises(ValueError, match="registration_id"):
        register_spoke(tmp_path, "bad id", definition, provider, "x")
    with pytest.raises(ValueError, match="non-empty"):
        register_spoke(tmp_path, REG, definition, provider, "")


def test_ledger_tamper_detected(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "one")
    creator_def = _definition(
        spoke_id="spoke.creator",
        caps=(Capability(id="creator.plan", description="p"),),
    )
    creator_prov = _provider(content_hash=H_PROV2, provider_id="godotforge.core.creator")
    register_spoke(tmp_path, REG2, creator_def, creator_prov, "two")
    path = ledger_path(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()

    # Payload edit
    data = json.loads(lines[0])
    data["reason"] = "forged"
    tampered = lines.copy()
    tampered[0] = json.dumps(data, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(tampered) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="event_hash mismatch"):
        verify_ledger(tmp_path)

    # Middle deletion → seq gap / chain break
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    verify_ledger(tmp_path)
    del lines[0]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        verify_ledger(tmp_path)


def test_event_hash_recompute() -> None:
    digest = compute_spoke_event_hash(
        1, LedgerAction.REGISTER, REG, "spoke.patch-engine", H_DEF, H_PROV, "r", None
    )
    assert digest == compute_spoke_event_hash(
        1, LedgerAction.REGISTER, REG, "spoke.patch-engine", H_DEF, H_PROV, "r", None
    )
    assert digest != compute_spoke_event_hash(
        2, LedgerAction.REGISTER, REG, "spoke.patch-engine", H_DEF, H_PROV, "r", None
    )


# --- invocation seam --------------------------------------------------------


def test_invoke_unknown_capability_rejected(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "one")
    definitions, providers = _maps((definition, provider))
    state = fold_registry(read_ledger(tmp_path), definitions, providers)
    with pytest.raises(ValueError, match="unknown or inactive capability"):
        resolve_capability(state, "patch.nonexistent")
    with pytest.raises(ValueError, match="unknown or inactive capability"):
        invoke(state, {}, "patch.nonexistent", {})


def test_invoke_after_deregister_rejected(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "one")
    deregister_spoke(tmp_path, REG, "retire")
    definitions, providers = _maps((definition, provider))
    state = fold_registry(read_ledger(tmp_path), definitions, providers)
    with pytest.raises(ValueError, match="unknown or inactive capability"):
        invoke(state, {provider.content_hash: lambda req: req}, "patch.apply", {})


def test_invoke_requires_authorization_for_gated_permissions(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "one")
    definitions, providers = _maps((definition, provider))
    state = fold_registry(read_ledger(tmp_path), definitions, providers)
    handler = lambda req: {"echo": req}  # noqa: E731
    with pytest.raises(ValueError, match="requires recorded authorization"):
        invoke(state, {provider.content_hash: handler}, "patch.apply", {"x": 1})
    auth = Authorization(mode="explicit_cli", plan_hash=H_PLAN, scope="apply")
    assert invoke(
        state, {provider.content_hash: handler}, "patch.apply", {"x": 1}, authorization=auth
    ) == {"echo": {"x": 1}}


def test_invoke_ungated_capability_needs_no_authorization(tmp_path: Path) -> None:
    definition = _definition(
        spoke_id="spoke.project-intel",
        caps=(Capability(id="scan.inventory", description="read-only inventory"),),
        permissions=(Permission.FILESYSTEM_READ,),
    )
    provider = _provider()
    register_spoke(tmp_path, REG, definition, provider, "one")
    definitions, providers = _maps((definition, provider))
    state = fold_registry(read_ledger(tmp_path), definitions, providers)
    assert invoke(state, {provider.content_hash: lambda req: 42}, "scan.inventory", {}) == 42


def test_invoke_invalid_provider_handler_rejected(tmp_path: Path) -> None:
    definition, provider = _definition(), _provider()
    register_spoke(tmp_path, REG, definition, provider, "one")
    definitions, providers = _maps((definition, provider))
    state = fold_registry(read_ledger(tmp_path), definitions, providers)
    auth = Authorization(mode="explicit_cli", plan_hash=H_PLAN, scope="apply")
    with pytest.raises(ValueError, match="invalid provider"):
        invoke(state, {}, "patch.apply", {}, authorization=auth)


# --- Hub control-plane path safety (remediation for the confirmed
# symlink-redirect defect: the ledger writer must reject a symlinked target
# before opening it, via godotforge_core.hub_control_plane) ---


def test_register_spoke_rejects_symlinked_ledger_before_writing_any_bytes_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-planted symlink at the spoke-ledger path must not be followed.

    Simulates the symlink via ``os.lstat`` (real symlinks require elevated
    privilege on this host) and proves the *target* file's bytes are
    untouched: the append must fail before opening the destination for
    write.
    """
    import os
    import stat

    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    victim = tmp_path / "project.godot"
    original_bytes = b'config_version=5\n[application]\nconfig/name="X"\n'
    victim.write_bytes(original_bytes)
    link = hub_dir / "spoke-ledger.jsonl"
    link.write_bytes(b"")
    real_lstat = os.lstat

    def _fake_lstat(path, *, dir_fd=None):  # noqa: ANN001
        if Path(path) == link:
            return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    monkeypatch.setattr(os, "lstat", _fake_lstat)
    definition, provider = _definition(), _provider()
    with pytest.raises(ValueError, match="symlink"):
        register_spoke(tmp_path, REG, definition, provider, "one")
    assert victim.read_bytes() == original_bytes


def test_register_spoke_rejects_symlinked_ledger_real(tmp_path: Path) -> None:
    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    victim = tmp_path / "project.godot"
    original_bytes = b'config_version=5\n[application]\nconfig/name="X"\n'
    victim.write_bytes(original_bytes)
    link = hub_dir / "spoke-ledger.jsonl"
    try:
        link.symlink_to(victim)
    except OSError:
        pytest.skip("host cannot create symlinks (elevated privilege / Developer Mode required)")
    definition, provider = _definition(), _provider()
    with pytest.raises(ValueError, match="symlink"):
        register_spoke(tmp_path, REG, definition, provider, "one")
    assert victim.read_bytes() == original_bytes


def test_read_ledger_rejects_symlinked_ledger_simulated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import stat

    hub_dir = tmp_path / ".godotforge" / "hub"
    hub_dir.mkdir(parents=True)
    link = hub_dir / "spoke-ledger.jsonl"
    link.write_text('{"seq":1}\n', encoding="utf-8")
    real_lstat = os.lstat

    def _fake_lstat(path, *, dir_fd=None):  # noqa: ANN001
        if Path(path) == link:
            return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        return real_lstat(path)

    monkeypatch.setattr(os, "lstat", _fake_lstat)
    with pytest.raises(ValueError, match="symlink"):
        read_ledger(tmp_path)
