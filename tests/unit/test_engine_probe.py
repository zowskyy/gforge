import hashlib
import pathlib

import pytest
from godotforge_core.detection.engine import EngineProbeResult, hash_executable, probe_engine_full


def test_hash_executable_deterministic(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "dummy.exe"
    p.write_bytes(b"hello world")
    h1 = hash_executable(p)
    h2 = hash_executable(p)
    assert h1 == h2
    assert h1 == hashlib.sha256(b"hello world").hexdigest()


def test_probe_nonexistent_returns_none() -> None:
    result = probe_engine_full("does-not-exist-xyz-12345", timeout=2.0)
    assert result is None


def test_probe_with_mocked_run_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    from godotforge_core.engine.runner import ProcessResult

    exe = tmp_path / "Godot_console.exe"
    exe.write_bytes(b"fake binary")

    def fake_run_process(executable, args, **kwargs):  # type: ignore[no-untyped-def]
        assert args == ["--version"]
        return ProcessResult(
            executable=str(executable),
            args=tuple(args),
            exit_code=0,
            stdout="4.7.1.stable.mono.official.a13da4feb\n",
            stderr="",
            duration_ms=12.3,
            timed_out=False,
            launch_error=None,
        )

    monkeypatch.setattr("godotforge_core.engine.runner.run_process", fake_run_process)
    result = probe_engine_full(exe, timeout=5.0)
    assert result is not None
    assert isinstance(result, EngineProbeResult)
    assert result.version == "4.7.1"
    assert result.flavor == "mono"
    assert result.raw_version == "4.7.1.stable.mono.official.a13da4feb"
    assert result.sha256 == hashlib.sha256(b"fake binary").hexdigest()
    assert result.probe_duration_ms == 12.3


def test_probe_standard_flavor(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    from godotforge_core.engine.runner import ProcessResult

    exe = tmp_path / "godot.exe"
    exe.write_bytes(b"x")

    def fake_run(executable, args, **kwargs):  # type: ignore[no-untyped-def]
        return ProcessResult(
            executable=str(executable),
            args=tuple(args),
            exit_code=0,
            stdout="4.7.1.stable.official.abc\n",
            stderr="",
            duration_ms=1.0,
            timed_out=False,
            launch_error=None,
        )

    monkeypatch.setattr("godotforge_core.engine.runner.run_process", fake_run)
    result = probe_engine_full(exe)
    assert result is not None
    assert result.flavor == "standard"
    assert result.version == "4.7.1"


def test_probe_timeout_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    from godotforge_core.engine.runner import ProcessResult

    exe = tmp_path / "godot.exe"
    exe.write_bytes(b"x")

    def fake_run(executable, args, **kwargs):  # type: ignore[no-untyped-def]
        return ProcessResult(
            executable=str(executable),
            args=tuple(args),
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=100.0,
            timed_out=True,
            launch_error="timeout after 5.0s",
        )

    monkeypatch.setattr("godotforge_core.engine.runner.run_process", fake_run)
    assert probe_engine_full(exe) is None


def test_probe_real_godot_if_available() -> None:
    import os

    from godotforge_core.detection.engine import resolve_engine

    exe = resolve_engine(env=os.environ)
    if exe is None or not exe.is_file():
        pytest.skip("Godot executable not available")
    result = probe_engine_full(exe, timeout=10.0)
    assert result is not None
    assert result.version == "4.7.1"
    # golden is mono
    assert result.flavor in ("mono", "standard")
    assert len(result.sha256) == 64
    assert result.probe_duration_ms >= 0
