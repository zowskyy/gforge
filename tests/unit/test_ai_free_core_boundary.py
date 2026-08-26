"""AST-based enforcement of the no-AI-in-core boundary — mechanically
verifies what docs/contracts/hub-v1.md §6 and
docs/contracts/candidate-manifest-adapter.md's "hard boundary" both claim,
which turned out (discovered while building the Phase 1b adapter,
2026-08-26) to have no actual enforcing test anywhere in the repo despite
hub-v1.md §12 listing "AST/import, dependency, credential, and
runtime-adapter checks (§6)" as a required, passing acceptance test class.

Scope, stated honestly: this file checks import statements only — it does
NOT implement hub-v1.md §6's full spec (the credential-read AST scan, the
subprocess shell/tuple-args shape check, or the dynamic-import/
importlib.import_module runtime-adapter check). Those remain a real,
separate gap; this closes the part directly relevant to the Phase 1
natural-language adapter's own boundary guarantee.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_SCAN_ROOTS = (
    REPO_ROOT / "packages" / "godotforge-core" / "src" / "godotforge_core",
    REPO_ROOT / "src" / "godotforge_cli",
)

# The adapter package this specifically must never reach godotforge-core/-cli.
_FORBIDDEN_ADAPTER_MODULE = "godotforge_adapter_nl"

# A representative, not exhaustive, set of AI-SDK and generic-network-client
# top-level module names. engine/runner.py's subprocess usage is
# intentionally exempt (that's Godot process invocation, not network I/O;
# its shape is a separate, un-implemented §6 check — see module docstring).
_FORBIDDEN_TOP_LEVEL_MODULES = frozenset(
    {
        _FORBIDDEN_ADAPTER_MODULE,
        "openai",
        "anthropic",
        "cohere",
        "langchain",
        "transformers",
        "requests",
        "httpx",
        "aiohttp",
        "socket",
        "http",
        "urllib3",
    }
)


def _iter_py_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        assert root.is_dir(), f"expected scan root not found: {root}"
        files.extend(
            p
            for p in root.rglob("*.py")
            if "__pycache__" not in p.parts
        )
    return files


def _imported_top_level_modules(source: str, path: Path) -> set[str]:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - would indicate a real bug elsewhere
        raise AssertionError(f"failed to parse {path}: {exc}") from exc

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module.split(".")[0])
    return names


def test_no_forbidden_imports_in_core_or_cli() -> None:
    violations: list[str] = []
    for path in _iter_py_files():
        imported = _imported_top_level_modules(path.read_text(encoding="utf-8"), path)
        forbidden_hits = imported & _FORBIDDEN_TOP_LEVEL_MODULES
        if forbidden_hits:
            rel = path.relative_to(REPO_ROOT).as_posix()
            violations.append(f"{rel}: imports {sorted(forbidden_hits)}")

    assert not violations, (
        "godotforge_core/godotforge_cli must never import an AI SDK, a "
        "generic network-HTTP client, or the natural-language adapter "
        "package — this is the mechanical guarantee behind the no-AI-in-core "
        "invariant (docs/contracts/hub-v1.md §6), not just a documentation "
        "promise:\n  " + "\n  ".join(violations)
    )


def test_forbidden_module_list_is_exercised() -> None:
    """Sanity check on the test itself: confirm the detection logic actually
    fires on a deliberately-constructed violating snippet, so a future
    refactor of _imported_top_level_modules can't silently stop checking
    anything and still show a passing (vacuous) suite."""
    source = "import godotforge_adapter_nl\nfrom openai import OpenAI\n"
    found = _imported_top_level_modules(source, Path("<test>"))
    assert found & _FORBIDDEN_TOP_LEVEL_MODULES == {"godotforge_adapter_nl", "openai"}
