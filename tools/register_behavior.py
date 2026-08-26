"""Register a new pinned-hash behavior — replaces the hand-`sha256sum`-and-
paste workflow that caused a real, silent, test-suite-breaking bug (the
original 3 PINNED_HASHES entries were simply transcribed wrong on HEAD,
undetected until 2026-08-26; see PROJECT_TRACKING.md's "District Kings 3D
Template" section).

Usage:
    python tools/register_behavior.py <source.gd> <behavior_id> [--force]

- <source.gd>: path to the GDScript file to register. If it isn't already
  inside behaviors/resources/, it is copied there.
- <behavior_id>: the registry id (e.g. "player_controller_3d" or
  "external/world_generator/map_generator"). The destination filename is
  always "<behavior_id>.gd", matching every existing entry's convention.
- --force: required to re-register an id that already exists with
  *different* bytes (a deliberate content update — bumps nothing
  automatically; the behavior-library.md contract says to bump
  BEHAVIOR_VERSION and document it by hand when this happens).

After editing registry.py, re-imports it fresh and calls load_behavior() to
verify the new entry actually works before declaring success — on any
verification failure, the edit is rolled back and the script exits non-zero.
No network, no LLM, deterministic.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCES_ROOT = (
    ROOT / "packages" / "godotforge-core" / "src" / "godotforge_core" / "behaviors" / "resources"
)
REGISTRY_PATH = (
    ROOT / "packages" / "godotforge-core" / "src" / "godotforge_core" / "behaviors" / "registry.py"
)


def _find_dict_block(lines: list[str], dict_header: str) -> tuple[int, int]:
    """Return (start, end) line indices of the dict literal whose opening
    line is exactly dict_header: start is the header line, end is the
    line index of its closing '}'. Raises ValueError if not found."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == dict_header:
            start = i
            break
    if start is None:
        raise ValueError(f"could not find dict header: {dict_header!r}")
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == "}":
            return start, j
    raise ValueError(f"could not find closing brace for: {dict_header!r}")


def _insert_dict_entry(lines: list[str], dict_header: str, entry_line: str) -> list[str]:
    """Insert entry_line just before the closing '}' of the dict literal
    whose opening line is exactly dict_header."""
    _start, end = _find_dict_block(lines, dict_header)
    new_lines = list(lines)
    new_lines.insert(end, entry_line)
    return new_lines


def _existing_pinned_hash(lines: list[str], behavior_id: str) -> str | None:
    """Return the currently-pinned hash for behavior_id from *within the
    PINNED_HASHES dict specifically* — never search the whole file text,
    since _ALLOWLIST has a same-shaped '"<id>": "<filename>"' line for the
    same id, and a naive whole-file search can match that instead (a real
    bug found and fixed while building this tool: it once extracted a
    filename as if it were a hash)."""
    start, end = _find_dict_block(lines, "PINNED_HASHES: dict[str, str] = {")
    marker = f'"{behavior_id}": "'
    for i in range(start + 1, end):
        line = lines[i]
        idx = line.find(marker)
        if idx == -1:
            continue
        value_start = idx + len(marker)
        value_end = line.find('"', value_start)
        return line[value_start:value_end]
    return None


def register(source: Path, behavior_id: str, *, force: bool) -> int:
    if not source.is_file():
        print(f"error: source file not found: {source}", file=sys.stderr)
        return 1
    if source.suffix != ".gd":
        print(f"error: source must be a .gd file, got: {source}", file=sys.stderr)
        return 1

    dest_rel = f"{behavior_id}.gd"
    dest = RESOURCES_ROOT / dest_rel

    if dest.resolve() != source.resolve():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        print(f"copied {source} -> {dest}")
    else:
        print(f"source is already in place: {dest}")

    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    print(f"sha256: {digest}")

    original_text = REGISTRY_PATH.read_text(encoding="utf-8")
    lines = original_text.splitlines(keepends=True)
    existing_hash = _existing_pinned_hash(lines, behavior_id)

    if existing_hash is not None:
        if existing_hash == digest:
            print(f"'{behavior_id}' is already registered with this exact hash — nothing to do.")
            return 0
        if not force:
            print(
                f"error: '{behavior_id}' is already registered with a DIFFERENT hash "
                f"({existing_hash}) than the new content ({digest}). This is a content "
                f"change, not a new registration — per docs/contracts/behavior-library.md, "
                f"bump BEHAVIOR_VERSION and document the change explicitly. Re-run with "
                f"--force only once you've done that and intend to overwrite the pin.",
                file=sys.stderr,
            )
            return 1
        # --force: replace the existing hash line in place, within the
        # PINNED_HASHES block specifically (never a whole-file string
        # replace — that's exactly what caused the bug this comment is
        # warning about further up in this file).
        p_start, p_end = _find_dict_block(lines, "PINNED_HASHES: dict[str, str] = {")
        marker = f'"{behavior_id}": "{existing_hash}"'
        replaced = False
        for i in range(p_start + 1, p_end):
            if marker in lines[i]:
                lines[i] = lines[i].replace(marker, f'"{behavior_id}": "{digest}"')
                replaced = True
                break
        if not replaced:
            print(f"error: could not locate the line to update for '{behavior_id}'", file=sys.stderr)
            return 1
        REGISTRY_PATH.write_text("".join(lines), encoding="utf-8")
        print(f"updated pinned hash for '{behavior_id}' (--force).")
    else:
        try:
            lines = _insert_dict_entry(
                lines, "_ALLOWLIST: dict[str, str] = {", f'    "{behavior_id}": "{dest_rel}",\n'
            )
            lines = _insert_dict_entry(
                lines, "PINNED_HASHES: dict[str, str] = {", f'    "{behavior_id}": "{digest}",\n'
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        REGISTRY_PATH.write_text("".join(lines), encoding="utf-8")
        print(f"registered '{behavior_id}' -> {dest_rel} in {REGISTRY_PATH}")

    # Verify: fresh-import the edited module and confirm the id actually
    # loads with matching bytes. Roll back on any failure — never leave the
    # repo in a broken state.
    try:
        import godotforge_core.behaviors.registry as registry_module

        importlib.reload(registry_module)
        loaded = registry_module.load_behavior(behavior_id)
        if hashlib.sha256(loaded).hexdigest() != digest:
            raise AssertionError("loaded bytes do not match computed digest")
    except Exception as exc:  # noqa: BLE001 - intentional broad catch for rollback safety
        print(f"error: verification failed after edit ({exc}); rolling back registry.py", file=sys.stderr)
        REGISTRY_PATH.write_text(original_text, encoding="utf-8")
        return 1

    print(f"verified: load_behavior({behavior_id!r}) succeeds with matching hash.")
    return 0


def verify_all() -> int:
    """Recompute every pinned hash from actual bytes on disk and report
    drift in both directions (wrong hash; allowlisted-but-missing-file;
    file-on-disk-but-unregistered). Same checks tests/unit/test_behaviors_registry.py
    enforces in CI — this is the interactive/manual equivalent."""
    import godotforge_core.behaviors.registry as registry_module

    importlib.reload(registry_module)
    problems: list[str] = []

    allowlist_ids = set(registry_module._ALLOWLIST)  # noqa: SLF001
    pinned_ids = set(registry_module.PINNED_HASHES)
    if allowlist_ids != pinned_ids:
        problems.append(
            f"_ALLOWLIST/PINNED_HASHES key drift: "
            f"allowlist-only={sorted(allowlist_ids - pinned_ids)} "
            f"pinned-only={sorted(pinned_ids - allowlist_ids)}"
        )

    for behavior_id in sorted(allowlist_ids):
        try:
            data = registry_module.load_behavior(behavior_id)
        except (FileNotFoundError, ValueError) as exc:
            problems.append(f"{behavior_id}: {exc}")
            continue
        actual = hashlib.sha256(data).hexdigest()
        pinned = registry_module.PINNED_HASHES[behavior_id]
        if actual != pinned:
            problems.append(f"{behavior_id}: pinned={pinned} actual={actual}")

    registered_filenames = {registry_module._ALLOWLIST[i] for i in allowlist_ids}  # noqa: SLF001
    on_disk = {p.relative_to(RESOURCES_ROOT).as_posix() for p in RESOURCES_ROOT.rglob("*.gd")}
    orphaned = on_disk - registered_filenames
    if orphaned:
        problems.append(f"unregistered .gd files on disk: {sorted(orphaned)}")

    if problems:
        print(f"FAILED — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK — {len(allowlist_ids)} behaviors verified, no drift.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", help="Path to the .gd source file")
    parser.add_argument("behavior_id", type=str, nargs="?", help="Registry id, e.g. player_controller_3d")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting an existing id's pinned hash with different content",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Ignore source/behavior_id; recompute and diff every pinned hash instead",
    )
    args = parser.parse_args()
    if args.verify:
        return verify_all()
    if args.source is None or args.behavior_id is None:
        parser.error("source and behavior_id are required unless --verify is given")
    return register(args.source, args.behavior_id, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
