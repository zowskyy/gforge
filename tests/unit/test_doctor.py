import json
from pathlib import Path

import godotforge_core.services.doctor as doctor_module
import pytest
from click.testing import CliRunner
from godotforge_core.detection.engine import EngineInfo

from godotforge_cli.app import cli


def _fake_engine_info() -> EngineInfo:
    return EngineInfo(
        executable=Path("C:/fake/godot_console.exe"),
        raw_version="4.7.1.stable.mono.official",
        version="4.7.1",
        flavor="mono",
    )


def _ok_check(name: str) -> doctor_module.DoctorCheck:
    return doctor_module.DoctorCheck(name, "ok", f"{name} present", {"present": True})


def _patch_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        doctor_module,
        "platform_info",
        lambda: {"os": "Test", "arch": "x86_64", "python_version": "3.12.0"},
    )


def test_doctor_no_workspace_warns_when_engine_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _patch_platform(monkeypatch)
    monkeypatch.setattr(
        doctor_module, "resolve_engine", lambda **kwargs: Path("C:/fake/godot_console.exe")
    )
    monkeypatch.setattr(doctor_module, "probe_engine", lambda *args, **kwargs: _fake_engine_info())
    monkeypatch.setattr(doctor_module, "check_git", lambda: _ok_check("git"))
    monkeypatch.setattr(doctor_module, "check_dotnet", lambda: _ok_check("dotnet"))

    result = CliRunner().invoke(
        cli,
        ["--project", str(tmp_path), "--format", "json", "doctor"],
    )
    assert result.exit_code == 0

    payload = json.loads(result.output)
    checks = payload["data"]["checks"]

    assert payload["status"] == "warn"
    assert checks["workspace"]["status"] == "warn"
    assert checks["engine"]["status"] == "ok"


def test_doctor_missing_engine_fails(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _patch_platform(monkeypatch)
    monkeypatch.setattr(doctor_module, "resolve_engine", lambda **kwargs: None)
    monkeypatch.setattr(doctor_module, "check_git", lambda: _ok_check("git"))
    monkeypatch.setattr(doctor_module, "check_dotnet", lambda: _ok_check("dotnet"))

    result = CliRunner().invoke(
        cli,
        ["--project", str(tmp_path), "--format", "json", "doctor"],
    )
    assert result.exit_code != 0

    payload = json.loads(result.output)
    checks = payload["data"]["checks"]

    assert payload["status"] == "fail"
    assert checks["engine"]["status"] == "fail"


def test_doctor_checks_are_keyed_by_name() -> None:
    result = CliRunner().invoke(cli, ["--format", "json", "doctor"])
    payload = json.loads(result.output)
    checks = payload["data"]["checks"]
    assert isinstance(checks, dict)
    assert set(checks) >= {"platform", "workspace", "engine", "git"}
