import sys

from godotforge_core.engine.runner import CaptureConfig, run_process


def test_capture_retains_up_to_limit() -> None:
    cfg = CaptureConfig(max_retained_stdout=10, max_retained_stderr=10)
    result = run_process(
        sys.executable,
        ["-c", "print('x' * 2000000)"],
        capture_config=cfg,
        timeout=5.0,
    )
    assert result.exit_code == 0
    assert result.stdout_truncated is True
    assert len(result.stdout) == 10
    assert result.stderr_truncated is False


def test_capture_truncation_marked() -> None:
    cfg = CaptureConfig(max_retained_stdout=5, max_retained_stderr=5)
    result = run_process(
        sys.executable,
        ["-c", "import sys; print('a'*100); print('b'*100, file=sys.stderr)"],
        capture_config=cfg,
        timeout=5.0,
    )
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True
    assert len(result.stdout) == 5
    assert len(result.stderr) == 5


def test_capture_exit_code_preserved() -> None:
    cfg = CaptureConfig(max_retained_stdout=10)
    result = run_process(
        sys.executable,
        ["-c", "import sys; print('hi'); sys.exit(7)"],
        capture_config=cfg,
    )
    assert result.exit_code == 7
    assert result.stdout_truncated is False or len(result.stdout) <= 10


def test_capture_stderr_separate() -> None:
    cfg = CaptureConfig(max_retained_stdout=100, max_retained_stderr=100)
    result = run_process(
        sys.executable,
        ["-c", "import sys; print('out'); print('err', file=sys.stderr)"],
        capture_config=cfg,
    )
    assert "out" in result.stdout
    assert "err" in result.stderr
    assert "err" not in result.stdout
    assert "out" not in result.stderr
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False


def test_capture_duration_populated() -> None:
    result = run_process(sys.executable, ["-c", "print('hi')"], timeout=5.0)
    assert result.duration_ms >= 0
    assert result.duration_ms < 5000


def test_capture_command_arguments_exact() -> None:
    result = run_process(sys.executable, ["-c", "print(42)"])
    assert result.executable == sys.executable
    assert result.args == ("-c", "print(42)")
    assert isinstance(result.args, tuple)


def test_capture_stdout_disabled() -> None:
    cfg = CaptureConfig(capture_stdout=False, capture_stderr=True)
    result = run_process(
        sys.executable,
        ["-c", "print('hello'); import sys; print('err', file=sys.stderr)"],
        capture_config=cfg,
    )
    assert result.stdout == ""
    assert result.stdout_truncated is False
    assert "err" in result.stderr


def test_capture_stderr_disabled() -> None:
    cfg = CaptureConfig(capture_stdout=True, capture_stderr=False)
    result = run_process(
        sys.executable,
        ["-c", "print('hello'); import sys; print('err', file=sys.stderr)"],
        capture_config=cfg,
    )
    assert result.stderr == ""
    assert result.stderr_truncated is False
    assert "hello" in result.stdout


def test_wall_duration_vs_stage() -> None:
    import tempfile
    from pathlib import Path

    from godotforge_core.engine.validate import ValidateMode, validate_project

    # Use a temp project with no engine - should still produce wall_duration
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "project.godot").write_text('[application]\nconfig/name="x"\n')
        result = validate_project(
            tmp,
            mode=ValidateMode.IMPORT,
            engine_path="does-not-exist-xyz",
            timeout=2.0,
        )
        assert result.wall_duration_ms >= 0
        # No stages should have run, wall still measured
        assert result.status == "fail"
