"""Behavior registry — allowlisted, versioned, pinned hashes, deterministic."""

from __future__ import annotations

import hashlib
import importlib.resources
from pathlib import Path

BEHAVIOR_VERSION = 1

_ALLOWLIST: dict[str, str] = {
    "platformer_controller": "platformer_controller.gd",
    "collectible": "collectible.gd",
}

PINNED_HASHES: dict[str, str] = {
    "platformer_controller": "59449f62b5371e7c255583f2932a75e88ebc91531c1986113c518c824ae9ee0e",
    "collectible": "c80b9f8d4463739bb9db90b0d5caf4b05ff34db22b84a625774da63a0b6b8f16",
}


def allowed_behavior_ids() -> tuple[str, ...]:
    """Return sorted tuple of allowlisted behavior IDs."""
    return tuple(sorted(_ALLOWLIST.keys()))


def behavior_version() -> int:
    """Return stable behavior version."""
    return BEHAVIOR_VERSION


def pinned_hash(behavior_id: str) -> str:
    """Return pinned SHA-256 for behavior ID.

    Raises ValueError for unknown IDs.
    """
    if behavior_id not in PINNED_HASHES:
        raise ValueError(f"unknown behavior ID {behavior_id!r}")
    return PINNED_HASHES[behavior_id]


def _resource_path(behavior_id: str) -> Path:
    """Return package resource path for behavior ID, validating allowlist."""
    if behavior_id not in _ALLOWLIST:
        raise ValueError(f"unknown behavior ID {behavior_id!r}")
    filename = _ALLOWLIST[behavior_id]
    # Explicit package resources path per corrected contract
    pkg = importlib.resources.files("godotforge_core.behaviors.resources").joinpath(filename)
    # For wheel/sdist, use as_file to get real path
    import importlib.resources as res

    try:
        # Try direct check if traversable
        if hasattr(pkg, "is_file"):
            # pkg is Traversable, check via as_file
            with res.as_file(pkg) as p:
                if Path(p).is_file():
                    return Path(p)
        # Fallback for source checkout
        candidate = Path(__file__).with_name("resources") / filename
        if candidate.is_file():
            return candidate
    except Exception:
        pass
    # Return traversable as Path fallback (for reading via read_bytes)
    # Use importlib.resources path as string fallback
    return Path(str(pkg))


def load_behavior(behavior_id: str) -> bytes:
    """Load behavior GDScript bytes for allowlisted ID, verifying pinned hash.

    Raises FileNotFoundError if resource missing, ValueError if hash mismatch or unknown ID.
    """
    if behavior_id not in _ALLOWLIST:
        raise ValueError(f"unknown behavior ID {behavior_id!r}")
    filename = _ALLOWLIST[behavior_id]
    expected = PINNED_HASHES[behavior_id]
    pkg = importlib.resources.files("godotforge_core.behaviors.resources").joinpath(filename)
    import importlib.resources as res

    data: bytes
    try:
        # Handle both source and wheel via as_file or read_bytes directly
        if hasattr(pkg, "read_bytes"):
            data = pkg.read_bytes()  # type: ignore[attr-defined]
        else:
            with res.as_file(pkg) as p:
                data = Path(p).read_bytes()
    except FileNotFoundError:
        raise FileNotFoundError(f"behavior resource missing: {behavior_id} ({filename})") from None
    except Exception as exc:
        raise FileNotFoundError(f"behavior resource missing: {behavior_id}: {exc}") from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"behavior hash mismatch for {behavior_id!r}: expected {expected}, got {actual}")  # noqa: E501
    return data


def is_allowlisted(behavior_id: str) -> bool:
    """Return whether behavior ID is allowlisted."""
    return behavior_id in _ALLOWLIST
