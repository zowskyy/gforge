"""godot_text_format.py — the Phase 2b section-file builder, tested on its
own terms before any plan.py emitter is ported onto it."""

from __future__ import annotations

from godotforge_core.creator.godot_text_format import (
    SectionFile,
    color,
    ext_resource,
    packed_vector2_array,
    quoted,
    sub_resource,
    vector2,
    vector3,
)


def test_empty_file_still_gets_trailing_newline() -> None:
    """Matches every existing emitter's own "if not text.endswith('\\n'):
    text += '\\n'" normalization — even a degenerate empty builder isn't
    special-cased around it."""
    assert SectionFile().build() == b"\n"


def test_first_section_has_no_leading_blank_line() -> None:
    out = SectionFile().section("[gd_scene load_steps=1 format=3]").build()
    assert out == b"[gd_scene load_steps=1 format=3]\n"


def test_second_section_gets_one_blank_line_separator() -> None:
    out = (
        SectionFile()
        .section("[node name=\"Main\" type=\"Node2D\"]")
        .section("[node name=\"Player\" type=\"CharacterBody2D\" parent=\".\"]")
        .build()
    )
    assert out == (
        b'[node name="Main" type="Node2D"]\n'
        b"\n"
        b'[node name="Player" type="CharacterBody2D" parent="."]\n'
    )


def test_prop_emits_key_equals_value_with_spaces() -> None:
    out = SectionFile().section("[resource]").prop("health", "100.0").build()
    assert out == b"[resource]\nhealth = 100.0\n"


def test_raw_emits_verbatim_no_spacing_added() -> None:
    out = SectionFile().section("[application]").raw('config/name="My Game"').build()
    assert out == b'[application]\nconfig/name="My Game"\n'


def test_blank_adds_extra_blank_line() -> None:
    out = SectionFile().section("[a]").prop("x", "1").blank().section("[b]").build()
    assert out == b"[a]\nx = 1\n\n\n[b]\n"


def test_build_adds_trailing_newline_if_missing() -> None:
    out = SectionFile().raw("no newline yet").build()
    assert out.endswith(b"\n")
    assert out == b"no newline yet\n"


def test_build_does_not_double_trailing_newline() -> None:
    """A trailing blank() line already makes the joined text end in "\\n"
    (join places "\\n" between "a" and the empty last line) — the
    normalization step must not add a second one."""
    out = SectionFile().raw("a").blank().build()
    assert out == b"a\n"


def test_quoted_escapes_backslash_and_double_quote() -> None:
    assert quoted("plain") == '"plain"'
    assert quoted('has "quotes"') == '"has \\"quotes\\""'
    assert quoted("back\\slash") == '"back\\\\slash"'


def test_vector2_and_vector3_literal_shape() -> None:
    assert vector2(0, 128) == "Vector2(0, 128)"
    assert vector2(0.0, -0.5) == "Vector2(0.0, -0.5)"
    assert vector3(0.0, -0.5, 0.0) == "Vector3(0.0, -0.5, 0.0)"


def test_packed_vector2_array_joins_all_coords() -> None:
    assert packed_vector2_array(-16, -16, 16, -16, 16, 16, -16, 16) == (
        "PackedVector2Array(-16, -16, 16, -16, 16, 16, -16, 16)"
    )


def test_color_default_alpha_is_bare_one() -> None:
    assert color(0.26, 0.53, 0.96) == "Color(0.26, 0.53, 0.96, 1)"
    assert color(0.26, 0.53, 0.96, 1) == "Color(0.26, 0.53, 0.96, 1)"


def test_ext_resource_and_sub_resource_reference_shape() -> None:
    assert ext_resource("1_script") == 'ExtResource("1_script")'
    assert sub_resource("CircleShape2D_player") == 'SubResource("CircleShape2D_player")'
