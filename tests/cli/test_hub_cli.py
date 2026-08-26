"""CLI tests for ``godotforge hub`` — read-only preview (Slice 4A) and the
authorization-bound apply/resume lifecycle (Slice 4B). Verification is faked
at the orchestrator seam so tests are deterministic on hosts without Godot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner, Result
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.creator.verify import VerifyResult
from godotforge_core.detection.engine import EngineProbeResult
from godotforge_core.engine.validate import ValidationResult
from godotforge_core.hub import orchestrator
from godotforge_core.hub.goal import compile_goal
from godotforge_core.hub.run_record import run_store_path

from godotforge_cli.app import cli

GOAL = {
    "schema_version": 1,
    "game": {"name": "HubPreview", "template": "2d-platformer-minimal"},
}


def _write_goal(path: Path, data: dict | None = None) -> Path:
    fp = path / "goal.yaml"
    fp.write_text(yaml.safe_dump(data or GOAL), encoding="utf-8")
    return fp


def _invoke(args: list[str]) -> Result:
    return CliRunner().invoke(cli, args)


def test_hub_appears_in_help() -> None:
    """The hub command group is registered."""
    r = _invoke(["--help"])
    assert r.exit_code == 0
    assert "hub" in r.output


def test_hub_run_preview_writes_nothing(tmp_path: Path) -> None:
    """Preview emits the canonical envelope and writes nothing at all."""
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    before = {p.relative_to(root) for p in root.rglob("*")}
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 0
    envelope = json.loads(r.output)
    assert envelope["command"] == "hub.run"
    assert envelope["status"] == "ok"
    data = envelope["data"]
    assert data["applied"] is False
    assert data["noop"] is False
    assert data["planId"].startswith("cr-")
    assert data["planHash"]
    assert data["goalHash"]
    assert data["manifestHash"]
    assert data["diff"]
    # Read-only guarantee: no run records, no .godotforge, no project files.
    assert not (root / ".godotforge").exists()
    assert {p.relative_to(root) for p in root.rglob("*")} == before


def test_hub_run_preview_noop(tmp_path: Path) -> None:
    """A project already matching the goal plans as a truthful no-op."""
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    compilation = compile_goal(GOAL)
    assert compilation.manifest_dict is not None
    patch = plan_creator_manifest(root, compilation.manifest_dict)
    for rel, content in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(content)
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 0
    data = json.loads(r.output)["data"]
    assert data["noop"] is True
    assert data["planHash"] is None
    assert data["diff"] is None
    assert data["planId"].startswith("cr-")


def test_hub_run_clarification_exit_2(tmp_path: Path) -> None:
    """Incomplete goals produce structured clarification diagnostics, exit 2."""
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path, {"schema_version": 1, "game": {"name": "OnlyName"}})
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 2
    envelope = json.loads(r.output)
    assert envelope["status"] == "fail"
    assert any("game.template" in d["message"] for d in envelope["diagnostics"])


def test_hub_run_invalid_goal_exit_2(tmp_path: Path) -> None:
    """Unknown goal keys are rejected with exit 2."""
    root = tmp_path / "proj"
    root.mkdir()
    bad = dict(GOAL)
    bad["bogus"] = True
    goal = _write_goal(tmp_path, bad)
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 2


def test_hub_run_preflight_stray_content_exit_2(tmp_path: Path) -> None:
    """Unmanaged/stray content in the root is a configuration failure."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "stray.txt").write_text("unmanaged", encoding="utf-8")
    goal = _write_goal(tmp_path)
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 2


def test_hub_run_symlink_root_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A symlinked --project root is rejected before resolution (F-002).

    Simulated via monkeypatch so the regression runs on hosts without
    symlink privileges.
    """
    real = tmp_path / "real"
    real.mkdir()
    (real / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    link = tmp_path / "link"
    link.mkdir()  # must exist for click.Path(exists=True); simulated as symlink below
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == link)
    goal = _write_goal(tmp_path)
    r = _invoke(["--project", str(link), "--format", "json", "hub", "run", str(goal)])
    assert r.exit_code == 2
    assert "symlink project root rejected" in r.output


def test_hub_run_preview_human_format(tmp_path: Path) -> None:
    """Human format renders the preview envelope."""
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    r = _invoke(["--project", str(root), "hub", "run", str(goal)])
    assert r.exit_code == 0
    assert "hub.run: ok" in r.output


# --- Slice 4B: authorization-bound apply / resume lifecycle ---

H_E = "e" * 64


def _fake_verify(with_engine: bool) -> Any:
    """_fake_verify — build a deterministic verify_creator_project double."""

    def _verify(
        root: Path,
        manifest_dict: dict[str, Any],
        *,
        engine_path: Any = None,
        timeout: float = 60.0,
        mode: str = "full",
    ) -> VerifyResult:
        engine = (
            EngineProbeResult(
                executable="/fake/godot",
                version="4.3.0",
                flavor="stable",
                raw_version="4.3.0.stable",
                sha256=H_E,
                probe_duration_ms=1.0,
            )
            if with_engine
            else None
        )
        validation = ValidationResult(
            project_root=str(root),
            engine=engine,
            mode=mode,
            stages=(),
            status="ok" if with_engine else "fail",
            wall_duration_ms=1.0,
            graph={},
        )
        return VerifyResult(
            manifest=None,
            plan_id="cr-fake",
            plan_hash=None,
            validation=validation,
            source_before_hash="a" * 64,
            source_after_hash="a" * 64,
            temp_removed=True,
            source_unchanged=True,
        )

    return _verify


def test_hub_run_apply_without_engine_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--apply mutates via the patch engine, then waits for validation (exit 3)."""
    monkeypatch.setattr(orchestrator, "verify_creator_project", _fake_verify(with_engine=False))
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal), "--apply"])
    assert r.exit_code == 3
    envelope = json.loads(r.output)
    assert envelope["status"] == "fail"
    data = envelope["data"]
    assert data["runId"].startswith("run-")
    assert data["state"] == "needs_validation"
    assert data["planHash"]
    assert (root / "project.godot").is_file()
    assert run_store_path(root).is_file()


def test_hub_run_apply_noop_exit_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--apply on a matching project is a truthful no-op with a proof hash."""
    monkeypatch.setattr(orchestrator, "verify_creator_project", _fake_verify(with_engine=False))
    root = tmp_path / "proj"
    root.mkdir()
    compilation = compile_goal(GOAL)
    assert compilation.manifest_dict is not None
    patch = plan_creator_manifest(root, compilation.manifest_dict)
    for rel, content in patch.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(content)
    goal = _write_goal(tmp_path)
    r = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal), "--apply"])
    assert r.exit_code == 0
    data = json.loads(r.output)["data"]
    assert data["noop"] is True
    assert data["outcome"] == "noop"
    assert data["proofHash"]
    assert data["planHash"] is None
    assert not (root / ".godotforge" / "backups").exists()


def test_hub_run_open_run_blocks_mutation_but_not_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An open run blocks a new --apply (exit 2); preview stays read-only."""
    monkeypatch.setattr(orchestrator, "verify_creator_project", _fake_verify(with_engine=False))
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    first = _invoke(
        ["--project", str(root), "--format", "json", "hub", "run", str(goal), "--apply"]
    )
    assert first.exit_code == 3
    run_id = json.loads(first.output)["data"]["runId"]

    blocked = _invoke(
        ["--project", str(root), "--format", "json", "hub", "run", str(goal), "--apply"]
    )
    assert blocked.exit_code == 2
    envelope = json.loads(blocked.output)
    assert envelope["status"] == "fail"
    assert envelope["data"]["runId"] == run_id
    assert any(d["rule"] == "open-run" for d in envelope["diagnostics"])

    preview = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert preview.exit_code == 0


def test_hub_run_tampered_store_exit_4(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A tampered run store is an integrity failure (exit 4); preview is fine."""
    monkeypatch.setattr(orchestrator, "verify_creator_project", _fake_verify(with_engine=False))
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    first = _invoke(
        ["--project", str(root), "--format", "json", "hub", "run", str(goal), "--apply"]
    )
    assert first.exit_code == 3
    store = run_store_path(root)
    lines = store.read_text(encoding="utf-8").splitlines()
    first_line = json.loads(lines[0])
    first_line["payload"]["goal_hash"] = "b" * 64
    lines[0] = json.dumps(first_line, sort_keys=True)
    store.write_text("\n".join(lines) + "\n", encoding="utf-8")

    blocked = _invoke(
        ["--project", str(root), "--format", "json", "hub", "run", str(goal), "--apply"]
    )
    assert blocked.exit_code == 4
    envelope = json.loads(blocked.output)
    assert any(d["rule"] == "run-record-integrity-failure" for d in envelope["diagnostics"])
    preview = _invoke(["--project", str(root), "--format", "json", "hub", "run", str(goal)])
    assert preview.exit_code == 0


def test_hub_run_dry_run_apply_conflict_exit_2(tmp_path: Path) -> None:
    """--dry-run and --apply are mutually exclusive (exit 2)."""
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    r = _invoke(["--project", str(root), "--dry-run", "hub", "run", str(goal), "--apply"])
    assert r.exit_code == 2
    assert "mutually exclusive" in r.output


def test_hub_resume_unknown_run_exit_2(tmp_path: Path) -> None:
    """Resuming an unknown run id is a configuration failure (exit 2)."""
    root = tmp_path / "proj"
    root.mkdir()
    r = _invoke(["--project", str(root), "--format", "json", "hub", "resume", "run-" + "9" * 12])
    assert r.exit_code == 2
    envelope = json.loads(r.output)
    assert envelope["command"] == "hub.resume"
    assert any(d["rule"] == "unknown-run" for d in envelope["diagnostics"])


def test_hub_resume_finalizes_with_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resume re-runs validation and finalizes with outcome=applied."""
    monkeypatch.setattr(orchestrator, "verify_creator_project", _fake_verify(with_engine=False))
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    first = _invoke(
        ["--project", str(root), "--format", "json", "hub", "run", str(goal), "--apply"]
    )
    assert first.exit_code == 3
    run_id = json.loads(first.output)["data"]["runId"]

    monkeypatch.setattr(orchestrator, "verify_creator_project", _fake_verify(with_engine=True))
    resumed = _invoke(["--project", str(root), "--format", "json", "hub", "resume", run_id])
    assert resumed.exit_code == 0
    data = json.loads(resumed.output)["data"]
    assert data["state"] == "finalized"
    assert data["outcome"] == "applied"
    assert data["applied"] is True
    assert data["proofHash"]
    assert data["validationStatus"] == "ok"


def test_hub_resume_mark_interrupted_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--mark-interrupted closes an open run; a follow-up run unblocks."""
    monkeypatch.setattr(orchestrator, "verify_creator_project", _fake_verify(with_engine=False))
    root = tmp_path / "proj"
    root.mkdir()
    goal = _write_goal(tmp_path)
    first = _invoke(
        ["--project", str(root), "--format", "json", "hub", "run", str(goal), "--apply"]
    )
    assert first.exit_code == 3
    run_id = json.loads(first.output)["data"]["runId"]

    marked = _invoke(
        ["--project", str(root), "--format", "json", "hub", "resume", run_id, "--mark-interrupted"]
    )
    assert marked.exit_code == 0
    data = json.loads(marked.output)["data"]
    assert data["state"] == "interrupted"

    followup = _invoke(
        ["--project", str(root), "--format", "json", "hub", "run", str(goal), "--apply"]
    )
    assert followup.exit_code == 0
    assert json.loads(followup.output)["data"]["noop"] is True
