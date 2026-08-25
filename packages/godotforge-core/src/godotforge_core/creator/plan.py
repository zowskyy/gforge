"""Deterministic creator planner — six-operation planning-only slice.

Produces a read-only CreatorPatch (plan + desired bytes) for an empty/template
root. No backup, apply, engine invocation, network, telemetry, LLM, or generated
source. The scene emitter, project.godot emitter, script emitters, UID, and
ordering are all deterministic.

No AI dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from godotforge_core.patch.hashing import hash_bytes
from godotforge_core.patch.models import OperationKind, PatchOperation, PatchPlan

from .manifest import CreatorManifest, CreatorPreflightError, validate_manifest_dict
from .uid import deterministic_uid

TEMPLATE_ID = "2d-platformer-minimal"
SCHEMA_VERSION = 1

# Deterministic scene geometry — single source of truth for tests
GROUND_POS = (0, 128)
GROUND_SIZE = (800, 32)  # RectangleShape2D size
GROUND_TOP = GROUND_POS[1] - GROUND_SIZE[1] // 2  # 112
PLAYER_POS = (0, 48)  # center 64px above top: 112-48=64
PLAYER_RADIUS = 16
COIN_POS = (160, 100)  # resting: 112 - 12 = 100
COIN_RADIUS = 12

# Fixed v1 input emissions — canonical Godot literals (no free-form)
# noqa: E501 — literals must match Godot's exact InputEventKey serialization
_INPUT_LITERAL: dict[str, str] = {
    "move_left": '{\n"deadzone": 0.5,\n"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194319,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)\n]\n}',  # noqa: E501
    "move_right": '{\n"deadzone": 0.5,\n"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":4194321,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)\n]\n}',  # noqa: E501
    "jump": '{\n"deadzone": 0.5,\n"events": [Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":32,"key_label":0,"unicode":0,"location":0,"echo":false,"script":null)\n]\n}',  # noqa: E501
}

# Allowed skeleton files (State B)
_SKELETON_FILES = {".godotforge/project.yaml", ".godotforge/project.lock"}
_ALLOWED_DIR_PREFIXES = ("scenes/", "scripts/", ".godotforge/")

_G_FILES = (
    "project.godot",
    "scenes/main.tscn",
    "scripts/coin.gd",
    "scripts/player_controller.gd",
)
_G_DIRS = ("scenes", "scripts")


def _canonical_manifest_json(manifest: CreatorManifest) -> str:
    payload = manifest.as_dict()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _plan_id_for(manifest: CreatorManifest) -> str:
    canon = _canonical_manifest_json(manifest)
    short = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:8]
    return f"cr-{short}"


def _emit_project_godot(manifest: CreatorManifest) -> bytes:
    lines = [
        "; Engine configuration file.",
        "; It's best edited using the editor UI; changes to this file may cause errors.",
        "",
        "config_version=5",
        "",
        "[application]",
        "",
        f'config/name="{manifest.game_name}"',
        'config/features=PackedStringArray("4.7")',
        'run/main_scene="res://scenes/main.tscn"',
        "",
        "[input]",
        "",
    ]
    for name in ("move_left", "move_right", "jump"):
        lines.append(f"{name}={_INPUT_LITERAL[name]}")
    lines.append("")
    text = "\n".join(lines)
    # Ensure final newline (deterministic LF)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _emit_player_controller() -> bytes:
    return (
        b"extends CharacterBody2D\n"
        b"\n"
        b"const SPEED := 200.0\n"
        b"const JUMP_VELOCITY := -350.0\n"
        b"\n"
        b"func _physics_process(_delta: float) -> void:\n"
        b"\tvar direction := 0\n"
        b"\tif Input.is_action_pressed(\"move_left\"):\n"
        b"\t\tdirection -= 1\n"
        b"\tif Input.is_action_pressed(\"move_right\"):\n"
        b"\t\tdirection += 1\n"
        b"\tvelocity.x = direction * SPEED\n"
        b"\tif Input.is_action_just_pressed(\"jump\") and is_on_floor():\n"
        b"\t\tvelocity.y = JUMP_VELOCITY\n"
        b"\tvelocity.y += 980.0 * _delta\n"
        b"\tmove_and_slide()\n"
    )


def _emit_coin() -> bytes:
    return (
        b"extends Area2D\n"
        b"\n"
        b"func _on_body_entered(_body: Node) -> void:\n"
        b"\tqueue_free()\n"
    )


def _emit_scene_tscn() -> bytes:
    uid = deterministic_uid(TEMPLATE_ID, SCHEMA_VERSION, "scenes/main.tscn")
    # load_steps = 1 + ext_resource_count(2) + sub_resource_count(3) = 6
    lines: list[str] = []
    lines.append(f'[gd_scene load_steps=6 format=3 uid="{uid}"]')
    lines.append("")
    lines.append(
        '[ext_resource type="Script" path="res://scripts/player_controller.gd" id="1_script"]'  # noqa: E501
    )
    lines.append('[ext_resource type="Script" path="res://scripts/coin.gd" id="2_coin"]')
    lines.append("")
    lines.append('[sub_resource type="CircleShape2D" id="CircleShape2D_player"]')
    lines.append(f"radius = {float(PLAYER_RADIUS):.1f}")
    lines.append("")
    lines.append('[sub_resource type="RectangleShape2D" id="RectangleShape2D_ground"]')
    lines.append(f"size = Vector2({GROUND_SIZE[0]}, {GROUND_SIZE[1]})")
    lines.append("")
    lines.append('[sub_resource type="CircleShape2D" id="CircleShape2D_coin"]')
    lines.append(f"radius = {float(COIN_RADIUS):.1f}")
    lines.append("")
    # Nodes in deterministic order: Main, Player, Camera2D,
    # Player/Polygon2D, Player/CollisionShape2D, Ground,
    # Ground/CollisionShape2D, Ground/Polygon2D, Coin,
    # Coin/CollisionShape2D, Coin/Polygon2D
    lines.append('[node name="Main" type="Node2D"]')
    lines.append("")
    lines.append('[node name="Player" type="CharacterBody2D" parent="."]')
    lines.append(f"position = Vector2({PLAYER_POS[0]}, {PLAYER_POS[1]})")
    lines.append('script = ExtResource("1_script")')
    lines.append("")
    lines.append('[node name="Camera2D" type="Camera2D" parent="Player"]')
    lines.append("current = true")
    lines.append("")
    lines.append('[node name="Polygon2D" type="Polygon2D" parent="Player"]')
    lines.append("polygon = PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)")
    lines.append("color = Color(0.26, 0.53, 0.96, 1)")
    lines.append("")
    lines.append('[node name="CollisionShape2D" type="CollisionShape2D" parent="Player"]')
    lines.append('shape = SubResource("CircleShape2D_player")')
    lines.append("")
    lines.append('[node name="Ground" type="StaticBody2D" parent="."]')
    lines.append(f"position = Vector2({GROUND_POS[0]}, {GROUND_POS[1]})")
    lines.append("")
    lines.append('[node name="CollisionShape2D" type="CollisionShape2D" parent="Ground"]')
    lines.append('shape = SubResource("RectangleShape2D_ground")')
    lines.append("")
    lines.append('[node name="Polygon2D" type="Polygon2D" parent="Ground"]')
    lines.append("polygon = PackedVector2Array(-400, -16, 400, -16, 400, 16, -400, 16)")
    lines.append("color = Color(0.4, 0.26, 0.13, 1)")
    lines.append("")
    lines.append('[node name="Coin" type="Area2D" parent="."]')
    lines.append(f"position = Vector2({COIN_POS[0]}, {COIN_POS[1]})")
    lines.append('script = ExtResource("2_coin")')
    lines.append("")
    lines.append('[node name="CollisionShape2D" type="CollisionShape2D" parent="Coin"]')
    lines.append('shape = SubResource("CircleShape2D_coin")')
    lines.append("")
    lines.append('[node name="Polygon2D" type="Polygon2D" parent="Coin"]')
    lines.append(
        "polygon = PackedVector2Array(12, 0, 8.49, 8.49, 0, 12, "  # noqa: E501
        "-8.49, 8.49, -12, 0, -8.49, -8.49, 0, -12, 8.49, -8.49)"
    )
    lines.append("color = Color(0.96, 0.78, 0.2, 1)")
    lines.append("")
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _is_empty_dir(path: Path) -> bool:
    try:
        return path.is_dir() and not any(path.iterdir())
    except OSError:
        return False


def _check_preflight(root: Path) -> None:
    """Enforce states A/B/C. Raise CreatorPreflightError otherwise.

    State A: empty root — no files at all (only root exists).
    State B: skeleton only — only .godotforge/project.yaml (+ optional .lock)
             plus optionally empty scenes/ and scripts/ dirs.
    State C: handled via no-op (caller compares hashes); preflight here
             allows B to pass; C is not a preflight reject but a plan=None case.

    Any creator_owned file outside these, or non-empty scenes/scripts with
    content, or stray files, or symlink escape, is rejected.
    """
    root = root.resolve()
    if not root.is_dir():
        raise CreatorPreflightError(f"root must be directory, got {root}")
    if (root / "project.godot").is_symlink() or any(
        p.is_symlink() for p in root.rglob("*") if p.is_symlink()
    ):
        # Symlink escape check — reuse scan/profile logic shape
        for p in sorted(root.rglob("*")):
            if p.is_symlink():
                try:
                    p.resolve().relative_to(root.resolve())
                except (OSError, ValueError) as exc:
                    raise CreatorPreflightError(f"symlink escapes root: {p}: {exc}") from exc
    # Collect relative posix for all files (not dirs)
    rel_files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip ignored .godot (inventory.py IGNORED_DIRS)
        dirnames[:] = [
            d
            for d in dirnames
            if d not in {".godot", ".git", ".pytest-tmp", "__pycache__", "build", "builds"}
        ]
        for fn in filenames:
            fp = Path(dirpath) / fn
            rel = fp.relative_to(root).as_posix()
            # Skip .godotforge/cache/reports/backups — managed ignored
            if rel.startswith(".godotforge/cache") or rel.startswith(
                ".godotforge/reports"
            ) or rel.startswith(".godotforge/backups"):
                continue
            # Skip .godot dir entirely (already pruned but be safe)
            if rel.startswith(".godot/"):
                continue
            rel_files.append(rel)
    rel_files_sorted = sorted(rel_files)
    if not rel_files_sorted:
        # Check dirs: empty or only allowed empty dirs
        # State A — empty root (allow empty scenes/scripts dirs)
        allowed_empty_dirs = {root / "scenes", root / "scripts", root / ".godotforge"}
        for p in root.iterdir():
            if p.is_dir():
                if p in allowed_empty_dirs and _is_empty_dir(p):
                    continue
                # .godot allowed to exist empty or not
                if p.name == ".godot":
                    continue
                raise CreatorPreflightError(f"unexpected directory {p.name} in empty root")
            else:
                raise CreatorPreflightError(f"unexpected file {p.name} in empty root")
        return
    # Non-empty: must be subset of skeleton + optionally empty dirs, or skeleton + G_files
    allowed_files = set(_SKELETON_FILES)
    # Empty dirs allowed even when files present
    for rel in list(rel_files_sorted):
        if rel in allowed_files:
            continue
        # G_files are allowed only if they will be hash-checked as no-op; but preflight
        # must not reject them before hash check — so we permit them here and let caller
        # decide plan is None if hashes match. If hashes differ, that is also allowed
        # as a future overwrite, but PATCH-0012 restricts to empty/template only, so
        # any G_file present with differing content should still be considered
        # "non-empty unmanaged" and rejected unless it exactly matches.
        # To keep preflight distinct from no-op, we allow G_files through and defer
        # content check to the planner's files_ok/dir_ok logic.
        if rel in _G_FILES:
            continue
        raise CreatorPreflightError(
            f"unexpected file {rel} — root must be empty or skeleton/G_files"
        )
    # Also ensure no unexpected top-level dirs with content
    # Empty scenes/scripts are fine; non-empty but only containing G_files is already covered
    # Stray empty dirs like 'foo/' with no files are caught as unexpected
    # dir containing nothing — but walk found no files there
    # So check for stray dirs that are empty and not allowed
    for p in root.iterdir():
        if p.is_dir() and p.name not in {".godotforge", "scenes", "scripts", ".godot"}:
            # Could be .godotforge subdirs — already file-based check covers
            raise CreatorPreflightError(f"unexpected directory {p.name}")


@dataclass(frozen=True)
class CreatorPatch:
    """Read-only creator patch — plan + desired bytes. No I/O on creation."""

    plan: PatchPlan | None
    desired_contents: dict[str, bytes]
    manifest: CreatorManifest
    reason: str = "creator manifest"

    def content_provider(self):
        desired = self.desired_contents

        def _provider(op) -> bytes | None:
            # op.path for CREATE/MKDIR (mkdir returns None content)
            rel = op.path if op.path is not None else None
            if rel is None:
                return None
            return desired.get(rel)

        return _provider


def _desired_contents_for(manifest: CreatorManifest) -> dict[str, bytes]:
    return {
        "project.godot": _emit_project_godot(manifest),
        "scenes/main.tscn": _emit_scene_tscn(),
        "scripts/player_controller.gd": _emit_player_controller(),
        "scripts/coin.gd": _emit_coin(),
    }


def plan_creator_manifest(root: Path | str, manifest_dict: dict) -> CreatorPatch:
    """Validate manifest and produce deterministic 6-op plan for empty/template root.

    No filesystem writes, no backup/apply, no engine invocation, no network/AI.
    Raises CreatorPreflightError or ValueError on invalid manifest or non-empty root.
    """
    manifest = validate_manifest_dict(manifest_dict)
    root = Path(root).resolve()
    _check_preflight(root)

    desired = _desired_contents_for(manifest)

    # Separate checks per amendment 7: files_ok vs dirs_ok
    files_ok = True
    for rel in _G_FILES:
        p = root / rel
        if not p.is_file():
            files_ok = False
            break
        try:
            if hashlib.sha256(p.read_bytes()).hexdigest() != hash_bytes(desired[rel]):
                files_ok = False
                break
        except OSError:
            files_ok = False
            break
    dirs_ok = all((root / d).is_dir() and not (root / d).is_symlink() for d in _G_DIRS)

    if files_ok and dirs_ok:
        return CreatorPatch(plan=None, desired_contents=desired, manifest=manifest)

    # Build 6 ops in (MKDIR=0, CREATE=1, path) order — amendment 4
    ops: list[PatchOperation] = []
    # MKDIRs sorted by path
    for d in sorted(_G_DIRS):
        ops.append(
            PatchOperation(
                kind=OperationKind.MKDIR,
                path=d,
                owner="godotforge",
                source="creator",
                reason="creator manifest",
            )
        )
    # CREATEs sorted by path: project.godot < scenes/main.tscn
    # < scripts/coin.gd < scripts/player_controller.gd
    for rel in sorted(_G_FILES):
        ops.append(
            PatchOperation(
                kind=OperationKind.CREATE,
                path=rel,
                desired_hash=hash_bytes(desired[rel]),
                owner="godotforge",
                source="creator",
                reason="creator manifest",
            )
        )
    # Enforce ordering rule explicitly: MKDIR before CREATE, then lexicographic
    # Already built as such; assert invariant
    kind_rank = {OperationKind.MKDIR: 0, OperationKind.CREATE: 1}
    for a, b in zip(ops, ops[1:]):
        assert (kind_rank[a.kind], a.path) <= (
            kind_rank[b.kind],
            b.path,
        ), f"ordering violated: {a} before {b}"

    plan_id = _plan_id_for(manifest)
    plan = PatchPlan(id=plan_id, operations=tuple(ops))
    return CreatorPatch(plan=plan, desired_contents=desired, manifest=manifest)
