"""Unit tests for deterministic project.godot plan generation (PATCH-0008)."""

from __future__ import annotations

import hashlib
import pathlib
import tempfile
from pathlib import Path

import pytest
from godotforge_core.patch.models import (
    OperationKind,
    PatchPlan,
)
from godotforge_core.patch.project_godot_plan import (
    ProjectGodotPatch,
    _compute_file_hash,
    _make_plan_id,
    plan_update_autoloads,
    plan_update_input_actions,
    plan_update_physics_layer_names,
    plan_update_renderer_settings,
)
from godotforge_core.patch.project_godot_plan import (
    _validate_hash as _vp_hash,
)
from godotforge_core.patch.project_godot_plan import (
    _validate_plan_id as _vp_plan_id,
)
from godotforge_core.patch.project_godot_plan import (
    _validate_relative_path as _vp_relpath,
)
from godotforge_core.scan.project_godot import (
    ProjectSettings,
    _read_sections,
    parse_project_settings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "golden-2d"


def _make_project_godot(tmp_path: Path) -> Path:
    """Create a minimal Godot project root with a valid project.godot."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "project.godot").write_text(
        "config_version=5\n"
        "\n"
        "[application]\n"
        "\n"
        'config/name="Fixture"\n'
        'config/features=PackedStringArray("4.7")\n'
        'run/main_scene="res://scenes/main.tscn"\n'
        "\n"
        "[autoload]\n"
        "\n"
        'GameState="*res://scripts/game_state.gd"\n'
        "\n"
        "[input]\n"
        "\n"
        "jump={\n"
        '"deadzone": 0.5,\n'
        '"events": []\n'
        "}\n"
        "\n"
        "[layer_names]\n"
        "\n"
        '2d_physics/layer_1="World"\n'
        "\n"
        "[rendering]\n"
        "\n"
        'renderer/rendering_method="gl_compatibility"\n',
        encoding="utf-8",
    )
    return root


def _hash(s: str) -> str:
    """Hash."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _file_hash(root: Path, rel: str) -> str:
    """File hash."""
    return _compute_file_hash(root, rel)


def _assert_plan_is_update_project_godot(
    plan: PatchPlan | None, expected_owner: str = "godotforge"
) -> None:
    """Assert plan is update project godot."""
    assert plan is not None, "expected a plan; no-op requests return plan=None"
    assert plan.id.startswith("pg-"), f"unexpected plan id: {plan.id!r}"
    assert len(plan.operations) == 1
    op = plan.operations[0]
    assert op.kind == OperationKind.UPDATE
    assert op.path == "project.godot"
    assert op.owner == expected_owner
    assert op.source == "project_godot_plan"
    assert op.reason
    assert op.expected_hash and len(op.expected_hash) == 64
    assert op.desired_hash and len(op.desired_hash) == 64


def _assert_patch_has_plan_and_content(patch: ProjectGodotPatch, root: Path) -> None:
    """Assert patch has plan and content."""
    _assert_plan_is_update_project_godot(patch.plan)
    assert isinstance(patch.desired_content, bytes)
    assert patch.desired_content  # non-empty
    want = hashlib.sha256(patch.desired_content).hexdigest()
    assert patch.plan.operations[0].desired_hash == want


def _write_and_parse(serialized: bytes) -> ProjectSettings:
    """Write serialized bytes to a temp dir and re-parse."""
    with tempfile.TemporaryDirectory() as td:
        tmproot = Path(td)
        (tmproot / "project.godot").write_bytes(serialized)
        return parse_project_settings(tmproot)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class TestValidationHelpers:
    """Tests for validation helpers."""

    def test_validate_plan_id_accepts(self) -> None:
        # Must match the model's _PLAN_ID_PATTERN:
        #   ^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$
        """Verify validate plan id accepts."""
        for good in ("pg-autoload", "pg-input-jump", "pg-layers-2d_physics-layer_1-World"):
            _vp_plan_id(good)

    def test_validate_plan_id_rejects_empty(self) -> None:
        """Verify validate plan id rejects empty."""
        with pytest.raises(ValueError, match="non-empty"):
            _vp_plan_id("")

    def test_validate_plan_id_rejects_no_prefix(self) -> None:
        """Verify validate plan id rejects no prefix."""
        with pytest.raises(ValueError, match="start with 'pg-'"):
            _vp_plan_id("autoload")

    def test_validate_plan_id_rejects_too_long(self) -> None:
        """Verify validate plan id rejects too long."""
        with pytest.raises(ValueError, match="too long"):
            _vp_plan_id("pg-" + "x" * 200)

    def test_validate_plan_id_rejects_bad_chars(self) -> None:
        """Verify validate plan id rejects bad chars."""
        with pytest.raises(ValueError, match="invalid characters"):
            _vp_plan_id("pg-a b")
        with pytest.raises(ValueError, match="invalid characters"):
            _vp_plan_id("pg-a+b")
        with pytest.raises(ValueError, match="invalid characters"):
            _vp_plan_id("pg-a=b")

    def test_validate_relative_path_accepts(self) -> None:
        """Verify validate relative path accepts."""
        for good in ("project.godot", "scripts/foo.gd", "a/b/c.res"):
            _vp_relpath(good, "x")

    def test_validate_relative_path_rejects_absolute(self) -> None:
        """Verify validate relative path rejects absolute."""
        for bad in ("/foo", "C:\\foo", "\\foo"):
            with pytest.raises(ValueError):
                _vp_relpath(bad, "x")

    def test_validate_relative_path_rejects_traversal(self) -> None:
        """Verify validate relative path rejects traversal."""
        with pytest.raises(ValueError, match="'\\.\\.'"):
            _vp_relpath("a/../b", "x")

    def test_validate_relative_path_rejects_empty(self) -> None:
        """Verify validate relative path rejects empty."""
        with pytest.raises(ValueError, match="non-empty"):
            _vp_relpath("", "x")

    def test_validate_hash_accepts_64_hex(self) -> None:
        """Verify validate hash accepts 64 hex."""
        _vp_hash("a" * 64, "x")

    def test_validate_hash_accepts_none(self) -> None:
        """Verify validate hash accepts none."""
        _vp_hash(None, "x")

    def test_validate_hash_rejects_short(self) -> None:
        """Verify validate hash rejects short."""
        with pytest.raises(ValueError, match="64 hex"):
            _vp_hash("a" * 63, "x")

    def test_validate_hash_rejects_nonhex(self) -> None:
        """Verify validate hash rejects nonhex."""
        with pytest.raises(ValueError, match="64 hex"):
            _vp_hash("g" * 64, "x")


class TestComputeFileHash:
    """Tests for compute file hash."""

    def test_known_file(self, tmp_path: Path) -> None:
        """Verify known file."""
        (tmp_path / "f.gd").write_text("x", encoding="utf-8")
        h = _compute_file_hash(tmp_path, "f.gd")
        assert len(h) == 64
        assert h == hashlib.sha256(b"x").hexdigest()

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Verify missing file raises."""
        with pytest.raises(FileNotFoundError):
            _compute_file_hash(tmp_path, "nope")

    def test_relative_only(self, tmp_path: Path) -> None:
        """Verify relative only."""
        with pytest.raises(ValueError, match="relative"):
            _compute_file_hash(tmp_path, "/abs")


class TestMakePlanId:
    """Tests for make plan id."""

    def test_prefix_and_clean(self) -> None:
        # '+' is not allowed by the model's plan id pattern, so it is
        # sanitized to '-'.
        """Verify prefix and clean."""
        assert _make_plan_id("autoload+GameState") == "pg-autoload-GameState"

    def test_special_chars_become_dashes(self) -> None:
        """Verify special chars become dashes."""
        assert _make_plan_id("a b/c") == "pg-a-b-c"

    def test_empty_cleanup(self) -> None:
        """Verify empty cleanup."""
        assert _make_plan_id("!!!") == "pg-default"

    def test_truncated_to_128(self) -> None:
        """Verify truncated to 128."""
        long_suffix = "x" * 200
        pid = _make_plan_id(long_suffix)
        assert len(pid) <= 128
        assert pid.startswith("pg-")


# ---------------------------------------------------------------------------
# Byte preservation and round-trip
# ---------------------------------------------------------------------------


class TestBytePreservation:
    """The targeted editor must touch only the targeted key spans.

    See docs/contracts/project-settings-adapter.md.
    """

    NONCANONICAL_LF = (
        "; engine configuration file.\n"
        "; It is best edited using the editor UI.\n"
        "\n"
        "config_version=5\n"
        "\n"
        "# human note below\n"
        "[application]\n"
        "\n"
        'config/name="Fixture"\n'
        'config/features=PackedStringArray("4.7")\n'
        'run/main_scene="res://scenes/main.tscn"   \n'  # trailing spaces
        "\n"
        "\n"
        "[autoload]\n"
        "\n"
        'GameState="*res://scripts/game_state.gd"\n'
        "\n"
        "[input]\n"
        "\n"
        "jump={\n"
        '"deadzone": 0.5,\n'
        '"events": []\n'
        "}\n"
    )

    def _write(self, tmp_path: Path, content: bytes) -> Path:
        """Write."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "project.godot").write_bytes(content)
        return root

    @staticmethod
    def _crlf(text: str) -> bytes:
        """Crlf."""
        return text.replace("\n", "\r\n").encode()

    # -- no-op requests ------------------------------------------------

    def test_noop_produces_no_plan_and_identical_bytes_lf(self, tmp_path: Path) -> None:
        """Verify noop produces no plan and identical bytes lf."""
        root = self._write(tmp_path, self.NONCANONICAL_LF.encode())
        original = (root / "project.godot").read_bytes()
        patch = plan_update_autoloads(root)  # no changes requested
        assert patch.plan is None
        assert patch.desired_content == original

    def test_noop_produces_no_plan_and_identical_bytes_crlf(self, tmp_path: Path) -> None:
        """Verify noop produces no plan and identical bytes crlf."""
        root = self._write(tmp_path, self._crlf(self.NONCANONICAL_LF))
        original = (root / "project.godot").read_bytes()
        patch = plan_update_input_actions(root)  # no changes requested
        assert patch.plan is None
        assert patch.desired_content == original

    # -- line-ending style ---------------------------------------------

    def test_crlf_add_update_remove(self, tmp_path: Path) -> None:
        """Verify crlf add update remove."""
        root = self._write(tmp_path, self._crlf(self.NONCANONICAL_LF))
        patch = plan_update_autoloads(
            root,
            add=[("NewAuto", "res://scripts/new_auto.gd")],
            set_singleton=[("GameState", False)],
        )
        out = patch.desired_content
        assert out.count(b"\n") == out.count(b"\r\n"), "mixed line endings introduced"
        assert b'NewAuto="*res://scripts/new_auto.gd"\r\n' in out
        assert b'GameState="res://scripts/game_state.gd"\r\n' in out
        # Removal keeps CRLF too.
        patch2 = plan_update_autoloads(root, remove=["GameState"])
        out2 = patch2.desired_content
        assert out2.count(b"\n") == out2.count(b"\r\n")
        assert b"GameState" not in out2

    def test_lf_add_update_remove(self, tmp_path: Path) -> None:
        """Verify lf add update remove."""
        root = self._write(tmp_path, self.NONCANONICAL_LF.encode())
        patch = plan_update_autoloads(
            root,
            add=[("NewAuto", "res://scripts/new_auto.gd")],
            set_singleton=[("GameState", False)],
        )
        out = patch.desired_content
        assert b"\r" not in out
        assert b'NewAuto="*res://scripts/new_auto.gd"\n' in out
        patch2 = plan_update_autoloads(root, remove=["GameState"])
        assert b"\r" not in patch2.desired_content
        assert b"GameState" not in patch2.desired_content

    # -- comments / whitespace / unrelated bytes ------------------------

    @pytest.mark.parametrize("crlf", [False, True])
    def test_comments_blank_lines_trailing_ws_preserved(self, tmp_path: Path, crlf: bool) -> None:
        """Verify comments blank lines trailing ws preserved."""
        content = self.NONCANONICAL_LF.encode()
        if crlf:
            content = self._crlf(self.NONCANONICAL_LF)
        root = self._write(tmp_path, content)
        patch = plan_update_autoloads(root, add=[("NewAuto", "res://scripts/new_auto.gd")])
        out = patch.desired_content
        nl = b"\r\n" if crlf else b"\n"
        assert b"; engine configuration file." + nl in out
        assert b"# human note below" + nl in out
        assert b'run/main_scene="res://scenes/main.tscn"   ' + nl in out  # trailing spaces
        assert nl + nl in out  # blank lines survive

    @pytest.mark.parametrize("crlf", [False, True])
    def test_only_targeted_lines_change(self, tmp_path: Path, crlf: bool) -> None:
        """Verify only targeted lines change."""
        content = self.NONCANONICAL_LF.encode()
        if crlf:
            content = self._crlf(self.NONCANONICAL_LF)
        root = self._write(tmp_path, content)
        patch = plan_update_autoloads(root, set_singleton=[("GameState", False)])
        before_lines = content.splitlines(keepends=True)
        after_lines = patch.desired_content.splitlines(keepends=True)
        # Same line count (pure replacement, no insertion).
        assert len(before_lines) == len(after_lines)
        changed = [(b, a) for b, a in zip(before_lines, after_lines, strict=True) if b != a]
        assert len(changed) == 1
        old, new = changed[0]
        assert old.startswith(b'GameState="*')
        assert new.startswith(b'GameState="')
        assert b"*" not in new

    def test_unrelated_sections_byte_identical_on_input_change(self, tmp_path: Path) -> None:
        """Verify unrelated sections byte identical on input change."""
        content = self.NONCANONICAL_LF.encode()
        root = self._write(tmp_path, content)
        patch = plan_update_input_actions(root, remove=["jump"])
        out = patch.desired_content.decode()
        # Everything except the jump entry (4 lines) is unchanged.
        expected = content.decode().replace('jump={\n"deadzone": 0.5,\n"events": []\n}\n', "")
        assert out == expected

    def test_final_newline_behavior_preserved(self, tmp_path: Path) -> None:
        """Verify final newline behavior preserved."""
        content = self.NONCANONICAL_LF.encode().rstrip(b"\n")  # no trailing newline
        root = self._write(tmp_path, content)
        patch = plan_update_autoloads(root, remove=["GameState"])
        assert not patch.desired_content.endswith(b"\n")

    # -- golden fixture round trip -------------------------------------

    def test_golden_noop_is_byte_identical(self) -> None:
        """Verify golden noop is byte identical."""
        original = (GOLDEN / "project.godot").read_bytes()
        patch = plan_update_autoloads(GOLDEN)
        assert patch.plan is None
        assert patch.desired_content == original

    def test_golden_change_preserves_everything_else(self) -> None:
        """Verify golden change preserves everything else."""
        orig = parse_project_settings(GOLDEN)
        target = orig.autoloads[0].name if orig.autoloads else None
        patch = plan_update_input_actions(
            GOLDEN,
            add=[("audit_probe", '{\n"deadzone": 0.5,\n"events": []\n}\n')],
        )
        new = _write_and_parse(patch.desired_content)
        assert new.name == orig.name
        assert new.config_version == orig.config_version
        assert list(new.features) == list(orig.features)
        assert new.main_scene == orig.main_scene
        assert len(new.autoloads) == len(orig.autoloads)
        assert {a.name for a in new.input_actions} == {a.name for a in orig.input_actions} | {
            "audit_probe"
        }
        assert dict(new.physics_layer_names) == dict(orig.physics_layer_names)
        assert dict(new.renderer_settings) == dict(orig.renderer_settings)
        assert target is None or target in {a.name for a in new.autoloads}

    def test_config_icon_preserved(self, tmp_path: Path) -> None:
        """Verify config icon preserved."""
        root = _make_project_godot(tmp_path)
        (root / "project.godot").write_text(
            "config_version=5\n\n"
            "[application]\n\n"
            'config/name="Fixture"\n'
            'config/features=PackedStringArray("4.7")\n'
            'config/icon="res://icon.svg"\n'
            'run/main_scene="res://scenes/main.tscn"\n',
            encoding="utf-8",
        )
        patch = plan_update_autoloads(root, add=[("A", "res://a.gd")])
        reparsed = _write_and_parse(patch.desired_content)
        assert reparsed.name == "Fixture"
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            (t / "project.godot").write_bytes(patch.desired_content)
            new_sec = _read_sections(t / "project.godot")
        assert new_sec.get("application", {}).get("config/icon") == '"res://icon.svg"'

    def test_determinism(self, tmp_path: Path) -> None:
        """Verify determinism."""
        root = _make_project_godot(tmp_path)
        a = plan_update_input_actions(
            root, add=[("dash", '{\n"deadzone": 0.25,\n"events": []\n}\n')]
        )
        b = plan_update_input_actions(
            root, add=[("dash", '{\n"deadzone": 0.25,\n"events": []\n}\n')]
        )
        assert a.desired_content == b.desired_content
        assert a.plan is not None and b.plan is not None
        assert a.plan.operations[0].desired_hash == b.plan.operations[0].desired_hash
        assert a.plan.id == b.plan.id


# ---------------------------------------------------------------------------
# plan_update_autoloads
# ---------------------------------------------------------------------------


class TestPlanUpdateAutoloads:
    """Tests for plan update autoloads."""

    def test_add_autoload(self, tmp_path: Path) -> None:
        """Verify add autoload."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(
            root,
            add=[("SceneRouter", "res://scripts/scene_router.gd")],
        )
        _assert_patch_has_plan_and_content(patch, root)
        assert patch.plan.operations[0].reason == "update autoloads"

    def test_remove_autoload(self, tmp_path: Path) -> None:
        """Verify remove autoload."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(root, remove=["GameState"])
        _assert_patch_has_plan_and_content(patch, root)
        new = _write_and_parse(patch.desired_content)
        names = {a.name for a in new.autoloads}
        assert "GameState" not in names

    def test_set_singleton(self, tmp_path: Path) -> None:
        """Verify set singleton."""
        root = _make_project_godot(tmp_path)
        (root / "project.godot").write_text(
            "config_version=5\n\n"
            "[application]\n\n"
            'config/name="Fixture"\n'
            'config/features=PackedStringArray("4.7")\n'
            'run/main_scene="res://scenes/main.tscn"\n'
            "\n"
            "[autoload]\n\n"
            'GameState="*res://scripts/game_state.gd"\n'
            'SceneRouter="*res://scripts/scene_router.gd"\n'
            "\n"
            "[input]\n\n"
            "jump={\n"
            '"deadzone": 0.5,\n'
            '"events": []\n'
            "}\n"
            "\n"
            "[layer_names]\n\n"
            '2d_physics/layer_1="World"\n'
            "\n"
            "[rendering]\n\n"
            'renderer/rendering_method="gl_compatibility"\n',
            encoding="utf-8",
        )
        patch = plan_update_autoloads(
            root,
            set_singleton=[("GameState", False)],
        )
        _assert_patch_has_plan_and_content(patch, root)
        new = _write_and_parse(patch.desired_content)
        gs = next(a for a in new.autoloads if a.name == "GameState")
        assert gs.singleton is False
        assert gs.path == "res://scripts/game_state.gd"

    def test_add_nonexistent_path_rejected(self, tmp_path: Path) -> None:
        """Verify add nonexistent path rejected."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="res://"):
            plan_update_autoloads(
                root,
                add=[("Bad", "scripts/not_res.gd")],
            )

    def test_add_duplicate_rejected(self, tmp_path: Path) -> None:
        """Verify add duplicate rejected."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="already present"):
            plan_update_autoloads(
                root,
                add=[("GameState", "res://scripts/other.gd")],
            )

    def test_remove_nonexistent_rejected(self, tmp_path: Path) -> None:
        """Verify remove nonexistent rejected."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="not present"):
            plan_update_autoloads(root, remove=["NoSuch"])

    def test_set_singleton_nonexistent_rejected(self, tmp_path: Path) -> None:
        """Verify set singleton nonexistent rejected."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="not present"):
            plan_update_autoloads(
                root,
                set_singleton=[("NoSuch", True)],
            )

    def test_plan_id_derived_from_ops(self, tmp_path: Path) -> None:
        """Verify plan id derived from ops."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(
            root,
            add=[("A", "res://a.gd"), ("SceneRouter", "res://b.gd")],
            remove=["GameState"],
            set_singleton=[("SceneRouter", False)],
        )
        assert patch.plan.id.startswith("pg-")
        assert "+" in patch.plan.id or "-" in patch.plan.id or "~" in patch.plan.id

    def test_preserves_unrelated_settings(self, tmp_path: Path) -> None:
        """Verify preserves unrelated settings."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(root, remove=["GameState"])
        new = _write_and_parse(patch.desired_content)
        assert new.name == "Fixture"
        assert new.main_scene == "res://scenes/main.tscn"
        assert list(new.features) == ["4.7"]
        assert dict(new.physics_layer_names) == {"2d_physics/layer_1": "World"}
        assert dict(new.renderer_settings) == {"renderer/rendering_method": "gl_compatibility"}

    def test_noop_produces_no_plan_and_original_bytes(self, tmp_path: Path) -> None:
        """Verify noop produces no plan and original bytes."""
        root = _make_project_godot(tmp_path)
        original = (root / "project.godot").read_bytes()
        patch = plan_update_autoloads(root)  # no ops → no plan
        assert patch.plan is None
        assert patch.desired_content == original
        _write_and_parse(patch.desired_content)  # still parseable


# ---------------------------------------------------------------------------
# plan_update_input_actions
# ---------------------------------------------------------------------------


class TestPlanUpdateInputActions:
    """Tests for plan update input actions."""

    def test_add_action(self, tmp_path: Path) -> None:
        """Verify add action."""
        root = _make_project_godot(tmp_path)
        raw = '{\n"deadzone": 0.25,\n"events": []\n}\n'
        patch = plan_update_input_actions(
            root,
            add=[("dash", raw)],
        )
        _assert_patch_has_plan_and_content(patch, root)

    def test_remove_action(self, tmp_path: Path) -> None:
        """Verify remove action."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_input_actions(root, remove=["jump"])
        _assert_patch_has_plan_and_content(patch, root)
        new = _write_and_parse(patch.desired_content)
        assert {a.name for a in new.input_actions} == set()

    def test_clear_and_add(self, tmp_path: Path) -> None:
        """Verify clear and add."""
        root = _make_project_godot(tmp_path)
        raw = '{\n"deadzone": 0.5,\n"events": []\n}\n'
        patch = plan_update_input_actions(
            root,
            clear=True,
            add=[("new_action", raw)],
        )
        _assert_patch_has_plan_and_content(patch, root)
        new = _write_and_parse(patch.desired_content)
        assert len(new.input_actions) == 1
        assert new.input_actions[0].name == "new_action"

    def test_remove_nonexistent_rejected(self, tmp_path: Path) -> None:
        """Verify remove nonexistent rejected."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="not present"):
            plan_update_input_actions(root, remove=["NoSuch"])

    def test_add_duplicate_without_clear_rejected(self, tmp_path: Path) -> None:
        """Verify add duplicate without clear rejected."""
        root = _make_project_godot(tmp_path)
        raw = '{\n"deadzone": 0.5,\n"events": []\n}\n'
        with pytest.raises(ValueError, match="already present"):
            plan_update_input_actions(
                root,
                add=[("jump", raw)],
            )

    def test_preserves_unrelated(self, tmp_path: Path) -> None:
        """Verify preserves unrelated."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_input_actions(root, remove=["jump"])
        new = _write_and_parse(patch.desired_content)
        assert new.name == "Fixture"
        assert dict(new.physics_layer_names) == {"2d_physics/layer_1": "World"}


# ---------------------------------------------------------------------------
# Input-action literal boundary (opaque validated fragment contract)
# ---------------------------------------------------------------------------


class TestInputActionLiteralValidation:
    """Accepted/rejected cases for the caller-provided literal contract.

    See docs/contracts/project-settings-adapter.md.
    """

    GOOD_MINIMAL = '{\n"deadzone": 0.5,\n"events": []\n}\n'
    GOOD_WITH_EVENT = (
        "{\n"
        '"deadzone": 0.25,\n'
        '"events": [Object(InputEventKey,'
        '"resource_local_to_scene":false,"resource_name":"",'
        '"script":null)]\n'
        "}\n"
    )
    GOOD_NESTED = '{"deadzone": 0.1, "events": [Object(InputEventJoypadButton,"a":(1))]}'

    def _sections(self, patch: ProjectGodotPatch) -> dict:
        """Sections."""
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            (t / "project.godot").write_bytes(patch.desired_content)
            return _read_sections(t / "project.godot")

    # -- accepted ------------------------------------------------------

    def test_accepts_minimal_empty_events(self, tmp_path: Path) -> None:
        """Verify accepts minimal empty events."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_input_actions(root, add=[("dash", self.GOOD_MINIMAL)])
        _assert_patch_has_plan_and_content(patch, root)
        new = _write_and_parse(patch.desired_content)
        dash = next(a for a in new.input_actions if a.name == "dash")
        assert dash.deadzone == 0.5
        assert dash.event_count == 0

    def test_accepts_literal_with_object_event(self, tmp_path: Path) -> None:
        """Verify accepts literal with object event."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_input_actions(root, add=[("dash", self.GOOD_WITH_EVENT)])
        new = _write_and_parse(patch.desired_content)
        dash = next(a for a in new.input_actions if a.name == "dash")
        assert dash.deadzone == 0.25
        assert dash.event_count == 1

    def test_accepts_nested_delimiters(self, tmp_path: Path) -> None:
        """Verify accepts nested delimiters."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_input_actions(root, add=[("dash", self.GOOD_NESTED)])
        _assert_patch_has_plan_and_content(patch, root)

    def test_literal_carried_through_verbatim(self, tmp_path: Path) -> None:
        """The opaque fragment survives unchanged (modulo the file's
        detected newline style, which inserted lines adopt)."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_input_actions(root, add=[("dash", self.GOOD_WITH_EVENT)])
        text = patch.desired_content.decode("utf-8").replace("\r\n", "\n")
        assert f"dash={self.GOOD_WITH_EVENT.strip()}" in text
        # And the re-parsed model sees it as one input action.
        sections = self._sections(patch)
        assert set(sections["input"]) == {"jump", "dash"}

    def test_literal_deterministic_reserialization(self, tmp_path: Path) -> None:
        """Repeated serialization of the same input is byte-identical."""
        root = _make_project_godot(tmp_path)
        patch1 = plan_update_input_actions(root, add=[("dash", self.GOOD_WITH_EVENT)])
        patch2 = plan_update_input_actions(root, add=[("dash", self.GOOD_WITH_EVENT)])
        assert patch1.desired_content == patch2.desired_content
        assert patch1.plan.operations[0].desired_hash == patch2.plan.operations[0].desired_hash

    def test_unrelated_actions_and_settings_preserved(self, tmp_path: Path) -> None:
        """Verify unrelated actions and settings preserved."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_input_actions(root, add=[("dash", self.GOOD_WITH_EVENT)])
        sections = self._sections(patch)
        # Existing action carried through from the file.
        assert '"deadzone": 0.5' in sections["input"]["jump"]
        new = _write_and_parse(patch.desired_content)
        assert new.name == "Fixture"
        assert {a.name for a in new.autoloads} == {"GameState"}
        assert dict(new.physics_layer_names) == {"2d_physics/layer_1": "World"}
        assert dict(new.renderer_settings) == {"renderer/rendering_method": "gl_compatibility"}

    # -- rejected: literals --------------------------------------------

    @pytest.mark.parametrize("raw", ["", "   ", "\n\n"])
    def test_rejects_empty_literal(self, tmp_path: Path, raw: str) -> None:
        """Verify rejects empty literal."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            plan_update_input_actions(root, add=[("dash", raw)])

    def test_rejects_carriage_return(self, tmp_path: Path) -> None:
        """Verify rejects carriage return."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="carriage return"):
            plan_update_input_actions(
                root, add=[("dash", '{\r\n"deadzone": 0.5,\r\n"events": []\r\n}')]
            )

    def test_rejects_not_a_dict(self, tmp_path: Path) -> None:
        """Verify rejects not a dict."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="dict literal"):
            plan_update_input_actions(root, add=[("dash", '["deadzone"]')])

    @pytest.mark.parametrize(
        "raw",
        [
            '{"deadzone": 0.5, "events": []',  # missing closing brace
            '{"deadzone": 0.5, "events": []}}',  # extra closing brace
            '{"deadzone": 0.5, "events": [)]}',  # mis-nested
            '{"events": [Object(InputEventKey,)}',  # unbalanced parens
        ],
    )
    def test_rejects_unbalanced_brackets(self, tmp_path: Path, raw: str) -> None:
        """Verify rejects unbalanced brackets."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="unbalanced|closing brace"):
            plan_update_input_actions(root, add=[("dash", raw)])

    @pytest.mark.parametrize(
        "raw",
        [
            '{"events": [Object()]}',  # no type identifier
            '{"events": [Object(,)]}',  # empty head
            '{"events": [Object(123,"x")]}',  # non-identifier head
            '{"events": [Object(InputEventKey)]}',  # missing comma
        ],
    )
    def test_rejects_malformed_object_expression(self, tmp_path: Path, raw: str) -> None:
        """Verify rejects malformed object expression."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="malformed Object"):
            plan_update_input_actions(root, add=[("dash", raw)])

    def test_rejects_section_injection_after_dict(self, tmp_path: Path) -> None:
        """Text after the closing brace could inject a new section/key."""
        root = _make_project_godot(tmp_path)
        raw = '{"deadzone": 0.5, "events": []}\n\n[rendering]\n\nrenderer/x="evil"\n'
        with pytest.raises(ValueError, match="content after the closing brace"):
            plan_update_input_actions(root, add=[("dash", raw)])
        # Confirm nothing was written.
        assert "[rendering]" in (root / "project.godot").read_text(encoding="utf-8")
        assert "evil" not in (root / "project.godot").read_text(encoding="utf-8")

    def test_rejects_key_injection_after_dict(self, tmp_path: Path) -> None:
        """Verify rejects key injection after dict."""
        root = _make_project_godot(tmp_path)
        raw = '{"deadzone": 0.5, "events": []}\nother_key="evil"'
        with pytest.raises(ValueError, match="content after the closing brace"):
            plan_update_input_actions(root, add=[("dash", raw)])

    def test_rejects_unterminated_string(self, tmp_path: Path) -> None:
        """Verify rejects unterminated string."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="unterminated string"):
            plan_update_input_actions(root, add=[("dash", '{"deadzone": "0.5}')])

    # -- rejected: action names ----------------------------------------

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "dash\n[rendering]\nfoo=1",  # newline → section/key injection
            "dash\revil",  # carriage return
            "dash=x",  # '=' would forge a key line
            "[input]",  # brackets → section injection
            " dash",  # leading space
            "a b",  # inner space
        ],
    )
    def test_rejects_invalid_action_names(self, tmp_path: Path, name: str) -> None:
        """Verify rejects invalid action names."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="input action name"):
            plan_update_input_actions(root, add=[(name, self.GOOD_MINIMAL)])

    def test_rejected_plan_leaves_file_untouched(self, tmp_path: Path) -> None:
        """Verify rejected plan leaves file untouched."""
        root = _make_project_godot(tmp_path)
        before = (root / "project.godot").read_bytes()
        with pytest.raises(ValueError):
            plan_update_input_actions(root, add=[("dash", '{"events": [],}\n[evil]\n')])
        assert (root / "project.godot").read_bytes() == before

    # -- sibling-adapter key safety ------------------------------------

    def test_rejects_invalid_autoload_name(self, tmp_path: Path) -> None:
        """Verify rejects invalid autoload name."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="autoload name"):
            plan_update_autoloads(root, add=[("Bad\n[x]", "res://a.gd")])

    def test_rejects_newline_in_layer_key(self, tmp_path: Path) -> None:
        """Verify rejects newline in layer key."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="newlines"):
            plan_update_physics_layer_names(root, set={"a\nb": "World"})

    def test_rejects_newline_in_layer_value(self, tmp_path: Path) -> None:
        """Verify rejects newline in layer value."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="newlines"):
            plan_update_physics_layer_names(root, set={"2d_physics/layer_1": "A\n[evil]"})

    def test_rejects_newline_in_renderer_value(self, tmp_path: Path) -> None:
        """Verify rejects newline in renderer value."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="newlines"):
            plan_update_renderer_settings(root, set={"renderer/rendering_method": "a\n[evil]"})


# ---------------------------------------------------------------------------
# plan_update_physics_layer_names
# ---------------------------------------------------------------------------


class TestPlanUpdatePhysicsLayerNames:
    """Tests for plan update physics layer names."""

    def test_set_layer(self, tmp_path: Path) -> None:
        """Verify set layer."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_physics_layer_names(
            root,
            set={"2d_physics/layer_2": "UI"},
        )
        _assert_patch_has_plan_and_content(patch, root)

    def test_remove_layer(self, tmp_path: Path) -> None:
        """Verify remove layer."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_physics_layer_names(root, remove=["2d_physics/layer_1"])
        _assert_patch_has_plan_and_content(patch, root)
        new = _write_and_parse(patch.desired_content)
        assert dict(new.physics_layer_names) == {}

    def test_clear_and_set(self, tmp_path: Path) -> None:
        """Verify clear and set."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_physics_layer_names(
            root,
            clear=True,
            set={"3d_physics/layer_1": "World"},
        )
        _assert_patch_has_plan_and_content(patch, root)
        new = _write_and_parse(patch.desired_content)
        assert dict(new.physics_layer_names) == {"3d_physics/layer_1": "World"}

    def test_remove_nonexistent_rejected(self, tmp_path: Path) -> None:
        """Verify remove nonexistent rejected."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="not present"):
            plan_update_physics_layer_names(root, remove=["NoSuch"])

    def test_set_empty_value_rejected(self, tmp_path: Path) -> None:
        """Verify set empty value rejected."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            plan_update_physics_layer_names(
                root,
                set={"2d_physics/layer_1": ""},
            )

    def test_preserves_unrelated(self, tmp_path: Path) -> None:
        """Verify preserves unrelated."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_physics_layer_names(root, set={"2d_physics/layer_1": "Ground"})
        new = _write_and_parse(patch.desired_content)
        assert new.name == "Fixture"
        assert dict(new.renderer_settings) == {"renderer/rendering_method": "gl_compatibility"}


# ---------------------------------------------------------------------------
# plan_update_renderer_settings
# ---------------------------------------------------------------------------


class TestPlanUpdateRendererSettings:
    """Tests for plan update renderer settings."""

    def test_set_setting(self, tmp_path: Path) -> None:
        """Verify set setting."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_renderer_settings(
            root,
            set={"renderer/rendering_method": "forward_plus"},
        )
        _assert_patch_has_plan_and_content(patch, root)

    def test_remove_setting(self, tmp_path: Path) -> None:
        """Verify remove setting."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_renderer_settings(
            root,
            remove=["renderer/rendering_method"],
        )
        _assert_patch_has_plan_and_content(patch, root)
        new = _write_and_parse(patch.desired_content)
        assert dict(new.renderer_settings) == {}

    def test_clear_and_set(self, tmp_path: Path) -> None:
        """Verify clear and set."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_renderer_settings(
            root,
            clear=True,
            set={"renderer/rendering_method": "gl_compatibility"},
        )
        _assert_patch_has_plan_and_content(patch, root)
        new = _write_and_parse(patch.desired_content)
        assert dict(new.renderer_settings) == {"renderer/rendering_method": "gl_compatibility"}

    def test_remove_nonexistent_rejected(self, tmp_path: Path) -> None:
        """Verify remove nonexistent rejected."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="not present"):
            plan_update_renderer_settings(root, remove=["NoSuch"])

    def test_set_empty_value_rejected(self, tmp_path: Path) -> None:
        """Verify set empty value rejected."""
        root = _make_project_godot(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            plan_update_renderer_settings(
                root,
                set={"renderer/rendering_method": ""},
            )

    def test_preserves_unrelated(self, tmp_path: Path) -> None:
        """Verify preserves unrelated."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_renderer_settings(
            root,
            set={"renderer/rendering_method": "forward_plus"},
        )
        new = _write_and_parse(patch.desired_content)
        assert new.name == "Fixture"
        assert dict(new.physics_layer_names) == {"2d_physics/layer_1": "World"}


# ---------------------------------------------------------------------------
# Plan structure
# ---------------------------------------------------------------------------


class TestPlanStructure:
    """Tests for plan structure."""

    def test_all_adapters_produce_update_on_project_godot(self, tmp_path: Path) -> None:
        """Verify all adapters produce update on project godot."""
        root = _make_project_godot(tmp_path)
        patches = [
            plan_update_autoloads(root, add=[("X", "res://x.gd")]),
            plan_update_input_actions(
                root,
                add=[("Y", '{\n"deadzone":0.5,\n"events":[]\n}\n')],
            ),
            plan_update_physics_layer_names(root, set={"2d_physics/layer_1": "Ground"}),
            plan_update_renderer_settings(root, set={"renderer/rendering_method": "forward_plus"}),
        ]
        for p in patches:
            _assert_plan_is_update_project_godot(p.plan)

    def test_patch_desired_hash_matches_content(self, tmp_path: Path) -> None:
        """Verify patch desired hash matches content."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(root, add=[("X", "res://x.gd")])
        want = hashlib.sha256(patch.desired_content).hexdigest()
        assert patch.plan.operations[0].desired_hash == want

    def test_expected_hash_matches_current_file(self, tmp_path: Path) -> None:
        """Verify expected hash matches current file."""
        root = _make_project_godot(tmp_path)
        current = _file_hash(root, "project.godot")
        patch = plan_update_autoloads(root, add=[("X", "res://x.gd")])
        assert patch.plan.operations[0].expected_hash == current


# ---------------------------------------------------------------------------
# Staleness and precondition checks
# ---------------------------------------------------------------------------


class TestStalenessAndPreconditions:
    """Tests for staleness and preconditions."""

    def test_malformed_config_name_rejected_at_plan_time(self, tmp_path: Path) -> None:
        """Verify malformed config name rejected at plan time."""
        from godotforge_core.scan.profile import ProfileError

        root = tmp_path / "bad"
        root.mkdir()
        (root / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/features=PackedStringArray("4.7")\n',
            encoding="utf-8",
        )
        with pytest.raises(ProfileError, match="config/name"):
            plan_update_autoloads(root)

    def test_missing_project_godot_rejected(self, tmp_path: Path) -> None:
        """Verify missing project godot rejected."""
        from godotforge_core.scan.profile import ProfileError

        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ProfileError, match=r"missing project\.godot"):
            plan_update_autoloads(empty)

    def test_plan_rejects_stale_apply_via_preconditions(self, tmp_path: pathlib.Path) -> None:
        """Generate a plan, mutate project.godot, and verify the precondition
        check catches the mismatch."""
        root = _make_project_godot(tmp_path)
        patch = plan_update_autoloads(root, add=[("X", "res://x.gd")])
        (root / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="Mutated"\n',
            encoding="utf-8",
        )
        from godotforge_core.patch.preconditions import check_plan

        report = check_plan(root, patch.plan)
        assert not report.ok
        assert any("hash" in str(issue).lower() for issue in report.issues)


# ---------------------------------------------------------------------------
# Ambiguity and malformed-file rejection (AdapterError)
# ---------------------------------------------------------------------------


class TestAmbiguityRejection:
    """Ambiguous or malformed targeted sections are rejected, not rewritten."""

    def _write(self, tmp_path: Path, content: str) -> Path:
        """Write."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "project.godot").write_text(content, encoding="utf-8")
        return root

    def test_duplicate_section_header_rejected(self, tmp_path: Path) -> None:
        """Verify duplicate section header rejected."""
        from godotforge_core.patch.project_godot_plan import AdapterError

        root = self._write(
            tmp_path,
            "config_version=5\n\n"
            "[application]\n\n"
            'config/name="Fixture"\n'
            "\n"
            "[autoload]\n\n"
            'GameState="*res://a.gd"\n'
            "\n"
            "[autoload]\n\n"
            'Other="*res://b.gd"\n',
        )
        with pytest.raises(AdapterError, match="duplicate \\[autoload\\]"):
            plan_update_autoloads(root, remove=["GameState"])

    def test_duplicate_key_in_targeted_section_rejected(self, tmp_path: Path) -> None:
        """Verify duplicate key in targeted section rejected."""
        from godotforge_core.patch.project_godot_plan import AdapterError

        root = self._write(
            tmp_path,
            "config_version=5\n\n"
            "[application]\n\n"
            'config/name="Fixture"\n'
            "\n"
            "[autoload]\n\n"
            'GameState="*res://a.gd"\n'
            'GameState="*res://b.gd"\n',
        )
        with pytest.raises(AdapterError, match="duplicate keys"):
            plan_update_autoloads(root, remove=["GameState"])

    def test_duplicate_key_in_unrelated_section_tolerated(self, tmp_path: Path) -> None:
        """Ambiguity outside the targeted section does not block the edit."""
        root = self._write(
            tmp_path,
            "config_version=5\n\n"
            "[application]\n\n"
            'config/name="Fixture"\n'
            "\n"
            "[autoload]\n\n"
            'GameState="*res://a.gd"\n'
            "\n"
            "[rendering]\n\n"
            'renderer/x="1"\n'
            'renderer/x="2"\n',
        )
        patch = plan_update_autoloads(root, remove=["GameState"])
        assert patch.plan is not None
        # The ambiguous unrelated section is carried through untouched.
        assert patch.desired_content.count(b"renderer/x=") == 2

    def test_unterminated_multiline_value_rejected(self, tmp_path: Path) -> None:
        """Verify unterminated multiline value rejected."""
        from godotforge_core.patch.project_godot_plan import AdapterError

        root = self._write(
            tmp_path,
            "config_version=5\n\n"
            "[application]\n\n"
            'config/name="Fixture"\n'
            "\n"
            "[input]\n\n"
            'jump={\n"deadzone": 0.5,\n"events": []\n',  # never closed
        )
        # NOTE: the malformed value swallows EOF; the targeted [input]
        # section is unbalanced and must be rejected.
        with pytest.raises(AdapterError, match="unterminated"):
            plan_update_input_actions(root, remove=["jump"])

    def test_rejected_ambiguous_request_leaves_file_byte_identical(self, tmp_path: Path) -> None:
        """Verify rejected ambiguous request leaves file byte identical."""
        from godotforge_core.patch.project_godot_plan import AdapterError

        content = (
            "config_version=5\n\n"
            "[application]\n\n"
            'config/name="Fixture"\n'
            "\n"
            "[autoload]\n\n"
            'GameState="*res://a.gd"\n'
            'GameState="*res://b.gd"\n'
        )
        root = self._write(tmp_path, content)
        before = (root / "project.godot").read_bytes()
        with pytest.raises(AdapterError):
            plan_update_autoloads(root, remove=["GameState"])
        assert (root / "project.godot").read_bytes() == before
