from godotforge_core.engine.parser import parse_engine_output


def test_parse_error_with_location() -> None:
    text = "ERROR: Some error message\n   at: some_function (some_file.cpp:123)\n"
    diags = parse_engine_output(text, stage="load", stream="stderr", engine_version="4.7.1")
    assert len(diags) == 1
    d = diags[0]
    assert d.severity == "error"
    assert d.message == "Some error message"
    assert d.location == "some_function (some_file.cpp:123)"
    assert d.source == "godot"
    assert d.stage == "load"
    assert d.stream == "stderr"
    assert d.engine_version == "4.7.1"


def test_parse_warning() -> None:
    text = "WARNING: Some warning\n"
    diags = parse_engine_output(text)
    assert len(diags) == 1
    assert diags[0].severity == "warning"
    assert diags[0].message == "Some warning"
    assert diags[0].location is None


def test_parse_multiline_error() -> None:
    text = "ERROR: First line\n   at: func (file.cpp:10)\nERROR: Second\n"
    diags = parse_engine_output(text)
    assert len(diags) == 2
    assert diags[0].message == "First line"
    assert diags[0].location == "func (file.cpp:10)"
    assert diags[1].message == "Second"


def test_parse_forge_json() -> None:
    text = 'GODOTFORGE_DIAGNOSTIC {"severity":"error","code":"MAIN_SCENE_LOAD","message":"oops"}'
    diags = parse_engine_output(text, stage="boot", stream="stderr")
    assert len(diags) == 1
    d = diags[0]
    assert d.source == "forge"
    assert d.code == "MAIN_SCENE_LOAD"
    assert d.message == "oops"
    assert d.severity == "error"
    assert d.stage == "boot"


def test_parse_forge_code_colon() -> None:
    text = "GODOTFORGE_DIAGNOSTIC AUTOLOAD_MISSING: Required autoload is missing: GameState"
    diags = parse_engine_output(text)
    assert len(diags) == 1
    assert diags[0].source == "forge"
    assert diags[0].code == "AUTOLOAD_MISSING"
    assert "GameState" in diags[0].message


def test_parse_version_line() -> None:
    text = "Godot Engine v4.7.1.stable.mono.official.a13da4feb - https://godotengine.org\n"
    diags = parse_engine_output(text)
    assert len(diags) == 1
    assert diags[0].severity == "info"
    assert "Godot Engine" in diags[0].message


def test_parse_empty() -> None:
    assert parse_engine_output("") == []
    assert parse_engine_output("   \n  ") == []


def test_parse_mixed() -> None:
    text = "\n".join(
        [
            "Godot Engine v4.7.1.stable.mono.official.a13da4feb",
            "ERROR: Failed to load res://missing.tscn",
            "   at: load (core/io/resource_loader.cpp:100)",
            "WARNING: Something odd",
            'GODOTFORGE_DIAGNOSTIC {"severity":"error","code":"NODE_MISSING","message":"Player"}',
        ]
    )
    diags = parse_engine_output(text, stage="boot", stream="stderr", engine_version="4.7.1")
    # version + error + warning + forge = 4
    assert len(diags) == 4
    assert diags[0].severity == "info"
    assert diags[1].severity == "error"
    assert diags[1].location is not None
    assert diags[2].severity == "warning"
    assert diags[3].source == "forge"
    assert diags[3].code == "NODE_MISSING"


def test_parse_forge_inside_error_line() -> None:
    # Boot script does push_error("GODOTFORGE_DIAGNOSTIC ...") which Godot prefixes with ERROR:
    text = "ERROR: GODOTFORGE_DIAGNOSTIC AUTOLOAD_MISSING: missing\n"
    diags = parse_engine_output(text)
    # Should capture Forge diagnostic, not generic error
    assert len(diags) == 1
    assert diags[0].source == "forge"
    assert diags[0].code == "AUTOLOAD_MISSING"
