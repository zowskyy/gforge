from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "fixtures" / "golden-2d"

EXCLUDE_DIRS = {".godot", ".pytest-tmp", "cache", "reports"}


def _is_excluded(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    for part in rel.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def _hash_tree(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dir_path = Path(dirpath)
        if _is_excluded(dir_path, root):
            continue
        dirnames[:] = [
            d for d in dirnames if d not in EXCLUDE_DIRS and not _is_excluded(dir_path / d, root)
        ]
        for name in sorted(filenames):
            file_path = dir_path / name
            if _is_excluded(file_path, root):
                continue
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            snapshot[str(file_path.relative_to(root).as_posix())] = digest
    return dict(sorted(snapshot.items()))


def _run_doctor() -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "godotforge_cli",
        "--project",
        str(FIXTURE_ROOT),
        "--format",
        "json",
        "doctor",
    ]
    env = dict(os.environ)
    return subprocess.run(command, capture_output=True, text=True, env=env, timeout=120)


@pytest.mark.skipif(
    not FIXTURE_ROOT.exists(),
    reason="golden-2d fixture not present",
)
def test_doctor_leaves_fixture_unchanged() -> None:
    before = _hash_tree(FIXTURE_ROOT)

    result = _run_doctor()

    after = _hash_tree(FIXTURE_ROOT)
    assert before == after, "doctor modified the fixture tree (read-only contract violated)"

    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["command"] == "doctor"
    assert "data" in payload

    engine_path = os.environ.get("FORGE_GODOT_PATH")
    if engine_path and Path(engine_path).exists():
        assert result.returncode == 0
        checks = payload["data"]["checks"]
        assert checks["workspace"]["status"] == "ok"
