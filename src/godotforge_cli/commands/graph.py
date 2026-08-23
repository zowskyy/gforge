"""``godotforge graph`` command group.

Read-only commands (status/validate/query/export/stats) open the index
read-only; mutating commands (rebuild/refresh/vacuum) open it read-write.
The scanner remains authoritative — ``rebuild``/``refresh`` recompute the
graph purely from the project tree.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import click
from godotforge_core.detection.workspace import find_workspace
from godotforge_core.graph import (
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
from godotforge_core.output import OutputFormat, build_envelope, serialize

from godotforge_cli.output import emit


def _resolve(ctx: click.Context) -> tuple[Path, Path]:
    project = ctx.obj.get("project")
    start = Path(project) if project else Path.cwd()
    root = find_workspace(start) or start
    store = default_store_path(root)
    return root, store


def _read_store(store: Path) -> sqlite3.Connection | None:
    try:
        return open_readonly(store)
    except FileNotFoundError:
        return None


@click.group("graph")
def cli() -> None:
    """Query and maintain the persisted project dependency graph."""


@cli.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    _root, store = _resolve(ctx)
    fmt: OutputFormat = ctx.obj["output_format"]
    conn = _read_store(store)
    if conn is None:
        emit(
            build_envelope(
                command="graph.status",
                status="inconclusive",
                data={"present": False, "store": str(store)},
                diagnostics=[
                    {
                        "rule": "graph-not-built",
                        "severity": "info",
                        "message": "project graph not built; run `godotforge graph rebuild`",
                    }
                ],
            ),
            fmt,
        )
        return
    try:
        emit(
            build_envelope(
                command="graph.status",
                status="ok",
                data=status(conn),
            ),
            fmt,
        )
    finally:
        conn.close()


@cli.command("validate")
@click.pass_context
def validate_cmd(ctx: click.Context) -> None:
    _root, store = _resolve(ctx)
    fmt: OutputFormat = ctx.obj["output_format"]
    conn = _read_store(store)
    if conn is None:
        emit(
            build_envelope(
                command="graph.validate",
                status="inconclusive",
                diagnostics=[
                    {
                        "rule": "graph-not-built",
                        "severity": "info",
                        "message": "graph not built",
                    }
                ],
            ),
            fmt,
        )
        return
    try:
        issues = validate(conn)
        state = "ok" if not issues else "warn"
        emit(
            build_envelope(
                command="graph.validate",
                status=state,
                data={"issue_count": len(issues)},
                diagnostics=issues,
            ),
            fmt,
        )
    finally:
        conn.close()


@cli.command("query")
@click.option("--node", default=None, help="Node id (res://...) to inspect.")
@click.option("--kind", default=None, help="Filter nodes by kind.")
@click.pass_context
def query_cmd(ctx: click.Context, node: str | None, kind: str | None) -> None:
    _root, store = _resolve(ctx)
    fmt: OutputFormat = ctx.obj["output_format"]
    conn = _read_store(store)
    if conn is None:
        emit(
            build_envelope(
                command="graph.query",
                status="inconclusive",
                diagnostics=[
                    {"rule": "graph-not-built", "severity": "info", "message": "graph not built"}
                ],
            ),
            fmt,
        )
        return
    try:
        data = query(conn, node_id=node, kind=kind)
        emit(build_envelope(command="graph.query", status="ok", data=data), fmt)
    finally:
        conn.close()


@cli.command("export")
@click.option("--output", "-o", default="-", help="Output file ('-' for stdout).")
@click.pass_context
def export_cmd(ctx: click.Context, output: str) -> None:
    _root, store = _resolve(ctx)
    fmt: OutputFormat = ctx.obj["output_format"]
    conn = _read_store(store)
    if conn is None:
        emit(
            build_envelope(
                command="graph.export",
                status="inconclusive",
                diagnostics=[
                    {"rule": "graph-not-built", "severity": "info", "message": "graph not built"}
                ],
            ),
            fmt,
        )
        return
    try:
        graph = graph_from_store(conn)
        payload = {
            "nodes": [n.__dict__ for n in graph.nodes],
            "edges": [e.__dict__ for e in graph.edges],
        }
        if output == "-":
            emit(build_envelope(command="graph.export", status="ok", data=payload), fmt)
        else:
            envelope = build_envelope(command="graph.export", status="ok", data=payload)
            Path(output).write_text(serialize(envelope, OutputFormat.JSON), encoding="utf-8")
    finally:
        conn.close()


@cli.command("stats")
@click.pass_context
def stats_cmd(ctx: click.Context) -> None:
    _root, store = _resolve(ctx)
    fmt: OutputFormat = ctx.obj["output_format"]
    conn = _read_store(store)
    if conn is None:
        emit(
            build_envelope(
                command="graph.stats",
                status="inconclusive",
                diagnostics=[
                    {"rule": "graph-not-built", "severity": "info", "message": "graph not built"}
                ],
            ),
            fmt,
        )
        return
    try:
        emit(build_envelope(command="graph.stats", status="ok", data=stats(conn)), fmt)
    finally:
        conn.close()


@cli.command("rebuild")
@click.pass_context
def rebuild_cmd(ctx: click.Context) -> None:
    root, store = _resolve(ctx)
    fmt: OutputFormat = ctx.obj["output_format"]
    graph = rebuild(root, store)
    emit(
        build_envelope(
            command="graph.rebuild",
            status="ok",
            data={
                "store": str(store),
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
            },
        ),
        fmt,
    )


@cli.command("refresh")
@click.pass_context
def refresh_cmd(ctx: click.Context) -> None:
    root, store = _resolve(ctx)
    fmt: OutputFormat = ctx.obj["output_format"]
    graph = rebuild(root, store)
    emit(
        build_envelope(
            command="graph.refresh",
            status="ok",
            data={
                "store": str(store),
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
            },
        ),
        fmt,
    )


@cli.command("vacuum")
@click.pass_context
def vacuum_cmd(ctx: click.Context) -> None:
    _root, store = _resolve(ctx)
    fmt: OutputFormat = ctx.obj["output_format"]
    conn = open_writer(store)
    try:
        vacuum(conn)
    finally:
        conn.close()
    emit(
        build_envelope(command="graph.vacuum", status="ok", data={"store": str(store)}),
        fmt,
    )
