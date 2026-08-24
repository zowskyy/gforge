"""Deterministic project.godot plan generation.

Produces PatchPlan objects (and the desired serialized content) from a
desired configuration change. The adapters are read-only: they never write
to the project. The desired content is produced by a *line-preserving
targeted editor*: only the targeted key spans in the targeted section are
replaced, inserted, or removed. Every other byte of the original file —
header comments, blank lines, trailing whitespace, line-ending style,
unrelated sections and keys — is carried through unchanged. The desired
content is returned alongside the plan so callers can supply a
content_provider to apply_plan.

Contract (see docs/contracts/project-settings-adapter.md):

- no-op request       -> no PatchPlan (``ProjectGodotPatch.plan is None``),
                         desired content is the original bytes unchanged
- real change         -> minimal byte-preserving update
- ambiguous input     -> AdapterError, no write (duplicate key/section in the
                         targeted section)
- malformed file      -> AdapterError/ProfileError, no write

No AI, LLM, machine-learning, inference, or network dependency.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from godotforge_core.patch.models import (
    OperationKind,
    PatchOperation,
    PatchPlan,
)
from godotforge_core.scan.project_godot import (
    ProjectSettings,
    parse_project_settings,
)

PLAN_ID_PREFIX = "pg"
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class AdapterError(ValueError):
    """project.godot is ambiguous or malformed for a targeted edit.

    Raised instead of rewriting the file when the targeted section
    contains duplicate keys, duplicate section headers, or an
    unterminated multi-line value.
    """


def _validate_plan_id(value: str) -> None:
    """Validate a plan id against the model pattern and pg- prefix."""
    if not value:
        raise ValueError("plan id must be non-empty")
    if not (value[:2] == PLAN_ID_PREFIX and len(value) > 2):
        raise ValueError(f"plan id must start with '{PLAN_ID_PREFIX}-': '{value}'")
    if len(value) > 128:
        raise ValueError(f"plan id too long: '{value}'")
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]*$", value):
        raise ValueError(f"plan id contains invalid characters: '{value}'")


def _validate_relative_path(value: str, field_name: str) -> None:
    """Validate a project-relative path (no absolute, traversal, or newlines)."""
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError(f"{field_name} must be relative, got '{value}'")
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        raise ValueError(f"{field_name} must be relative, got '{value}'")
    if "\x00" in value:
        raise ValueError(f"{field_name} contains null byte")
    if "\r" in value or "\n" in value:
        raise ValueError(f"{field_name} must not contain newlines: '{value}'")
    if "\\" in value:
        raise ValueError(f"{field_name} must use '/' not '\\': '{value}'")
    # Godot resource URIs (res://, uid://, local://, ...) contain '//'
    # but are not filesystem paths.  Allow them.
    if value.startswith(("res://", "uid://", "local://", "user://")):
        parts = value.split("/")
        if ".." in parts:
            raise ValueError(f"{field_name} must not contain '..': '{value}'")
        return
    if "//" in value:
        raise ValueError(f"{field_name} must not contain '//': '{value}'")
    parts = value.split("/")
    if ".." in parts:
        raise ValueError(f"{field_name} must not contain '..': '{value}'")
    if "" in parts:
        raise ValueError(f"{field_name} must not contain empty segment: '{value}'")


def _validate_hash(value: str | None, field_name: str) -> None:
    """Validate an optional 64-character lowercase hex SHA-256 hash."""
    if value is None:
        return
    if not _HASH_PATTERN.match(value):
        raise ValueError(f"invalid {field_name} '{value}' (expected 64 hex)")


# Input action names are emitted verbatim as ``key=`` lines in the [input]
# section.  Restrict them to a conservative charset so a name can never
# inject a new line, key, or section into project.godot.  This covers
# Godot's built-in ``ui_*`` actions and typical custom names.
_ACTION_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}$")

# Autoload names are Godot singleton identifiers, also emitted as keys.
_AUTOLOAD_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _validate_input_action_name(name: str) -> None:
    """Validate an input action name against the safe key charset."""
    if not name:
        raise ValueError("input action name must be non-empty")
    if not _ACTION_NAME_PATTERN.match(name):
        raise ValueError(f"invalid input action name: '{name}'")


def _validate_autoload_name(name: str) -> None:
    """Validate an autoload name as a Godot singleton identifier."""
    if not name:
        raise ValueError("autoload name must be non-empty")
    if not _AUTOLOAD_NAME_PATTERN.match(name):
        raise ValueError(f"invalid autoload name: '{name}'")


_LITERAL_PAIRS = {"{": "}", "[": "]", "(": ")"}
_LITERAL_CLOSERS = {"}": "{", "]": "[", ")": "("}
_OBJECT_CALL = re.compile(r"Object\(")
_OBJECT_CALL_HEAD = re.compile(r"\s*[A-Za-z_][A-Za-z0-9_]*\s*,")


def _validate_input_event_literal(raw: str, action_name: str) -> None:
    """Validate a caller-provided input-action dict literal.

    The literal is an *opaque fragment*: it is carried through to
    project.godot verbatim, so validation must guarantee it cannot escape
    the ``name={...}`` value position it will occupy.  Rules:

    - non-empty after stripping
    - no carriage returns or null bytes (LF inside the dict is normal)
    - exactly one balanced ``{...}`` dict: the outermost brace must close
      at the final non-whitespace character, and ``{}``/``[]``/``()``
      must nest correctly (double-quoted strings are skipped)
    - every ``Object(`` call must start with a type identifier and a
      comma (Godot's ``Object(Type,...)`` event form)

    Because the outer brace closes only at the end, no text can follow
    the dict, so the fragment cannot inject a new section header or
    ``key=`` line regardless of what it contains inside.
    """
    label = f"input event literal for '{action_name}'"
    if not raw or not raw.strip():
        raise ValueError(f"{label} must be non-empty")
    if "\r" in raw:
        raise ValueError(f"{label} must not contain carriage returns")
    if "\x00" in raw:
        raise ValueError(f"{label} must not contain null bytes")
    text = raw.strip()
    if not text.startswith("{"):
        raise ValueError(f"{label} must be a '{{...}}' dict literal")

    stack: list[str] = []
    in_string = False
    escaped = False
    for index, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in _LITERAL_PAIRS:
            stack.append(ch)
        elif ch in _LITERAL_CLOSERS:
            if not stack or stack[-1] != _LITERAL_CLOSERS[ch]:
                raise ValueError(f"{label} has unbalanced '{ch}'")
            stack.pop()
            if not stack and index != len(text) - 1:
                raise ValueError(
                    f"{label} has content after the closing brace; "
                    "the literal must be a single dict"
                )
    if in_string:
        raise ValueError(f"{label} has an unterminated string")
    if stack:
        raise ValueError(f"{label} has unbalanced '{stack[-1]}'")

    for match in _OBJECT_CALL.finditer(text):
        if not _OBJECT_CALL_HEAD.match(text, match.end()):
            raise ValueError(
                f"{label} has a malformed Object(...) expression at offset {match.start()}"
            )


def _validate_serialized_key(key: str, section: str | None) -> None:
    """Defense-in-depth guard for keys/section names at emission time.

    The editor writes ``{key}={value}`` lines under ``[{section}]``; any
    CR/LF or ``=``/``[``/``]`` in either would corrupt the file.  All
    public adapters validate before this point, so this should never
    fire — it exists to catch future callers that bypass them.
    """
    label = f"key '{key}' in section '{section}'"
    if not key:
        raise ValueError(f"empty key in section '{section}'")
    for bad in ("\r", "\n", "\x00", "="):
        if bad in key:
            raise ValueError(f"{label} contains forbidden character {bad!r}")
    if section is not None:
        for bad in ("\r", "\n", "\x00", "[", "]"):
            if bad in section:
                raise ValueError(f"section '{section}' contains forbidden character {bad!r}")


def _compute_file_hash(root: Path, relative: str) -> str:
    """SHA-256 of the project.godot file at *relative* under *root*."""
    _validate_relative_path(relative, "relative")
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(f"missing {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_plan_id(suffix: str) -> str:
    """Stable plan id from a descriptive suffix.

    The id must satisfy :func:`godotforge_core.patch.models._validate_plan_id`
    which uses ``^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,127}$``.  Non-conforming
    characters in *suffix* are replaced with ``-``.
    """
    # Sanitize to match the model's _PLAN_ID_PATTERN.
    sanitized = re.sub(r"[^a-zA-Z0-9._:-]", "-", suffix).strip(".-")
    if not sanitized:
        sanitized = "default"
    candidate = f"{PLAN_ID_PREFIX}-{sanitized}"
    if len(candidate) > 128:
        candidate = candidate[:128]
    return candidate


@dataclass(frozen=True)
class ProjectGodotPatch:
    """A patch for project.godot: plan + desired content.

    The plan targets ``project.godot`` with the file's current hash as
    ``expected_hash`` and the desired edited content hash as
    ``desired_hash``. The ``desired_content`` bytes are what a
    ``ContentProvider`` should return for the ``UPDATE`` operation.

    ``plan`` is ``None`` for a no-op request: the adapters produce no
    PatchPlan, and ``desired_content`` is the original file bytes
    unchanged. Callers must check ``plan is not None`` before applying.
    """

    plan: PatchPlan | None
    desired_content: bytes
    reason: str = ""

    def as_content_provider(self) -> Callable[[PatchOperation], bytes | None]:
        """Return a content provider that yields the desired bytes."""
        return lambda op: self.desired_content


# ---------------------------------------------------------------------------
# Line-preserving targeted editor
# ---------------------------------------------------------------------------


@dataclass
class _Entry:
    """A ``key=value`` entry spanning lines [start, end)."""

    key: str
    start: int
    end: int  # exclusive
    balanced: bool = True  # False if a multi-line value never closes


@dataclass
class _SectionSpan:
    """Line span of one ``[section]`` and its ``key=value`` entries."""

    name: str | None  # None = top-level (before any header)
    header: int | None  # line index of the "[name]" header line
    entries: list[_Entry] = field(default_factory=list)
    body_end: int = 0  # first line index after the section body


def _bracket_delta(text: str) -> int:
    """Net open-bracket count of *text* (``{``/``[`` minus ``}``/``]``)."""
    delta = 0
    for ch in text:
        if ch in "{[":
            delta += 1
        elif ch in "}]":
            delta -= 1
    return delta


def _index_lines(lines: list[str]) -> list[_SectionSpan]:
    """Index *lines* (splitlines keepends) into section spans.

    Structure detection mirrors the scan parser: comments (``;``/``#``)
    and blank lines are skipped, ``[name]`` starts a section, and a value
    starting with ``{`` or ``[`` continues across lines until the bracket
    depth returns to zero.
    """
    spans: list[_SectionSpan] = []
    current = _SectionSpan(None, None)
    n = len(lines)
    i = 0
    while i < n:
        stripped = lines[i].strip()
        if not stripped or stripped.startswith((";", "#")):
            i += 1
            continue
        if stripped.startswith("[") and stripped.endswith("]") and "=" not in stripped:
            current.body_end = i
            spans.append(current)
            current = _SectionSpan(stripped[1:-1].strip(), i)
            i += 1
            continue
        if "=" in stripped:
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()
            start = i
            balanced = True
            i += 1
            if value[:1] in ("{", "["):
                depth = _bracket_delta(value)
                while depth > 0 and i < n:
                    depth += _bracket_delta(lines[i].strip())
                    i += 1
                if depth != 0:
                    balanced = False
            current.entries.append(_Entry(key, start, i, balanced))
            continue
        i += 1
    current.body_end = n
    spans.append(current)
    return spans


def _detect_newline(lines: list[str]) -> str:
    """Dominant line-ending style: CRLF if any line uses it, else LF."""
    for line in lines:
        if line.endswith("\r\n"):
            return "\r\n"
    return "\n"


def _emit_entry(key: str, value: str, newline: str, section: str | None) -> str:
    """Serialize one ``key=value`` entry (value may be multi-line)."""
    _validate_serialized_key(key, section)
    if "\r" in value:
        raise ValueError(f"value for key '{key}' must not contain carriage returns")
    body = value.replace("\n", newline)
    return f"{key}={body}{newline}"


def _apply_section_edits(
    original_text: str,
    section: str,
    *,
    replacements: dict[str, str],
    removals: list[str],
    insertions: list[tuple[str, str]],
) -> str:
    """Apply targeted edits to one section of *original_text*.

    Every line outside the targeted key spans is preserved byte-for-byte
    (including its original terminator). Inserted and replacement lines
    use the file's detected newline style. Raises AdapterError on
    duplicate section headers, duplicate keys in the targeted section,
    or an unterminated multi-line value in the targeted section.
    """
    lines = original_text.splitlines(keepends=True)
    newline = _detect_newline(lines)
    spans = _index_lines(lines)

    insert_keys = [k for k, _ in insertions]
    if len(insert_keys) != len(set(insert_keys)):
        raise AdapterError(f"duplicate insertion keys for [{section}]")
    if set(insert_keys) & set(replacements):
        raise AdapterError(f"keys both replaced and inserted in [{section}]")

    targets = [s for s in spans if s.name == section]
    if len(targets) > 1:
        raise AdapterError(
            f"duplicate [{section}] section headers; refusing to edit ambiguous file"
        )

    if not targets:
        # Section absent: only insertions are possible; append a new
        # section at the end of the file.
        if replacements or removals:
            missing = sorted(set(replacements) | set(removals))
            raise AdapterError(f"section [{section}] not present; cannot modify keys: {missing}")
        if not insertions:
            return original_text
        block_lines = [f"[{section}]{newline}", newline]
        for key, value in sorted(insertions):
            block_lines.append(_emit_entry(key, value, newline, section))
        out = original_text
        if out and not out.endswith(("\n", "\r")):
            out += newline  # minimum required to start the new section
        if out and not out.endswith(newline + newline):
            out += newline  # blank line separating the new section
        return out + "".join(block_lines)

    target = targets[0]
    keys = [e.key for e in target.entries]
    if len(keys) != len(set(keys)):
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        raise AdapterError(
            f"duplicate keys in [{section}]: {dupes}; refusing to edit ambiguous file"
        )
    for entry in target.entries:
        if not entry.balanced:
            raise AdapterError(f"unterminated multi-line value for '{entry.key}' in [{section}]")

    by_key = {e.key: e for e in target.entries}
    for key in insert_keys:
        if key in by_key and key not in removals:
            raise AdapterError(f"key '{key}' already present in [{section}]; cannot insert")
    for key in removals:
        if key not in by_key:
            raise AdapterError(f"key '{key}' not present in [{section}]; cannot remove")
    for key in replacements:
        if key not in by_key:
            raise AdapterError(f"key '{key}' not present in [{section}]; cannot replace")

    new_lines = list(lines)
    # Replace/remove in reverse document order so spans stay valid.
    edits: list[tuple[int, int, list[str]]] = []
    for key in removals:
        e = by_key[key]
        edits.append((e.start, e.end, []))
    for key, value in replacements.items():
        e = by_key[key]
        edits.append((e.start, e.end, [_emit_entry(key, value, newline, section)]))
    for start, end, repl in sorted(edits, key=lambda t: t[0], reverse=True):
        new_lines[start:end] = repl

    if insertions:
        # Insert after the last remaining entry of the section, or right
        # after the header line when the section has no entries.
        anchor = target.header
        assert anchor is not None
        last_end = anchor + 1
        for e in target.entries:
            if e.key not in removals:
                last_end = max(last_end, e.end)
        # Edits before the insertion point shift its index in new_lines:
        # removals drop lines, replacements may change the line count.
        shift = 0
        for k in removals:
            if by_key[k].start < last_end:
                shift -= by_key[k].end - by_key[k].start
        for k, value in replacements.items():
            if by_key[k].start < last_end:
                old_len = by_key[k].end - by_key[k].start
                new_len = len(_emit_entry(k, value, newline, section).splitlines())
                shift += new_len - old_len
        position = last_end + shift
        block = [_emit_entry(key, value, newline, section) for key, value in sorted(insertions)]
        new_lines[position:position] = block

    return "".join(new_lines)


# ---------------------------------------------------------------------------
# Plan construction
# ---------------------------------------------------------------------------


def _preflight(root: Path) -> ProjectSettings:
    """Shared read-only preflight for all adapters."""
    root = root.resolve()
    pgodot = root / "project.godot"
    from godotforge_core.scan.profile import ProfileError

    if not pgodot.is_file():
        raise ProfileError(f"missing project.godot under {root}")
    if pgodot.is_symlink():
        raise ProfileError(f"project.godot is a symbolic link: {pgodot}")
    try:
        resolved = pgodot.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ProfileError(f"project.godot resolves outside the project root: {exc}") from exc

    current = parse_project_settings(root)
    if current.name is None:
        raise ProfileError("malformed project configuration: [application] config/name missing")
    return current


def _plan_from_edits(
    root: Path,
    *,
    section: str,
    replacements: dict[str, str],
    removals: list[str],
    insertions: list[tuple[str, str]],
    reason: str,
    suffix: str,
) -> ProjectGodotPatch:
    """Build a ProjectGodotPatch from targeted edits to one section.

    A request with no effective changes produces no PatchPlan: the
    returned patch has ``plan is None`` and ``desired_content`` equal to
    the original file bytes.
    """
    root = root.resolve()
    pgodot = root / "project.godot"
    original_bytes = pgodot.read_bytes()

    if not (replacements or removals or insertions):
        return ProjectGodotPatch(plan=None, desired_content=original_bytes, reason=reason)

    original_text = original_bytes.decode("utf-8")
    desired_text = _apply_section_edits(
        original_text,
        section,
        replacements=replacements,
        removals=removals,
        insertions=insertions,
    )
    desired_bytes = desired_text.encode("utf-8")

    current_hash = hashlib.sha256(original_bytes).hexdigest()
    desired_hash = hashlib.sha256(desired_bytes).hexdigest()

    op = PatchOperation(
        kind=OperationKind.UPDATE,
        path="project.godot",
        expected_hash=current_hash,
        desired_hash=desired_hash,
        owner="godotforge",
        source="project_godot_plan",
        reason=reason,
    )
    plan_id = _make_plan_id(suffix)
    _validate_plan_id(plan_id)
    plan = PatchPlan(id=plan_id, operations=(op,))
    return ProjectGodotPatch(plan=plan, desired_content=desired_bytes, reason=reason)


# ---------------------------------------------------------------------------
# Public adapters
# ---------------------------------------------------------------------------


def plan_update_autoloads(
    root: Path,
    *,
    add: list[tuple[str, str]] | None = None,
    remove: list[str] | None = None,
    set_singleton: list[tuple[str, bool]] | None = None,
    reason: str = "update autoloads",
) -> ProjectGodotPatch:
    """Produce a patch that adds/removes/toggles autoload singletons.

    *add*: list of (name, res_path) — path must start with ``res://``.
        New autoloads are written as singletons (``Name="*res://..."``).
        Names must match ``^[A-Za-z_][A-Za-z0-9_]{0,127}$``.
    *remove*: list of autoload names to remove.
    *set_singleton*: list of (name, singleton) to set the singleton flag.
    Only the targeted lines of ``[autoload]`` change; every other byte of
    the file is preserved. A request with no changes produces no plan.
    """
    root = Path(root)
    current = _preflight(root)
    by_name = {a.name: a for a in current.autoloads}

    removals: list[str] = []
    replacements: dict[str, str] = {}
    insertions: list[tuple[str, str]] = []

    if remove:
        for name in remove:
            if name not in by_name:
                raise ValueError(f"autoload '{name}' not present; cannot remove")
            removals.append(name)

    if add:
        for name, path in add:
            _validate_autoload_name(name)
            if name in by_name:
                raise ValueError(f"autoload '{name}' already present; cannot add")
            _validate_relative_path(path, f"autoload path for '{name}'")
            if not path.startswith("res://"):
                raise ValueError(f"autoload path must start with 'res://': '{path}'")
            insertions.append((name, f'"*{path}"'))

    inserted_paths = {n: p for n, p in add} if add else {}

    if set_singleton:
        for name, singleton in set_singleton:
            if name in inserted_paths:
                # Newly added autoload: adjust the insertion value instead
                # of emitting a replacement.
                if not singleton:
                    path = inserted_paths[name]
                    insertions = [(n, f'"{path}"' if n == name else v) for n, v in insertions]
                continue
            if name not in by_name:
                raise ValueError(f"autoload '{name}' not present; cannot set singleton")
            if name in removals:
                raise ValueError(f"autoload '{name}' is being removed; cannot set singleton")
            a = by_name[name]
            if a.singleton == singleton:
                continue  # already in the desired state; no edit needed
            replacements[name] = f'"*{a.path}"' if singleton else f'"{a.path}"'

    suffix = "autoload"
    if add:
        suffix += "+" + "+".join(n for n, _ in add)
    if remove:
        suffix += "-" + "-".join(remove)
    if set_singleton:
        suffix += "~" + "~".join(f"{n}:{s}" for n, s in set_singleton)

    return _plan_from_edits(
        root,
        section="autoload",
        replacements=replacements,
        removals=removals,
        insertions=insertions,
        reason=reason,
        suffix=suffix,
    )


def plan_update_input_actions(
    root: Path,
    *,
    add: list[tuple[str, str]] | None = None,
    remove: list[str] | None = None,
    clear: bool = False,
    reason: str = "update input actions",
) -> ProjectGodotPatch:
    """Produce a patch that adds/removes input actions.

    *add*: list of (name, raw_value) — raw_value is the full Godot
        input-action dict literal (e.g. ``{\n"deadzone": 0.5,\n...}\n``).
        The literal is an *opaque validated fragment*: it is checked by
        ``_validate_input_event_literal`` and then inserted verbatim.
        See ``docs/contracts/project-settings-adapter.md`` for the
        contract. Action names must match
        ``^[A-Za-z0-9_][A-Za-z0-9_./-]{0,127}$``.
    *remove*: list of action names to remove.
    *clear*: remove all existing input actions (used with *add* to
        replace).
    Only the targeted entries of ``[input]`` change; every other byte of
    the file is preserved. A request with no changes produces no plan.
    """
    root = Path(root)
    current = _preflight(root)
    by_name = {a.name: a for a in current.input_actions}

    removals: list[str] = []
    insertions: list[tuple[str, str]] = []

    if clear:
        removals.extend(sorted(by_name))

    if remove:
        for name in remove:
            if name not in by_name:
                raise ValueError(f"input action '{name}' not present; cannot remove")
            if name not in removals:
                removals.append(name)

    if add:
        for name, raw_value in add:
            _validate_input_action_name(name)
            _validate_input_event_literal(raw_value, name)
            if name in by_name and name not in removals:
                raise ValueError(f"input action '{name}' already present; cannot add")
            insertions.append((name, raw_value.strip()))

    suffix = "input"
    if clear:
        suffix += "-all"
    if add:
        suffix += "+" + "+".join(n for n, _ in add)
    if remove:
        suffix += "-" + "-".join(remove)

    return _plan_from_edits(
        root,
        section="input",
        replacements={},
        removals=removals,
        insertions=insertions,
        reason=reason,
        suffix=suffix,
    )


def plan_update_physics_layer_names(
    root: Path,
    *,
    set: dict[str, str] | None = None,
    remove: list[str] | None = None,
    clear: bool = False,
    reason: str = "update physics layer names",
) -> ProjectGodotPatch:
    """Produce a patch that sets/removes physics layer names.

    *set*: dict of layer_key → display_name (e.g.
        ``{"2d_physics/layer_1": "World"}``).
    *remove*: list of layer keys to remove.
    *clear*: remove all layer names (used with *set* to replace).
    Only the targeted entries of ``[layer_names]`` change; every other
    byte of the file is preserved. A request with no changes produces no
    plan.
    """
    root = Path(root)
    current = _preflight(root)
    existing = dict(current.physics_layer_names)

    removals: list[str] = []
    replacements: dict[str, str] = {}
    insertions: list[tuple[str, str]] = []

    if clear:
        removals.extend(sorted(existing))

    if remove:
        for key in remove:
            if key not in existing:
                raise ValueError(f"layer '{key}' not present; cannot remove")
            if key not in removals:
                removals.append(key)

    if set:
        for key, value in set.items():
            _validate_relative_path(key, f"layer key '{key}'")
            if not value:
                raise ValueError(f"layer value for '{key}' must be non-empty")
            if "\r" in value or "\n" in value:
                raise ValueError(f"layer value for '{key}' must not contain newlines")
            if key in existing and key not in removals:
                replacements[key] = f'"{value}"'
            else:
                insertions.append((key, f'"{value}"'))

    suffix = "layers"
    if clear:
        suffix += "-all"
    if set:
        suffix += "+" + "+".join(f"{k}={v}" for k, v in sorted(set.items()))
    if remove:
        suffix += "-" + "-".join(remove)

    return _plan_from_edits(
        root,
        section="layer_names",
        replacements=replacements,
        removals=removals,
        insertions=insertions,
        reason=reason,
        suffix=suffix,
    )


def plan_update_renderer_settings(
    root: Path,
    *,
    set: dict[str, str] | None = None,
    remove: list[str] | None = None,
    clear: bool = False,
    reason: str = "update renderer settings",
) -> ProjectGodotPatch:
    """Produce a patch that sets/removes renderer settings.

    *set*: dict of render_key → value (e.g.
        ``{"renderer/rendering_method": "gl_compatibility"}``).
    *remove*: list of render keys to remove.
    *clear*: remove all renderer settings (used with *set* to replace).
    Only the targeted entries of ``[rendering]`` change; every other byte
    of the file is preserved. A request with no changes produces no plan.
    """
    root = Path(root)
    current = _preflight(root)
    existing = dict(current.renderer_settings)

    removals: list[str] = []
    replacements: dict[str, str] = {}
    insertions: list[tuple[str, str]] = []

    if clear:
        removals.extend(sorted(existing))

    if remove:
        for key in remove:
            if key not in existing:
                raise ValueError(f"renderer setting '{key}' not present; cannot remove")
            if key not in removals:
                removals.append(key)

    if set:
        for key, value in set.items():
            _validate_relative_path(key, f"renderer key '{key}'")
            if not value:
                raise ValueError(f"renderer value for '{key}' must be non-empty")
            if "\r" in value or "\n" in value:
                raise ValueError(f"renderer value for '{key}' must not contain newlines")
            if key in existing and key not in removals:
                replacements[key] = f'"{value}"'
            else:
                insertions.append((key, f'"{value}"'))

    suffix = "render"
    if clear:
        suffix += "-all"
    if set:
        suffix += "+" + "+".join(f"{k}={v}" for k, v in sorted(set.items()))
    if remove:
        suffix += "-" + "-".join(remove)

    return _plan_from_edits(
        root,
        section="rendering",
        replacements=replacements,
        removals=removals,
        insertions=insertions,
        reason=reason,
        suffix=suffix,
    )
