"""Composite project scan report assembled from the read-only scanners.

``build_scan_report`` aggregates the inventory, project settings, parsed
scenes, parsed scripts, and the in-memory project graph into a single
structured payload. It performs no persistence and no mutation — persistence
is the job of ``godotforge graph rebuild``.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from .gdscript import index_scripts
from .inventory import inventory_project
from .project_godot import parse_project_settings
from .tscn import index_scenes


def build_scan_report(root: str | Path) -> dict:
    """build_scan_report — production helper."""
    # Local import to avoid circular init between scan and graph
    # (graph.store -> scan.gdscript -> scan.__init__ -> report -> graph).
    from ..graph.store import build_graph

    root = Path(root)
    inventory = inventory_project(root)
    settings = parse_project_settings(root)
    scenes = index_scenes(root)
    scripts = index_scripts(root)
    graph = build_graph(root)

    return {
        "project": {
            "root": str(root),
            "godot_version": settings.godot_version or None,
        },
        "inventory": asdict(inventory),
        "settings": asdict(settings),
        "scenes": [asdict(scene) for scene in scenes],
        "scripts": [asdict(script) for script in scripts],
        "graph": {
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
        },
    }
