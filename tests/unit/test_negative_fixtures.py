from godotforge_core.graph import build_graph, default_store_path, rebuild
from godotforge_core.scan import build_scan_report, index_scenes, parse_script

CASES = "fixtures/cases"


def test_dangling_preload_detected() -> None:
    script = parse_script(
        open(f"{CASES}/dangling-preload/scripts/broken.gd", encoding="utf-8").read(),
        "res://scripts/broken.gd",
    )
    assert any(
        d.kind == "preload" and d.target == "res://scripts/does_not_exist.gd"
        for d in script.dependencies
    )
    graph = build_graph(f"{CASES}/dangling-preload")
    ids = {n.id for n in graph.nodes}
    assert "res://scripts/broken.gd" in ids
    assert "res://scripts/does_not_exist.gd" in ids
    assert any(n.status == "missing" for n in graph.nodes)


def test_missing_scene_reference_detected() -> None:
    scenes = index_scenes(f"{CASES}/missing-scene-ref")
    assert len(scenes) == 1
    graph = build_graph(f"{CASES}/missing-scene-ref")
    assert "res://scenes/missing.tscn" in {n.id for n in graph.nodes}
    assert any(n.status == "missing" for n in graph.nodes)


def test_malformed_scene_does_not_crash() -> None:
    graph = build_graph(f"{CASES}/malformed-scene")
    assert graph is not None


def test_scanner_is_read_only_on_golden() -> None:
    import hashlib
    import pathlib

    root = pathlib.Path("fixtures/golden-2d")
    exclude = {".git", ".godot", ".godotforge", ".pytest-tmp"}

    def hash_tree() -> bytes:
        hasher = hashlib.sha256()
        for path in sorted(root.rglob("*")):
            if path.is_file() and not (exclude & set(path.parts)):
                hasher.update(path.read_bytes())
        return hasher.digest()

    before = hash_tree()
    build_scan_report(root)
    store = default_store_path(root)
    rebuild(root, store)
    after = hash_tree()

    import os

    for suffix in ("", "-wal", "-shm", ".new"):
        candidate = pathlib.Path(str(store) + suffix)
        if candidate.exists():
            os.remove(candidate)

    assert before == after
