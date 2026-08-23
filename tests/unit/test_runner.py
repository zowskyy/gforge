import sys

from godotforge_core.engine.runner import run_process


def test_run_process_success() -> None:
    result = run_process(sys.executable, ["-c", "print('hello')"])
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.launch_error is None
    assert "hello" in result.stdout
    assert result.duration_ms >= 0
    assert result.args == ("-c", "print('hello')")
    assert result.executable == sys.executable


def test_run_process_nonzero_exit() -> None:
    result = run_process(sys.executable, ["-c", "import sys; sys.exit(3)"])
    assert result.exit_code == 3
    assert result.timed_out is False
    assert result.launch_error is None


def test_run_process_timeout() -> None:
    result = run_process(
        sys.executable,
        ["-c", "import time; time.sleep(5)"],
        timeout=0.2,
    )
    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.launch_error is not None
    assert "timeout" in result.launch_error


def test_run_process_nonexistent_executable() -> None:
    result = run_process("does-not-exist-xyz-12345", ["--help"])
    assert result.exit_code == -2
    assert result.timed_out is False
    assert result.launch_error is not None
    assert result.stdout == ""
    assert result.stderr == ""


def test_run_process_env_passthrough() -> None:
    result = run_process(
        sys.executable,
        ["-c", "import os; print(os.environ.get('FORGE_TEST_ENV', ''))"],
        env={"FORGE_TEST_ENV": "hello-forge"},
    )
    assert result.exit_code == 0
    assert "hello-forge" in result.stdout


def test_run_process_env_does_not_drop_path() -> None:
    # Overlay must preserve PATH so the executable can still be found.
    result = run_process(
        sys.executable,
        ["-c", "import sys; print(sys.version)"],
        env={"FORGE_TEST_ENV2": "x"},
    )
    assert result.exit_code == 0
    assert result.launch_error is None


def test_run_process_args_tuple_immutable() -> None:
    result = run_process(sys.executable, ("-c", "print(42)"))
    assert result.args == ("-c", "print(42)")
    assert isinstance(result.args, tuple)
