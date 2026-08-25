"""Deterministic UID generation for Godot resources.

No randomness, timestamps, machine paths, or environment values are used.
Only template_id, schema_version, and relative_posix feed the digest.

No AI, network, or telemetry dependency.
"""

from __future__ import annotations

import hashlib

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_UID_RE = __import__("re").compile(r"^uid://[a-z0-9]{13}$")


def _base36_encode(num: int) -> str:
    """Encode non-negative int as base36 (0-9a-z), lower-case, no leading zeros unless zero."""
    if num == 0:
        return "0"
    out = []
    while num > 0:
        num, rem = divmod(num, 36)
        out.append(_ALPHABET[rem])
    return "".join(reversed(out))


def deterministic_uid(template_id: str, schema_version: int, relative_posix: str) -> str:
    """Return deterministic ``uid://`` for ``relative_posix`` under ``template_id``.

    Inputs are validated for non-emptiness and slash form; digest is
    ``sha256(f"{template_id}:{schema_version}:{relative_posix}")``.
    Suffix is 13-char lower-case a-z0-9, proven accepted by Godot 4.7 parser
    via the required import test gate (see docs/contracts/creator-manifest.md).
    """
    if not template_id or not relative_posix:
        raise ValueError("template_id and relative_posix must be non-empty")
    if schema_version < 1:
        raise ValueError("schema_version must be >=1")
    if "\x00" in template_id or "\x00" in relative_posix:
        raise ValueError("inputs must not contain null bytes")
    raw = f"{template_id}:{schema_version}:{relative_posix}".encode()
    digest = hashlib.sha256(raw).hexdigest()
    # Interpret hex as int then base36
    num = int(digest, 16)
    b36 = _base36_encode(num).lower()
    # Pad/truncate to exactly 13 chars deterministically
    if len(b36) < 13:
        b36 = b36.rjust(13, "0")
    suffix = b36[:13]
    uid = f"uid://{suffix}"
    # Validate format defensively
    assert _UID_RE.match(uid), f"generated uid does not match pattern: {uid}"
    return uid


def is_valid_uid(value: str) -> bool:
    """Return whether *value* matches the 13-char lower-case UID pattern."""
    return bool(_UID_RE.match(value))
