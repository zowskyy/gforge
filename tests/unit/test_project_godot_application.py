"""Unit and apply tests for application settings adapter (PATCH-0010 core-only)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from godotforge_core.patch.apply import apply_plan
from godotforge_core.patch.backup import create_backup
from godotforge_core.patch.models import OperationKind
from godotforge_core.patch.preconditions import check_plan
from godotforge_core.patch.project_godot_plan import (
    AdapterError,
    plan_update_application_settings,
)
from godotforge_core.scan.profile import ProfileError
from godotforge_core.scan.project_godot import parse_project_settings


def _make(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "project.godot").write_text(
        "config_version=5\n\n"
        "[application]\n\n"
        'config/name="Fixture"\n'
        'config/description="Desc"\n'
        'config/icon="res://icon.svg"\n'
        'run/main_scene="res://scenes/main.tscn"\n'
        "\n"
        "[autoload]\n\n"
        'GameState="*res://scripts/game_state.gd"\n'
        "\n"
        "[input]\n\n"
        "jump={\n"
        '"deadzone": 0.5,\n'
        '"events": []\n'
        "}\n"
        "\n"
        "[rendering]\n\n"
        'renderer/rendering_method="gl_compatibility"\n',
        encoding="utf-8",
    )
    return root


def _make_minimal(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "project.godot").write_text(
        'config_version=5\n\n[application]\n\nconfig/name="Fixture"\n',
        encoding="utf-8",
    )
    return root


def _parse(root: Path):
    return parse_project_settings(root)


def _write_and_parse(content: bytes):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "project.godot").write_bytes(content)
        return parse_project_settings(p)


class TestSetRemoveCombined:
    def test_set_name(self, tmp_path: Path):
        root = _make(tmp_path)
        patch = plan_update_application_settings(root, set={"config/name": "New Name"})
        assert patch.plan is not None
        assert patch.plan.operations[0].kind == OperationKind.UPDATE
        assert "New Name" in patch.desired_content.decode()

    def test_remove_description(self, tmp_path: Path):
        root = _make(tmp_path)
        patch = plan_update_application_settings(root, remove=["config/description"])
        assert patch.plan is not None
        _write_and_parse(patch.desired_content)
        # description is not stored in ProjectSettings, check raw absence
        assert "config/description" not in patch.desired_content.decode()

    def test_combined_set_and_remove(self, tmp_path: Path):
        root = _make(tmp_path)
        patch = plan_update_application_settings(
            root, set={"config/name": "Combined"}, remove=["config/icon"]
        )
        assert patch.plan is not None
        txt = patch.desired_content.decode()
        assert "Combined" in txt
        assert "config/icon" not in txt


class TestRequiredAndOptional:
    def test_missing_config_name_profile_error_no_mutation(self, tmp_path: Path):
        root = tmp_path / "proj"
        root.mkdir()
        (root / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/description="No name"\n',
            encoding="utf-8",
        )
        before = (root / "project.godot").read_bytes()
        with pytest.raises(ProfileError, match="config/name"):
            plan_update_application_settings(root, set={"config/name": "New"})
        assert (root / "project.godot").read_bytes() == before

    def test_config_name_cannot_be_removed(self, tmp_path: Path):
        root = _make(tmp_path)
        before = (root / "project.godot").read_bytes()
        with pytest.raises(ValueError, match="config/name"):
            plan_update_application_settings(root, remove=["config/name"])
        assert (root / "project.godot").read_bytes() == before

    def test_same_value_noop_exact_bytes_no_mutation(self, tmp_path: Path):
        root = _make(tmp_path)
        before = (root / "project.godot").read_bytes()
        patch = plan_update_application_settings(root, set={"config/name": "Fixture"})
        assert patch.plan is None
        assert patch.desired_content == before
        assert (root / "project.godot").read_bytes() == before

    def test_remove_optional_icon_when_absent_raises(self, tmp_path: Path):
        root = _make_minimal(tmp_path)
        with pytest.raises(ValueError, match="not present"):
            plan_update_application_settings(root, remove=["config/icon"])

    def test_remove_optional_description_when_present_ok(self, tmp_path: Path):
        root = _make(tmp_path)
        patch = plan_update_application_settings(root, remove=["config/description"])
        assert patch.plan is not None

    def test_unknown_key_raises(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="unknown application key"):
            plan_update_application_settings(root, set={"config_version": "5"})
        with pytest.raises(ValueError, match="unknown application key"):
            plan_update_application_settings(root, remove=["config/features"])

    def test_noop_empty_request(self, tmp_path: Path):
        root = _make(tmp_path)
        before = (root / "project.godot").read_bytes()
        patch = plan_update_application_settings(root)
        assert patch.plan is None
        assert patch.desired_content == before


class TestConflicting:
    def test_set_and_remove_same_key(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="both set and removed"):
            plan_update_application_settings(
                root, set={"config/icon": "res://new.svg"}, remove=["config/icon"]
            )

    def test_duplicate_set_remove_conflict(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="both set and removed"):
            plan_update_application_settings(
                root, set={"run/main_scene": "res://a.tscn"}, remove=["run/main_scene"]
            )


class TestInvalidValues:
    def test_empty_name(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            plan_update_application_settings(root, set={"config/name": ""})

    def test_name_with_newline(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="newlines"):
            plan_update_application_settings(root, set={"config/name": "A\nB"})

    def test_description_with_newline(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="newlines"):
            plan_update_application_settings(root, set={"config/description": "a\nb"})

    def test_icon_not_res(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="res://"):
            plan_update_application_settings(root, set={"config/icon": "icon.svg"})
        with pytest.raises(ValueError, match="res://"):
            plan_update_application_settings(root, set={"config/icon": "uid://abc"})

    def test_icon_with_backslash(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError):
            plan_update_application_settings(root, set={"config/icon": "res://a\\b.svg"})

    def test_main_scene_invalid_forms(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="res://.*uid://"):
            plan_update_application_settings(root, set={"run/main_scene": "scenes/main.tscn"})
        with pytest.raises(ValueError):
            plan_update_application_settings(root, set={"run/main_scene": ""})
        with pytest.raises(ValueError, match="newlines"):
            plan_update_application_settings(root, set={"run/main_scene": "res://a\nb.tscn"})


class TestUriForms:
    def test_res_uri_accepted(self, tmp_path: Path):
        root = _make(tmp_path)
        patch = plan_update_application_settings(
            root, set={"run/main_scene": "res://scenes/other.tscn"}
        )
        assert patch.plan is not None
        assert "res://scenes/other.tscn" in patch.desired_content.decode()

    def test_uid_uri_accepted(self, tmp_path: Path):
        root = _make(tmp_path)
        patch = plan_update_application_settings(
            root, set={"run/main_scene": "uid://cn47sdqsmtchm"}
        )
        assert patch.plan is not None
        assert "uid://cn47sdqsmtchm" in patch.desired_content.decode()

    def test_local_uri_rejected(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="res://.*uid://"):
            plan_update_application_settings(root, set={"run/main_scene": "local://foo.tscn"})

    def test_user_uri_rejected(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="res://.*uid://"):
            plan_update_application_settings(root, set={"run/main_scene": "user://save.tscn"})


class TestAmbiguity:
    def _write(self, tmp_path: Path, content: str) -> Path:
        root = tmp_path / "proj"
        root.mkdir()
        (root / "project.godot").write_text(content, encoding="utf-8")
        return root

    def test_duplicate_section(self, tmp_path: Path):
        root = self._write(
            tmp_path,
            'config_version=5\n\n[application]\n\nconfig/name="A"\n\n[application]\n\nconfig/name="B"\n',
        )
        with pytest.raises(AdapterError, match="duplicate \\[application\\]"):
            plan_update_application_settings(root, set={"config/name": "C"})

    def test_duplicate_key(self, tmp_path: Path):
        root = self._write(
            tmp_path,
            'config_version=5\n\n[application]\n\nconfig/name="A"\nconfig/name="B"\n',
        )
        with pytest.raises(AdapterError, match="duplicate keys"):
            plan_update_application_settings(root, set={"config/name": "C"})

    def test_unterminated_multiline(self, tmp_path: Path):
        root = self._write(
            tmp_path,
            'config_version=5\n\n[application]\n\nconfig/name="A"\nrun/main_scene={\n',
        )
        with pytest.raises(AdapterError, match="unterminated"):
            plan_update_application_settings(root, set={"config/name": "B"})

    def test_duplicate_in_unrelated_section_tolerated(self, tmp_path: Path):
        root = self._write(
            tmp_path,
            'config_version=5\n\n[application]\n\nconfig/name="A"\n\n[rendering]\n\nrenderer/x="1"\nrenderer/x="2"\n',
        )
        patch = plan_update_application_settings(root, set={"config/name": "B"})
        assert patch.plan is not None
        assert patch.desired_content.count(b"renderer/x=") == 2


class TestBytePreservation:
    NONCANONICAL = (
        "; header\n\n"
        "config_version=5\n\n"
        "[application]\n\n"
        'config/name="Fixture"   \n'
        'config/icon="res://icon.svg"\n'
        "\n"
        "[autoload]\n\n"
        'GameState="*res://a.gd"\n'
    )

    def _write(self, tmp_path: Path, content: bytes) -> Path:
        root = tmp_path / "proj"
        root.mkdir()
        (root / "project.godot").write_bytes(content)
        return root

    def test_comments_and_whitespace_preserved(self, tmp_path: Path):
        root = self._write(tmp_path, self.NONCANONICAL.encode())
        patch = plan_update_application_settings(root, set={"config/name": "New"})
        out = patch.desired_content
        assert b"; header\n" in out
        assert b'config/icon="res://icon.svg"\n' in out
        # trailing spaces on original name line are gone (replaced), but other lines preserved

    def test_unrelated_section_identical(self, tmp_path: Path):
        root = self._write(tmp_path, self.NONCANONICAL.encode())
        patch = plan_update_application_settings(root, set={"config/name": "New"})
        out = patch.desired_content.decode()
        assert 'GameState="*res://a.gd"' in out

    def test_crlf_preserved(self, tmp_path: Path):
        content = self.NONCANONICAL.replace("\n", "\r\n").encode()
        root = self._write(tmp_path, content)
        patch = plan_update_application_settings(root, set={"config/name": "New"})
        out = patch.desired_content
        assert out.count(b"\r\n") == out.count(b"\n")
        assert b'config/name="New"\r\n' in out

    def test_lf_preserved(self, tmp_path: Path):
        root = self._write(tmp_path, self.NONCANONICAL.encode())
        patch = plan_update_application_settings(root, set={"config/name": "New"})
        assert b"\r" not in patch.desired_content

    def test_final_newline_preserved(self, tmp_path: Path):
        content = self.NONCANONICAL.encode().rstrip(b"\n")
        root = self._write(tmp_path, content)
        patch = plan_update_application_settings(root, set={"config/name": "New"})
        assert not patch.desired_content.endswith(b"\n")
        # with newline preserved
        tmp2 = tmp_path / "p2"
        tmp2.mkdir()
        root2 = self._write(tmp2, self.NONCANONICAL.encode())
        patch2 = plan_update_application_settings(root2, set={"config/name": "New2"})
        assert patch2.desired_content.endswith(b"\n")

    def test_deterministic(self, tmp_path: Path):
        root = _make(tmp_path)
        a = plan_update_application_settings(root, set={"config/name": "Deterministic"})
        b = plan_update_application_settings(root, set={"config/name": "Deterministic"})
        assert a.desired_content == b.desired_content
        assert a.plan.operations[0].desired_hash == b.plan.operations[0].desired_hash


class TestStaleAndApply:
    def test_stale_via_check_plan(self, tmp_path: Path):
        root = _make(tmp_path)
        patch = plan_update_application_settings(root, set={"config/name": "Stale"})
        (root / "project.godot").write_text(
            'config_version=5\n\n[application]\n\nconfig/name="Mutated"\n',
            encoding="utf-8",
        )
        report = check_plan(root, patch.plan)
        assert not report.ok
        assert any("hash" in i.reason.lower() for i in report.issues)

    def test_apply_and_verify(self, tmp_path: Path):
        root = _make(tmp_path)
        patch = plan_update_application_settings(
            root,
            set={"config/name": "Applied", "run/main_scene": "uid://abc123"},
            remove=["config/icon"],
        )
        # check_plan -> backup -> apply
        report = check_plan(root, patch.plan)
        assert report.ok
        manifest = create_backup(root, "tx-app", patch.plan, report)
        result = apply_plan(root, patch.plan, manifest, patch.as_content_provider())
        assert result.status.value == "committed"
        new = _write_and_parse(patch.desired_content)
        assert new.name == "Applied"
        assert new.main_scene == "uid://abc123"
        # verify on-disk
        on_disk = parse_project_settings(root)
        assert on_disk.name == "Applied"
        assert on_disk.main_scene == "uid://abc123"
        txt = (root / "project.godot").read_text(encoding="utf-8")
        assert "config/icon" not in txt

    def test_missing_project_godot(self, tmp_path: Path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(ProfileError):
            plan_update_application_settings(empty, set={"config/name": "X"})

    def test_config_version_out_of_scope(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="unknown application key"):
            plan_update_application_settings(root, set={"config_version": "5"})

    def test_features_out_of_scope(self, tmp_path: Path):
        root = _make(tmp_path)
        with pytest.raises(ValueError, match="unknown application key"):
            plan_update_application_settings(root, set={"config/features": "PackedStringArray()"})
