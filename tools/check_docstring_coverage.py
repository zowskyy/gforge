"""Production docstring coverage checker — 100% required for release.

Scope: packages/**/src/**/*.py + src/**/*.py (62 modules).
Counts: modules, classes, functions/methods (including private helpers),
CLI command groups/handlers. Private helpers are required; dunder __*__ and
nested closures inside functions are excluded.

Exclusions:
  tests/**, packages/**/tests/**, test_*.py, *_test.py,
  tools/** (self-exclude), scripts/**, docs/**, examples/**,
  .pytest-tmp/**, .godot/**, build/**, builds/**, __pycache__/**, .git/**,
  *.generated.py, generated/**.
  __init__.py module docstring: excluded if file ≤5 lines and has no public symbols
  (treated as re-export shim — not a violation).

No network, no LLM, deterministic.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

INCLUDE_GLOBS = [
    "packages/**/src/**/*.py",
    "src/**/*.py",
]

EXCLUDE_PATTERNS = [
    "tests",
    "tools",
    "scripts",
    "docs",
    "examples",
    ".pytest-tmp",
    ".godot",
    "build",
    "builds",
    "__pycache__",
    ".git",
]

EXCLUDE_SUFFIXES = (".pyc",)
GENERATED_MARKERS = (".generated.",)


def is_excluded(path: pathlib.Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    for excl in EXCLUDE_PATTERNS:
        if rel == excl or rel.startswith(excl + "/") or f"/{excl}/" in rel:
            return True
    if rel.startswith("tests/") or "/tests/" in rel:
        return True
    if path.name.startswith("test_") or path.name.endswith("_test.py"):
        return True
    if GENERATED_MARKERS[0] in path.name:
        return True
    for suf in EXCLUDE_SUFFIXES:
        if path.name.endswith(suf):
            return True
    return False


def discover_files() -> list[pathlib.Path]:
    files: set[pathlib.Path] = set()
    for pattern in INCLUDE_GLOBS:
        for p in ROOT.glob(pattern):
            if p.is_file() and p.suffix == ".py" and not is_excluded(p):
                files.add(p.resolve())
    return sorted(files)


def has_docstring(node: ast.AST) -> bool:
    return ast.get_docstring(node) is not None


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def inspect_file(path: pathlib.Path) -> tuple[list[str], list[str]]:
    """Return (missing, details) for path; missing entries are human-readable."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno} SyntaxError {exc.msg}"], []

    rel = path.relative_to(ROOT).as_posix()
    missing: list[str] = []

    # Module docstring
    is_init_shim = path.name == "__init__.py"
    if is_init_shim:
        # Exclude re-export shims: ≤5 lines and no public Class/Function beyond imports
        lines = source.strip().splitlines()
        # count non-empty, non-comment lines
        code_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
        has_public = any(
            isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")
            for n in tree.body
        )
        if len(code_lines) <= 5 and not has_public:
            pass  # excluded
        elif not has_docstring(tree):
            missing.append(f"{rel}:1 module docstring")
    else:
        if not has_docstring(tree):
            missing.append(f"{rel}:1 module docstring")

    # Collect classes and functions at module and class scope
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if is_dunder(node.name):
                continue
            if not has_docstring(node):
                missing.append(f"{rel}:{node.lineno} class {node.name}")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if is_dunder(item.name):
                        continue
                    # include private helpers per expanded scope
                    if not has_docstring(item):
                        missing.append(f"{rel}:{item.lineno} method {node.name}.{item.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if is_dunder(node.name):
                continue
            if not has_docstring(node):
                missing.append(f"{rel}:{node.lineno} function {node.name}")

    return missing, []


def main() -> None:
    parser = argparse.ArgumentParser(description="Check production docstring coverage")
    parser.add_argument(
        "--minimum", type=float, default=100.0, help="Minimum coverage percent required"
    )  # noqa: E501
    parser.add_argument("--verbose", action="store_true", help="List missing symbols")
    parser.add_argument(
        "--list-missing", action="store_true", help="List missing (alias for --verbose)"
    )  # noqa: E501
    args = parser.parse_args()

    files = discover_files()
    total_expected = 0
    missing_all: list[str] = []

    # First pass: count expected total as discovered symbols
    for path in files:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        rel = path.relative_to(ROOT).as_posix()
        is_init_shim = path.name == "__init__.py"
        # module
        if is_init_shim:
            lines = source.strip().splitlines()
            code_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
            has_public = any(
                isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and not n.name.startswith("_")
                for n in tree.body
            )
            if not (len(code_lines) <= 5 and not has_public):
                total_expected += 1
                if not has_docstring(tree):
                    missing_all.append(f"{rel}:1 module docstring")
            # else excluded shim not counted
        else:
            total_expected += 1
            if not has_docstring(tree):
                missing_all.append(f"{rel}:1 module docstring")
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if is_dunder(node.name):
                    continue
                total_expected += 1
                if not has_docstring(node):
                    missing_all.append(f"{rel}:{node.lineno} class {node.name}")
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if is_dunder(item.name):
                            continue
                        total_expected += 1
                        if not has_docstring(item):
                            missing_all.append(
                                f"{rel}:{item.lineno} method {node.name}.{item.name}"
                            )  # noqa: E501
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if is_dunder(node.name):
                    continue
                total_expected += 1
                if not has_docstring(node):
                    missing_all.append(f"{rel}:{node.lineno} function {node.name}")

    covered = total_expected - len(missing_all)
    pct = (covered / total_expected * 100) if total_expected else 100.0

    print(f"Docstring coverage: {covered}/{total_expected} ({pct:.1f}%)")
    print(f"Files scanned: {len(files)}")
    if missing_all:
        print(f"Missing: {len(missing_all)} symbols")
        if args.verbose or args.list_missing:
            for m in sorted(missing_all):
                print(f"  {m}")
    else:
        print("All production symbols documented.")

    if pct < args.minimum - 1e-9:
        print(f"FAIL: coverage {pct:.1f}% below minimum {args.minimum:.1f}%")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
