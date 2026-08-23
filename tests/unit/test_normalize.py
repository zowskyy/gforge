from godotforge_core.engine.normalize import normalize_process


def test_exit0_no_errors_ok() -> None:
    result = normalize_process(
        exit_code=0,
        stdout="Godot Engine v4.7.1\n",
        stderr="",
        duration_ms=100.0,
        timed_out=False,
        launch_error=None,
        stage="load",
        engine_version="4.7.1",
    )
    assert result.status == "ok"
    assert result.exit_code == 0


def test_exit0_known_teardown_warn() -> None:
    result = normalize_process(
        exit_code=0,
        stdout="",
        stderr="ERROR: ObjectDB instances leaked at exit\n",
        duration_ms=100.0,
        timed_out=False,
        launch_error=None,
        stage="boot",
        engine_version="4.7.1",
    )
    assert result.status == "warn"
    assert any(d.classification == "known_teardown_noise" for d in result.diagnostics)
    assert any(d.ignored_for_status for d in result.diagnostics)


def test_exit0_script_error_fail() -> None:
    result = normalize_process(
        exit_code=0,
        stdout="",
        stderr="SCRIPT ERROR: Parse Error\n",
        duration_ms=100.0,
        timed_out=False,
        launch_error=None,
        stage="load",
        engine_version="4.7.1",
    )
    assert result.status == "fail"
    assert any(d.classification == "fatal" for d in result.diagnostics)


def test_exit1_fail() -> None:
    result = normalize_process(
        exit_code=1,
        stdout="",
        stderr="",
        duration_ms=50.0,
        timed_out=False,
        launch_error=None,
        stage="import",
        engine_version="4.7.1",
    )
    assert result.status == "fail"
    assert result.exit_code == 1


def test_timeout_fail() -> None:
    result = normalize_process(
        exit_code=-1,
        stdout="",
        stderr="",
        duration_ms=1000.0,
        timed_out=True,
        launch_error="timeout after 60.0s",
        stage="boot",
        engine_version="4.7.1",
    )
    assert result.status == "fail"
    assert any(d.code == "TIMEOUT" for d in result.diagnostics)


def test_crash_detection() -> None:
    result = normalize_process(
        exit_code=-11,
        stdout="",
        stderr="SIGSEGV: crash\n",
        duration_ms=10.0,
        timed_out=False,
        launch_error=None,
        stage="boot",
        engine_version="4.7.1",
    )
    assert result.status == "fail"
    assert any(d.code == "CRASH" for d in result.diagnostics)


def test_unknown_shutdown_inconclusive() -> None:
    result = normalize_process(
        exit_code=0,
        stdout="",
        stderr="ERROR: UNKNOWN SHUTDOWN NOISE for test\n",
        duration_ms=10.0,
        timed_out=False,
        launch_error=None,
        stage="boot",
        engine_version="4.7.1",
    )
    # Our implementation marks UNKNOWN as inconclusive
    assert result.status == "inconclusive"


def test_fatal_patterns_all() -> None:
    for pat in [
        "SCRIPT ERROR",
        "Parse Error",
        "Failed to load",
        "Cannot get class",
        "Invalid call",
        "Invalid set index",
        "Main scene could not be loaded",
        "autoload initialization failure",
    ]:
        result = normalize_process(
            exit_code=0,
            stdout="",
            stderr=pat,
            duration_ms=10.0,
            timed_out=False,
            launch_error=None,
            stage="load",
            engine_version="4.7.1",
        )
        assert result.status == "fail", f"pattern {pat} should be fatal"


def test_second_resource_still_in_use() -> None:
    result = normalize_process(
        exit_code=0,
        stdout="",
        stderr="ERROR: 2 resources still in use at exit\n",
        duration_ms=10.0,
        timed_out=False,
        launch_error=None,
        stage="boot",
        engine_version="4.7.1",
    )
    assert result.status == "warn"
    assert any("resources still in use" in d.message for d in result.diagnostics)
