"""Project graph model: nodes (files/resources) and dependency edges."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GraphNode:
    """GraphNode — production class."""

    id: str
    kind: str
    label: str
    checksum: str | None = None
    status: str = "valid"


@dataclass
class GraphEdge:
    """GraphEdge — production class."""

    source: str
    target: str
    kind: str
    confidence: float = 0.9


@dataclass
class ProjectGraph:
    """ProjectGraph — production class."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    main_scene: str | None = None


VALID_STATUSES = {"valid", "missing", "stale", "corrupt", "rebuilding", "inconclusive"}
