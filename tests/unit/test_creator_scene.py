"""Scene — TSCN order, load_steps, Polygon2D/Collision same origin, coin sibling."""

from __future__ import annotations

import re
from pathlib import Path

from godotforge_core.creator.plan import plan_creator_manifest
from godotforge_core.scan.tscn import parse_scene


def _manifest() -> dict:
    return {
        "schema_version": 1,
        "game": {"name": "Dodge Hop", "template": "2d-platformer-minimal"},
        "input": [
            {"name": "move_left", "binding": "ui_left"},
            {"name": "move_right", "binding": "ui_right"},
            {"name": "jump", "binding": "ui_accept"},
        ],
    }


def test_tscn_section_order_and_load_steps(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest())
    tscn_text = patch.desired_contents["scenes/main.tscn"].decode()
    lines = tscn_text.splitlines()
    # Find section starts in order
    order = []
    for line in lines:
        s = line.strip()
        if s.startswith("[gd_scene"):
            order.append("gd_scene")
        elif s.startswith("[ext_resource"):
            order.append("ext_resource")
        elif s.startswith("[sub_resource"):
            order.append("sub_resource")
        elif s.startswith("[node"):
            order.append("node")
    # Must be gd_scene -> ext -> sub -> node (no interleaving)
    assert order[0] == "gd_scene"
    first_ext = order.index("ext_resource")
    first_sub = order.index("sub_resource")
    first_node = order.index("node")
    assert first_ext < first_sub < first_node
    # All ext before any sub, all sub before any node
    seen_sub = False
    seen_node = False
    for kind in order:
        if kind == "sub_resource":
            seen_sub = True
        if kind == "node":
            seen_node = True
        if seen_sub and kind == "ext_resource":
            raise AssertionError("ext_resource after sub_resource")
        if seen_node and kind in {"ext_resource", "sub_resource"}:
            raise AssertionError(f"{kind} after node")

    # load_steps = 1 + ext(2) + sub(3) = 6
    m = re.search(r'load_steps=(\d+)', tscn_text)
    assert m is not None and m.group(1) == "6"
    assert 'format=3' in tscn_text
    assert 'uid="uid://' in tscn_text


def test_tscn_parseable_and_has_expected_nodes(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest())
    # Materialize so parse_scene can read file path
    fp = tmp_path / "scenes/main.tscn"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_bytes(patch.desired_contents["scenes/main.tscn"])
    scene = parse_scene(fp)
    assert scene.format == 3
    assert scene.uid is not None and scene.uid.startswith("uid://")
    names = [(n.name, n.parent) for n in scene.nodes]
    # Main at root, Player/Ground/Coin siblings under Main
    assert ("Main", None) in names
    assert ("Player", ".") in names
    assert ("Ground", ".") in names
    assert ("Coin", ".") in names  # sibling of Ground, not child
    assert ("Camera2D", "Player") in names
    # Coin not under Ground
    assert not any(n.name == "Coin" and n.parent == "Ground" for n in scene.nodes)
    # Polygon2D visuals present for all three
    assert sum(1 for n in scene.nodes if n.name == "Polygon2D") == 3
    # ext 2 scripts
    assert len(scene.ext_resources) == 2
    assert len(scene.sub_resources) == 3


def test_polygon_and_collision_same_origin(tmp_path: Path) -> None:
    patch = plan_creator_manifest(tmp_path, _manifest())
    tscn = patch.desired_contents["scenes/main.tscn"].decode()
    # Player polygon centered at origin: -16..16
    assert "polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)" in tscn
    # Ground polygon 800x32 centered
    assert "polygon = PackedVector2Array(-400, -16, 400, -16, 400, 16, -400, 16)" in tscn
    # Coin octagon r12 centered
    assert "PackedVector2Array(12, 0, 8.49" in tscn
    # Shapes centered (no position offset in sub_resource)
    assert "radius = 16.0" in tscn
    assert "radius = 12.0" in tscn
    assert "size = Vector2(800, 32)" in tscn
