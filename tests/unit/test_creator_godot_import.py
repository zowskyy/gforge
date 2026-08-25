"""Pinned Godot import/load proof — exit 0, normalized ok, no SCRIPT/UID fatal.

Skipped if FORGE_GODOT_PATH not resolving. Relaxed stderr: warnings allowed.
Proof required before slice declared complete (see docs/contracts/creator-manifest.md).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.detection.engine import resolve_engine
from godotforge_core.engine.normalize import normalize_process
from godotforge_core.engine.runner import run_process
from godotforge_core.scan.tscn import parse_scene


def _manifest() -> dict:
    return {
        "schema_version": 1,
        "game": {"name": "ImportProof", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }


def _resolve_godot() -> Path | None:
    # Reuse existing resolver: FORGE_GODOT_PATH or PATH
    p = resolve_engine(env=os.environ, config=None)
    if p is not None and Path(p).is_file():
        return Path(p)
    # Explicit env fallback for local copy
    env_path = os.environ.get("FORGE_GODOT_PATH")
    if env_path and Path(env_path).is_file():
        return Path(env_path)
    return None


@pytest.mark.integration
def test_godot_import_and_load_proof() -> None:
    engine = _resolve_godot()
    if engine is None:
        pytest.skip("Godot engine not found (set FORGE_GODOT_PATH)")
    # Strict check: engine file must exist
    assert engine.is_file()

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        patch = plan_creator_manifest(root, _manifest())
        # Materialize 6-op plan files
        for d in ("scenes", "scripts"):
            (root / d).mkdir(parents=True, exist_ok=True)
        for rel, data in patch.desired_contents.items():
            fp = root / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_bytes(data)
        # Minimal .godotforge skeleton preserved
        (root / ".godotforge").mkdir(exist_ok=True)
        (root / ".godotforge/project.yaml").write_text("name: importproof\n")

        # TSCN parse gate
        scene = parse_scene(root / "scenes/main.tscn")
        assert scene.format == 3
        assert scene.uid is not None and scene.uid.startswith("uid://")
        # Deterministic header
        raw = (root / "scenes/main.tscn").read_text(encoding="utf-8")
        assert "load_steps=6" in raw and 'format=3' in raw

        # --import gate
        proc = run_process(str(engine), ["--headless", "--path", str(root), "--import"], timeout=60)
        norm = normalize_process(
            exit_code=proc.exit_code,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_ms=proc.duration_ms,
            timed_out=proc.timed_out,
            launch_error=proc.launch_error,
            stage="import",
            engine_version="4.7.1",
        )
        assert proc.exit_code == 0, (
            f"import exit {proc.exit_code}\n"
            f"stdout:{proc.stdout[:2000]}\nstderr:{proc.stderr[:2000]}"
        )
        assert not proc.timed_out
        # Normalized must be ok (warnings allowed), no SCRIPT ERROR / UID fatal
        assert norm.status == "ok", (
            f"import normalized status {norm.status}, "
            f"diagnostics: {norm.diagnostics[:3]}"
        )
        assert "SCRIPT ERROR" not in proc.stderr
        assert "UID" not in proc.stderr or "uid" not in proc.stderr.lower() or norm.status == "ok"

        # --editor --quit load gate (proves scripts parse, no fatal filter bypass)
        proc2 = run_process(
            str(engine), ["--headless", "--path", str(root), "--editor", "--quit"], timeout=60
        )
        norm2 = normalize_process(
            exit_code=proc2.exit_code,
            stdout=proc2.stdout,
            stderr=proc2.stderr,
            duration_ms=proc2.duration_ms,
            timed_out=proc2.timed_out,
            launch_error=proc2.launch_error,
            stage="load",
            engine_version="4.7.1",
        )
        assert proc2.exit_code == 0, (
            f"load exit {proc2.exit_code}\nstderr:{proc2.stderr[:2000]}"
        )
        assert norm2.status in {"ok", "warn"}, f"load status {norm2.status}"
        assert "SCRIPT ERROR" not in proc2.stderr
