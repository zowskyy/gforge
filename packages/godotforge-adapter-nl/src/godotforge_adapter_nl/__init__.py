"""godotforge-adapter-nl — optional natural-language candidate-manifest
adapter for Godot Forge Hub.

Deliberately outside the AI-free default package boundary (godotforge-core,
godotforge-cli — see docs/contracts/hub-v1.md §6). This package is the only
place in the whole workspace that shells out to an LLM; it is never
imported by godotforge-core or godotforge-cli (see
tests/unit/test_adapter_nl_import_boundary.py for the enforced check).

Full contract: docs/contracts/candidate-manifest-adapter.md.
"""

from __future__ import annotations

__version__ = "0.1.0"
