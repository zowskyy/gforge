import pathlib
import tempfile

import pytest
from godotforge_core.graph import (
    build_graph,
    default_store_path,
    graph_from_store,
    open_readonly,
    open_writer,
    query,
    rebuild,
    stats,
    status,
    vacuum,
    validate,
)

ROOT = "fixtures/golden-2d"


def test_build_graph_counts() -> None:
    graph = build_graph(ROOT)
    ids = {n.id for n in graph.nodes}
    assert "res://project.godot" in ids
    assert "res://scenes/main.tscn" in ids
    assert "res://scripts/player/player_controller.gd" in ids
    kinds = {e.kind for e in graph.edges}
    assert "depends_on" in kinds
    assert "instance" in kinds


def test_rebuild_and_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = pathlib.Path(tmp) / "index.sqlite"
        graph = rebuild(ROOT, store)
        conn = open_readonly(store)
        try:
            st = status(conn)
            assert st["present"] is True
            assert st["node_count"] == len(graph.nodes)
            assert st["edge_count"] == len(graph.edges)
        finally:
            conn.close()


def test_validate_clean() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = pathlib.Path(tmp) / "index.sqlite"
        rebuild(ROOT, store)
        conn = open_readonly(store)
        try:
            assert validate(conn) == []
        finally:
            conn.close()


def test_query_node() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = pathlib.Path(tmp) / "index.sqlite"
        rebuild(ROOT, store)
        conn = open_readonly(store)
        try:
            res = query(conn, node_id="res://scenes/main.tscn")
            assert any(n["id"] == "res://scenes/main.tscn" for n in res["nodes"])
        finally:
            conn.close()


def test_stats() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "index.sqlite"
        rebuild(ROOT, root)
        conn = open_readonly(root)
        try:
            s = stats(conn)
            assert s["node_total"] > 0
            assert s["edge_total"] > 0
            assert "scene" in s["nodes"]
        finally:
            conn.close()


def test_vacuum() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = pathlib.Path(tmp) / "index.sqlite"
        rebuild(ROOT, store)
        conn = open_writer(store)
        try:
            vacuum(conn)
        finally:
            conn.close()


def test_readonly_missing_raises() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(FileNotFoundError):
            open_readonly(pathlib.Path(tmp) / "nope.sqlite")


def test_roundtrip_graph_from_store() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = pathlib.Path(tmp) / "index.sqlite"
        graph = rebuild(ROOT, store)
        conn = open_readonly(store)
        try:
            restored = graph_from_store(conn)
            assert len(restored.nodes) == len(graph.nodes)
            assert len(restored.edges) == len(graph.edges)
        finally:
            conn.close()


def test_default_store_path() -> None:
    assert default_store_path("fixtures/golden-2d").as_posix().endswith(".godotforge/index.sqlite")


def test_graph_records_main_scene() -> None:
    graph = build_graph(ROOT)
    assert graph.main_scene == "res://scenes/main.tscn"
    assert any(
        edge.kind == "main_scene" and edge.target == "res://scenes/main.tscn"
        for edge in graph.edges
    )
