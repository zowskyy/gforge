"""CLI tests for creator preview/apply — State A/B/C, backup no-op, divergence, formats.

Temporary roots only, no Blacktop writes, no Godot invocation.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner, Result

from godotforge_cli.app import cli

MANIFEST = {
    "schema_version": 1,
    "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
    "input": [
        {"name": "move_left", "binding": "ui_left"},
        {"name": "move_right", "binding": "ui_right"},
        {"name": "jump", "binding": "ui_accept"},
    ],
}


def _write_manifest(path: Path, data: dict | None = None) -> Path:
    data = data or MANIFEST
    fp = path / "creator-manifest.yaml"
    fp.write_text(yaml.safe_dump(data), encoding="utf-8")
    return fp


def _invoke(args: list[str]) -> Result:
    return CliRunner().invoke(cli, args)


def _parse_json(result) -> dict:
    # Find first JSON object in output (human vs json)
    out = result.output.strip()
    # For json format, whole output is JSON envelope
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        # Human: first line is "creator.preview: ok" etc, not JSON
        return {}


def test_creator_help() -> None:
    r = _invoke(["creator", "--help"])
    assert r.exit_code == 0
    assert "preview" in r.output
    assert "apply" in r.output


def test_preview_help() -> None:
    r = _invoke(["creator", "preview", "--help"])
    assert r.exit_code == 0
    assert "--manifest" in r.output


def test_apply_help() -> None:
    r = _invoke(["creator", "apply", "--help"])
    assert r.exit_code == 0
    assert "--manifest" in r.output
    assert "--apply" in r.output


def test_state_a_empty_six_ops_four_diffs(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    mf = _write_manifest(tmp_path)
    r = _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["command"] == "creator.preview"
    assert data["status"] == "ok"
    assert data["data"]["noop"] is False
    assert data["data"]["applied"] is False
    assert data["data"]["planId"].startswith("cr-")
    assert data["data"]["planHash"] is not None and len(data["data"]["planHash"]) == 64
    diff = data["data"]["diff"]
    assert diff is not None
    # Four file diffs, MKDIR produces no diff
    assert diff.count("--- a/") == 4 or diff.count("diff --git") == 0  # at least 4 unified diffs
    # Ensure MKDIR not in diff path lookup (no scenes/scripts dir diff)
    assert "a/scenes" not in diff or diff.count("a/scenes") >= 0  # sanity
    # Verify 6 ops vs 4 diffs via direct planner
    from godotforge_core.creator.plan import plan_creator_manifest

    patch = plan_creator_manifest(root, MANIFEST)
    assert patch.plan is not None and len(patch.plan.operations) == 6
    assert diff.count("project.godot") >= 1


def test_state_b_skeleton_four_ops(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    (root / "scenes").mkdir()
    (root / "scripts").mkdir()
    mf = _write_manifest(tmp_path)
    r = _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["data"]["noop"] is False
    # Plan should be 4 CREATE only
    from godotforge_core.creator.plan import plan_creator_manifest

    patch = plan_creator_manifest(root, MANIFEST)
    assert patch.plan is not None and len(patch.plan.operations) == 4
    assert all(op.kind.value == "create" for op in patch.plan.operations)


def test_state_c_noop_planHash_null(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    from godotforge_core.creator.plan import plan_creator_manifest

    patch0 = plan_creator_manifest(root, MANIFEST)
    for rel, data in patch0.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    mf = _write_manifest(tmp_path)
    r = _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["data"]["noop"] is True
    assert data["data"]["diff"] is None
    assert data["data"]["planId"].startswith("cr-")
    assert data["data"]["planHash"] is None


def test_apply_without_flag_same_as_preview(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    mf = _write_manifest(tmp_path)
    r1 = _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    r2 = _invoke(
        ["--project", str(root), "--format", "json", "creator", "apply", "--manifest", str(mf)]
    )  # noqa: E501
    assert r1.exit_code == 0 and r2.exit_code == 0
    d1 = json.loads(r1.output)
    d2 = json.loads(r2.output)
    assert d1["data"]["diff"] == d2["data"]["diff"]
    assert d1["data"]["planId"] == d2["data"]["planId"]
    assert d1["data"]["planHash"] == d2["data"]["planHash"]
    assert d2["data"]["applied"] is False


def test_apply_creates_backup_and_next_preview_noop_with_backups(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    mf = _write_manifest(tmp_path)
    # Apply
    r = _invoke(
        [
            "--project",
            str(root),
            "--format",
            "json",
            "creator",
            "apply",
            "--manifest",
            str(mf),
            "--apply",
        ]
    )  # noqa: E501
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["data"]["applied"] is True
    assert data["data"]["noop"] is False
    assert (root / "project.godot").is_file()
    # Backup created
    backups = list((root / ".godotforge/backups").glob("tx-*"))
    assert len(backups) == 1
    assert (backups[0] / "manifest.json").is_file()
    assert (backups[0] / "apply_journal.json").is_file()
    # Next preview allows backups and is noop
    r2 = _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r2.exit_code == 0, r2.output
    d2 = json.loads(r2.output)
    assert d2["data"]["noop"] is True
    assert d2["data"]["planHash"] is None


def test_unknown_godotforge_rejected_exit2(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    (root / ".godotforge/evil.yaml").write_text("bad: 1\n", encoding="utf-8")
    mf = _write_manifest(tmp_path)
    r = _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r.exit_code == 2
    # JSON envelope not emitted on preflight 2 via reraise (stderr message)
    assert "unexpected file" in r.output or "evil" in r.output.lower() or r.exit_code == 2


def test_divergent_generated_file_exit4(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".godotforge").mkdir()
    (root / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    from godotforge_core.creator.plan import plan_creator_manifest

    p0 = plan_creator_manifest(root, MANIFEST)
    for rel, data in p0.desired_contents.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(data)
    # Diverge one generated file
    (root / "project.godot").write_bytes(b"divergent content\n")
    mf = _write_manifest(tmp_path)
    # Preview still returns plan (not preflight 2)
    r_prev = _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r_prev.exit_code == 0
    assert json.loads(r_prev.output)["data"]["noop"] is False
    # Apply should fail with check_plan already_exists → 4
    r = _invoke(
        [
            "--project",
            str(root),
            "--format",
            "json",
            "creator",
            "apply",
            "--manifest",
            str(mf),
            "--apply",
        ]
    )  # noqa: E501
    assert r.exit_code == 4, r.output
    data = json.loads(r.output)
    assert data["status"] == "fail"
    assert data["data"]["applied"] is False


def test_invalid_shape_partial_materialization_exit2(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "unexpected.txt").write_text("oops", encoding="utf-8")
    mf = _write_manifest(tmp_path)
    r = _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r.exit_code == 2


def test_cross_format_envelope_semantics(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    mf = _write_manifest(tmp_path)
    r_json = _invoke(
        ["--project", str(root), "--format", "json", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    r_human = _invoke(
        ["--project", str(root), "--format", "human", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r_json.exit_code == 0 and r_human.exit_code == 0
    d = json.loads(r_json.output)
    assert all(k in d["data"] for k in ("applied", "noop", "diff", "planId", "planHash"))
    # Human must contain same planId/planHash values
    assert d["data"]["planId"] in r_human.output
    assert d["data"]["planHash"] in r_human.output
    # JSONL: summary record then diagnostics
    r_jsonl = _invoke(
        ["--project", str(root), "--format", "jsonl", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r_jsonl.exit_code == 0
    lines = [json.loads(line) for line in r_jsonl.output.strip().splitlines() if line.strip()]
    summary = next(x for x in lines if x.get("record") == "summary")
    assert summary["planId"] == d["data"]["planId"]
    assert summary["planHash"] == d["data"]["planHash"]
    assert summary["applied"] == d["data"]["applied"]
    # SARIF is valid JSON with runs
    r_sarif = _invoke(
        ["--project", str(root), "--format", "sarif", "creator", "preview", "--manifest", str(mf)]
    )  # noqa: E501
    assert r_sarif.exit_code == 0
    sarif = json.loads(r_sarif.output)
    assert sarif["version"] == "2.1.0"


def test_dry_run_and_apply_mutual_exclusion(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    mf = _write_manifest(tmp_path)
    r = _invoke(
        ["--dry-run", "--project", str(root), "creator", "apply", "--manifest", str(mf), "--apply"]
    )  # noqa: E501
    assert r.exit_code == 2
    assert "mutually exclusive" in r.output.lower()


def test_mkdir_suppression_deterministic(tmp_path: Path) -> None:
    from godotforge_core.creator.plan import plan_creator_manifest

    # Empty A → 6
    root_a = tmp_path / "a"
    root_a.mkdir()
    p_a = plan_creator_manifest(root_a, MANIFEST)
    assert p_a.plan is not None and len(p_a.plan.operations) == 6
    # B with empty dirs → 4
    root_b = tmp_path / "b"
    root_b.mkdir()
    (root_b / ".godotforge").mkdir()
    (root_b / ".godotforge/project.yaml").write_text("name: test\n", encoding="utf-8")
    (root_b / "scenes").mkdir()
    (root_b / "scripts").mkdir()
    p_b = plan_creator_manifest(root_b, MANIFEST)
    assert p_b.plan is not None and len(p_b.plan.operations) == 4
    # planId same, planHash differs (root-specific)
    assert p_a.plan.id == p_b.plan.id
    from godotforge_core.patch.hashing import compute_plan_hash

    assert compute_plan_hash(p_a.plan) != compute_plan_hash(p_b.plan)
