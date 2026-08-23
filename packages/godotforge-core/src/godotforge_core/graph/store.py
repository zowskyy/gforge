"""Persisted project dependency graph backed by SQLite (WAL).

The graph is the cache layer between the read-only scanner and every
downstream consumer (validate, query, export, the future VS Code surface).
It is always built from scanner output -- never the other way around -- so the
scanner remains authoritative and the store is safely rebuildable.

Design:
* ``open_writer`` opens a read-write connection (creating the file and schema)
  with WAL + foreign keys + a busy timeout.
* ``open_readonly`` opens a read-only connection; if the file is absent it
  raises ``FileNotFoundError`` so callers can report "not built".
* ``rebuild`` writes to a ``.new`` sibling and atomically replaces, so a
  crashed build never leaves a half-written index.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from ..scan.gdscript import index_scripts
from ..scan.paths import exists, filesystem_path, res_path
from ..scan.project_godot import parse_project_settings
from ..scan.tscn import index_scenes
from .model import GraphEdge, GraphNode, ProjectGraph

GRAPH_SCHEMA_VERSION = 1


def classify_resource(path: str) -> str:
    if path.endswith(".gd"):
        return "script"
    if path.endswith(".tscn"):
        return "scene"
    if path.endswith(".tres"):
        return "resource"
    return "asset"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            checksum TEXT,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS edges (
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            kind TEXT NOT NULL,
            confidence REAL NOT NULL,
            PRIMARY KEY (source, target, kind)
        );
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
        CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
        CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
        """
    )


def open_writer(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    return conn


def open_readonly(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    uri = f"file:{path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _upsert_graph(conn: sqlite3.Connection, graph: ProjectGraph, meta: dict[str, str]) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute("DELETE FROM edges")
    conn.executemany(
        "INSERT OR REPLACE INTO nodes (id, kind, label, checksum, status, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(n.id, n.kind, n.label, n.checksum, n.status, now) for n in graph.nodes],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO edges (source, target, kind, confidence) VALUES (?, ?, ?, ?)",
        [(e.source, e.target, e.kind, e.confidence) for e in graph.edges],
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(GRAPH_SCHEMA_VERSION),),
    )
    for key, value in meta.items():
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
    conn.commit()


def build_graph(root: str | Path) -> ProjectGraph:
    root = Path(root)
    graph = ProjectGraph()
    seen: dict[str, GraphNode] = {}

    def add_node(id: str, kind: str, label: str, status: str = "valid") -> GraphNode:
        if id not in seen:
            node = GraphNode(id=id, kind=kind, label=label, status=status)
            seen[id] = node
            graph.nodes.append(node)
        return seen[id]

    project_godot = root / "project.godot"
    if project_godot.exists():
        project_id = res_path("project.godot")
        add_node(project_id, "config", "project.godot")

        settings = parse_project_settings(root)
        for autoload in settings.autoloads:
            if not autoload.path:
                continue
            target = res_path(autoload.path)
            if getattr(autoload, "valid", True) is False:
                status = "invalid"
            else:
                status = "valid" if exists(root, target) else "missing"
            add_node(target, "script", autoload.name, status)
            graph.edges.append(GraphEdge(project_id, target, "autoload", 0.9))

        if settings.main_scene:
            main_scene = res_path(settings.main_scene)
            status = "valid" if exists(root, main_scene) else "missing"
            add_node(main_scene, "scene", settings.main_scene, status)
            graph.edges.append(GraphEdge(project_id, main_scene, "main_scene", 1.0))
            graph.main_scene = main_scene

    for scene in index_scenes(root):
        scene_id = res_path(scene.path)
        add_node(scene_id, "scene", scene.path)
        for ref in scene.ext_resources:
            if not ref.path:
                continue
            target = res_path(ref.path)
            status = "valid" if exists(root, target) else "missing"
            kind = classify_resource(target)
            add_node(target, kind, target, status)
            graph.edges.append(GraphEdge(scene_id, target, "depends_on", 0.98))
        ext_ids = {r.id for r in scene.ext_resources}
        for node in scene.nodes:
            if node.instance and node.instance in ext_ids:
                ref = next(r for r in scene.ext_resources if r.id == node.instance)
                if ref.path:
                    target = res_path(ref.path)
                    graph.edges.append(GraphEdge(scene_id, target, "instance", 0.98))

    for script in index_scripts(root):
        script_id = res_path(script.path)
        add_node(script_id, "script", script.path)
        for dependency in script.dependencies:
            target_value = dependency.target
            if not target_value or dependency.resolution != "static":
                continue
            target = res_path(target_value)
            status = "valid" if exists(root, target) else "missing"
            kind = classify_resource(target)
            add_node(target, kind, target, status)
            graph.edges.append(GraphEdge(script_id, target, "depends_on", dependency.confidence))

    for node in graph.nodes:
        fp = filesystem_path(root, node.id)
        if fp.exists():
            import hashlib

            node.checksum = hashlib.sha256(fp.read_bytes()).hexdigest()
            node.status = "valid"
        else:
            node.status = "missing"

    return graph


def graph_from_store(conn: sqlite3.Connection) -> ProjectGraph:
    graph = ProjectGraph()
    for row in conn.execute("SELECT id, kind, label, checksum, status FROM nodes"):
        graph.nodes.append(
            GraphNode(id=row[0], kind=row[1], label=row[2], checksum=row[3], status=row[4])
        )
    for row in conn.execute("SELECT source, target, kind, confidence FROM edges"):
        graph.edges.append(GraphEdge(source=row[0], target=row[1], kind=row[2], confidence=row[3]))
    return graph


def rebuild(root: str | Path, store_path: str | Path) -> ProjectGraph:
    graph = build_graph(root)
    store_path = Path(store_path)
    temp = store_path.with_suffix(store_path.suffix + ".new")
    conn = open_writer(temp)
    try:
        _upsert_graph(
            conn,
            graph,
            {
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source": "scanner",
                "project_root": str(Path(root)),
            },
        )
    finally:
        conn.close()
    os.replace(temp, store_path)
    for sibling in (store_path.with_suffix(".sqlite-wal"), store_path.with_suffix(".sqlite-shm")):
        if sibling.exists():
            try:
                os.remove(sibling)
            except OSError:
                pass
    return graph


def status(conn: sqlite3.Connection) -> dict:
    counts: dict[str, int] = {}
    for status_value, count in conn.execute("SELECT status, COUNT(*) FROM nodes GROUP BY status"):
        counts[status_value] = count
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    built_at = conn.execute("SELECT value FROM meta WHERE key='built_at'").fetchone()
    return {
        "present": True,
        "node_count": node_count,
        "edge_count": edge_count,
        "by_status": counts,
        "built_at": built_at[0] if built_at else None,
        "schema_version": GRAPH_SCHEMA_VERSION,
    }


def validate(conn: sqlite3.Connection) -> list[dict]:
    issues: list[dict] = []
    for source, target, kind in conn.execute(
        "SELECT e.source, e.target, e.kind FROM edges e "
        "LEFT JOIN nodes n ON e.target = n.id "
        "WHERE n.id IS NULL"
    ):
        issues.append(
            {
                "rule": "dangling-edge",
                "severity": "error",
                "source": source,
                "target": target,
                "edge": kind,
            }
        )
    for node_id, status_value in conn.execute(
        "SELECT id, status FROM nodes WHERE status IN ('missing', 'corrupt')"
    ):
        issues.append(
            {
                "rule": "node-status",
                "severity": "warning",
                "node": node_id,
                "status": status_value,
            }
        )
    return issues


def query(
    conn: sqlite3.Connection,
    *,
    node_id: str | None = None,
    kind: str | None = None,
) -> dict:
    if node_id is not None:
        row = conn.execute(
            "SELECT id, kind, label, checksum, status FROM nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        nodes = (
            [
                {
                    "id": row[0],
                    "kind": row[1],
                    "label": row[2],
                    "checksum": row[3],
                    "status": row[4],
                }
            ]
            if row
            else []
        )
        edges = conn.execute(
            "SELECT source, target, kind, confidence FROM edges WHERE source = ? OR target = ?",
            (node_id, node_id),
        ).fetchall()
    elif kind is not None:
        rows = conn.execute(
            "SELECT id, kind, label, checksum, status FROM nodes WHERE kind = ?",
            (kind,),
        ).fetchall()
        nodes = [
            {
                "id": row[0],
                "kind": row[1],
                "label": row[2],
                "checksum": row[3],
                "status": row[4],
            }
            for row in rows
        ]
        edges = []
    else:
        rows = conn.execute("SELECT id, kind, label, checksum, status FROM nodes").fetchall()
        nodes = [
            {
                "id": row[0],
                "kind": row[1],
                "label": row[2],
                "checksum": row[3],
                "status": row[4],
            }
            for row in rows
        ]
        edges = conn.execute("SELECT source, target, kind, confidence FROM edges").fetchall()

    return {
        "nodes": nodes,
        "edges": [
            {"source": r[0], "target": r[1], "kind": r[2], "confidence": r[3]} for r in edges
        ],
    }


def stats(conn: sqlite3.Connection) -> dict:
    by_kind: dict[str, int] = {}
    for kind, count in conn.execute("SELECT kind, COUNT(*) FROM nodes GROUP BY kind"):
        by_kind[kind] = count
    by_edge: dict[str, int] = {}
    for kind, count in conn.execute("SELECT kind, COUNT(*) FROM edges GROUP BY kind"):
        by_edge[kind] = count
    return {
        "nodes": by_kind,
        "edges": by_edge,
        "node_total": sum(by_kind.values()),
        "edge_total": sum(by_edge.values()),
    }


def vacuum(conn: sqlite3.Connection) -> None:
    conn.execute("VACUUM")
    conn.commit()


def default_store_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".godotforge" / "index.sqlite"
