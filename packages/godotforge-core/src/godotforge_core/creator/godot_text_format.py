"""Godot text-resource format builder — Phase 2b of the roadmap plan
(``~/.claude/plans/claude-district-reactive-bear.md``).

Godot's ``.tscn``/``.tres``/``project.godot`` files share one underlying
textual format: a sequence of ``[section header]`` lines, each followed by
``key = value`` property lines, with sections separated by exactly one
blank line and the file ending in a single trailing newline. Before this
module existed, every scene/resource/config emitter in ``plan.py``
independently re-derived that same blank-line and trailing-newline
convention as a flat list of ``lines.append(...)`` calls, and re-typed the
same ``Vector2(...)``/``Color(...)``/``ExtResource(...)``/``SubResource(...)``
literal syntax by hand at each call site.

Deliberately narrow, matching the roadmap's own scoping for this phase:
this only centralizes format *mechanics* (section/blank-line bookkeeping,
the handful of value-literal shapes repeated verbatim across emitters). It
has no opinion on node hierarchy, which properties a node type needs, or
numeric display precision (``f"{x:.1f}"``-style formatting stays each call
site's responsibility, passed through :meth:`SectionFile.prop` as an
already-formatted string) — genericizing *that* would risk silently
changing emitted bytes, which is exactly what porting the two existing
templates onto this builder must NOT do. Composing actual gameplay logic
from reusable building blocks (a much harder, genuinely uncertain claim)
is out of scope here entirely; see the roadmap plan's Phase 2b notes.

No AI, network, or filesystem I/O — pure byte formatting.
"""

from __future__ import annotations


class SectionFile:
    """Incrementally build one Godot text-resource file's bytes."""

    def __init__(self) -> None:
        self._lines: list[str] = []

    def section(self, header: str) -> SectionFile:
        """Start a new ``[header]`` block. Emits a blank line before it
        unless it's the very first line in the file — every existing
        emitter's convention is "blank line between sections, none before
        the first"."""
        if self._lines:
            self._lines.append("")
        self._lines.append(header)
        return self

    def prop(self, key: str, value: str) -> SectionFile:
        """Append one ``key = value`` property line under the current
        section. *value* is already-formatted literal text — use the
        helper functions below (or format numerics at the call site) to
        build it."""
        self._lines.append(f"{key} = {value}")
        return self

    def raw(self, line: str) -> SectionFile:
        """Append one already-formatted line verbatim — for content that
        doesn't fit the ``key = value`` shape (e.g. ``project.godot``'s
        ``config/name="..."`` with no spaces around ``=``, or comment
        lines)."""
        self._lines.append(line)
        return self

    def blank(self) -> SectionFile:
        """Append an extra blank line beyond the automatic inter-section
        one (some emitters put a blank line after a section's last
        property even without a following section)."""
        self._lines.append("")
        return self

    def build(self) -> bytes:
        """Join with LF and enforce exactly one trailing newline —
        matches every existing emitter's final normalization step."""
        text = "\n".join(self._lines)
        if not text.endswith("\n"):
            text += "\n"
        return text.encode("utf-8")


def quoted(value: str) -> str:
    """A double-quoted Godot string literal, escaping backslash and
    double-quote."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def vector2(x: object, y: object) -> str:
    return f"Vector2({x}, {y})"


def vector3(x: object, y: object, z: object) -> str:
    return f"Vector3({x}, {y}, {z})"


def packed_vector2_array(*coords: object) -> str:
    return f"PackedVector2Array({', '.join(str(c) for c in coords)})"


def color(r: object, g: object, b: object, a: object = 1) -> str:
    return f"Color({r}, {g}, {b}, {a})"


def ext_resource(id_: str) -> str:
    return f'ExtResource("{id_}")'


def sub_resource(id_: str) -> str:
    return f'SubResource("{id_}")'
