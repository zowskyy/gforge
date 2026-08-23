import pathlib

from godotforge_core.engine.normalize import normalize_process
from godotforge_core.engine.parser import parse_engine_output

FIXTURE_ROOT = pathlib.Path("fixtures/godot-output/4.7.1")


def _read(name: str) -> str:
    p = FIXTURE_ROOT / name
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def test_version_fixture() -> None:
    text = _read("version.stdout")
    # Version file is just "4.7.1.stable..." without prefix, so parser
    # won't emit info; raw version probing uses regex. Just check content.
    assert "4.7.1" in text


def test_import_ok_no_fatal() -> None:
    stdout = _read("import-ok.stdout")
    stderr = _read("import-ok.stderr")
    diags = parse_engine_output(stdout, stage="import", stream="stdout", engine_version="4.7.1")
    diags += parse_engine_output(stderr, stage="import", stream="stderr", engine_version="4.7.1")
    # Only version info or empty -> no error
    assert all(d.severity != "error" for d in diags)
    norm = normalize_process(
        exit_code=0,
        stdout=stdout,
        stderr=stderr,
        duration_ms=100.0,
        timed_out=False,
        launch_error=None,
        stage="import",
        engine_version="4.7.1",
    )
    assert norm.status == "ok"


def test_import_error_fatal() -> None:
    stderr = _read("import-error.stderr")
    diags = parse_engine_output(stderr, stage="import", stream="stderr", engine_version="4.7.1")
    assert len(diags) == 1
    assert diags[0].severity == "error"
    assert "Failed to load" in diags[0].message
    norm = normalize_process(
        exit_code=1,
        stdout="",
        stderr=stderr,
        duration_ms=100.0,
        timed_out=False,
        launch_error=None,
        stage="import",
        engine_version="4.7.1",
    )
    assert norm.status == "fail"


def test_load_ok() -> None:
    stderr = _read("load-ok.stderr")
    norm = normalize_process(
        exit_code=0,
        stdout=_read("load-ok.stdout"),
        stderr=stderr,
        duration_ms=100.0,
        timed_out=False,
        launch_error=None,
        stage="load",
        engine_version="4.7.1",
    )
    assert norm.status == "ok"


def test_load_error_script_parse() -> None:
    stderr = _read("load-error.stderr")
    # Parser sees SCRIPT ERROR without ERROR: prefix, so it won't parse;
    # raw fatal check will catch it. Ensure normalize marks fail.
    norm = normalize_process(
        exit_code=0,
        stdout="",
        stderr=stderr,
        duration_ms=100.0,
        timed_out=False,
        launch_error=None,
        stage="load",
        engine_version="4.7.1",
    )
    assert norm.status == "fail"


def test_boot_ok_shutdown_noise_warn() -> None:
    stderr = _read("boot-ok.stderr")
    diags = parse_engine_output(stderr, stage="boot", stream="stderr", engine_version="4.7.1")
    assert len(diags) == 2
    assert all(d.severity == "error" for d in diags)
    norm = normalize_process(
        exit_code=0,
        stdout=_read("boot-ok.stdout"),
        stderr=stderr,
        duration_ms=100.0,
        timed_out=False,
        launch_error=None,
        stage="boot",
        engine_version="4.7.1",
    )
    assert norm.status == "warn"
    assert any(d.classification == "known_teardown_noise" for d in norm.diagnostics)


def test_boot_error_autoload_missing() -> None:
    stderr = _read("boot-error.stderr")
    diags = parse_engine_output(stderr, stage="boot", stream="stderr", engine_version="4.7.1")
    assert len(diags) == 1
    assert diags[0].source == "forge"
    assert diags[0].code == "AUTOLOAD_MISSING"
    norm = normalize_process(
        exit_code=1,
        stdout="",
        stderr=stderr,
        duration_ms=100.0,
        timed_out=False,
        launch_error=None,
        stage="boot",
        engine_version="4.7.1",
    )
    assert norm.status == "fail"


def test_fixtures_exist() -> None:
    expected = [
        "version.stdout",
        "import-ok.stdout",
        "import-ok.stderr",
        "import-error.stderr",
        "load-ok.stdout",
        "load-ok.stderr",
        "load-error.stderr",
        "boot-ok.stdout",
        "boot-ok.stderr",
        "boot-error.stderr",
    ]
    for name in expected:
        assert (FIXTURE_ROOT / name).exists(), f"missing fixture {name}"
