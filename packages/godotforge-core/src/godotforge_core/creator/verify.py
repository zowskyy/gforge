"""Creator verify — isolated Godot validation for generated projects.

Secure temporary copy, strict symlink rejection, validator injection,
process-safe cleanup, and source immutability. No AI/network/telemetry.
"""

from __future__ import annotations

import hashlib
import importlib.resources
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from godotforge_core.creator.manifest import validate_manifest_dict
from godotforge_core.creator.plan import _plan_id_for
from godotforge_core.engine.validate import ValidateMode, ValidationResult, validate_project

# Limits for secure copy — prevents resource exhaustion.
MAX_COPY_FILES = 4096
MAX_COPY_BYTES = 64 * 1024 * 1024  # 64 MiB

# Pruned during copy — never copied to temp.
PRUNED_DIRS = {".git", ".godot", ".pytest-tmp", "__pycache__", "build", "builds"}
PRUNED_PREFIXES = (".godotforge/cache", ".godotforge/reports", ".godotforge/backups")

# Pinned validator hash — must match package resource.
PINNED_VALIDATOR_SHA256 = "1e01c7a59baa856ebeb4a14d2f39d143640e2162f1fc31aee2d80df69cbd525c"


@dataclass(frozen=True)
class VerifyResult:
    """Result of isolated verification."""

    manifest: Any
    plan_id: str
    plan_hash: str | None
    validation: ValidationResult
    source_before_hash: str
    source_after_hash: str
    temp_removed: bool
    source_unchanged: bool


def _validator_source_path() -> Path:
    """Return package-owned validator path via importlib.resources.

    Raises FileNotFoundError if resource missing (packaging misconfiguration).
    """
    try:
        # importlib.resources.files is available on 3.12
        pkg = importlib.resources.files("godotforge_core.engine") / "validate_boot.gd"
        # files() returns Traversable; check existence via is_file()
        if hasattr(pkg, "is_file") and pkg.is_file():  # type: ignore[attr-defined]
            # For Traversable, read via open/read_text; but for path return, use as_file
            import importlib.resources as res

            # Use as_file to get actual Path when in wheel
            with res.as_file(pkg) as p:
                return Path(p)
        # Fallback: try direct filesystem path for source checkout
        # (editable install)
        candidate = Path(__file__).with_name("validate_boot.gd")
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"validator resource not found: {pkg}")
    except Exception as exc:
        raise FileNotFoundError(f"validator resource missing: {exc}") from exc


def _hash_source_files(root: Path) -> str:
    """Deterministic hash of source files (excluding pruned)."""
    root = root.resolve()
    files: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune
        dirnames[:] = [d for d in dirnames if d not in PRUNED_DIRS]
        # Skip pruned prefixes
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir != "." and any(rel_dir == p or rel_dir.startswith(p + "/") for p in PRUNED_PREFIXES):  # noqa: E501
            dirnames[:] = []
            continue
        for fn in sorted(filenames):
            fp = Path(dirpath) / fn
            rel = fp.relative_to(root).as_posix()
            if any(rel == p or rel.startswith(p + "/") for p in PRUNED_PREFIXES):
                continue
            if rel.startswith(".godot/"):
                continue
            # Do not follow symlinks for hashing
            if fp.is_symlink():
                continue
            try:
                files[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
            except OSError:
                files[rel] = "unreadable"
    import json

    canon = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _secure_copy(src: Path, dst: Path) -> None:
    """Copy src to dst with strict symlink rejection and size limits.

    Rejects symlink project root and every symlink encountered.
    Bounds file count and total bytes.
    Never follows symlinks (follow_symlinks=False).
    """
    # F-002: reject a symlinked root on the *unresolved* user-supplied path;
    # resolve() would silently dereference it and defeat this check.
    if src.is_symlink():
        raise ValueError(f"symlink project root rejected: {src}")
    src = src.resolve()
    dst = dst.resolve()
    total_files = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(src, topdown=True, followlinks=False):
        # Check each dir for symlink before descending
        for d in list(dirnames):
            dir_path = Path(dirpath) / d
            if dir_path.is_symlink():
                raise ValueError(f"nested symlink rejected: {dir_path.relative_to(src)}")
            # Prune ignored dirs
            if d in PRUNED_DIRS:
                dirnames.remove(d)
        # Prune prefixes
        rel_dir = Path(dirpath).relative_to(src).as_posix()
        if rel_dir != "." and any(rel_dir == p or rel_dir.startswith(p + "/") for p in PRUNED_PREFIXES):  # noqa: E501
            dirnames[:] = []
            continue
        # Ensure dest dir exists
        dest_dir = dst / Path(dirpath).relative_to(src)
        dest_dir.mkdir(parents=True, exist_ok=True)
        for fn in filenames:
            src_file = Path(dirpath) / fn
            rel = src_file.relative_to(src).as_posix()
            if any(rel == p or rel.startswith(p + "/") for p in PRUNED_PREFIXES):
                continue
            if rel.startswith(".godot/"):
                continue
            if src_file.is_symlink():
                raise ValueError(f"symlink file rejected: {rel}")
            # Size limits
            total_files += 1
            if total_files > MAX_COPY_FILES:
                raise ValueError(f"copy file count limit exceeded: {MAX_COPY_FILES}")
            try:
                size = src_file.stat().st_size
            except OSError as exc:
                raise ValueError(f"cannot stat {rel}: {exc}") from exc
            total_bytes += size
            if total_bytes > MAX_COPY_BYTES:
                raise ValueError(f"copy total size limit exceeded: {MAX_COPY_BYTES}")
            dest_file = dst / rel
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            # Copy without following symlinks, preserve bytes
            shutil.copy2(src_file, dest_file, follow_symlinks=False)


def _inject_validator(dst: Path) -> None:
    """Copy package validator into temp workspace at .godotforge/validate_boot.gd."""
    src_validator = _validator_source_path()
    data = src_validator.read_bytes()
    # Verify pinned hash
    actual = hashlib.sha256(data).hexdigest()
    if actual != PINNED_VALIDATOR_SHA256:
        raise ValueError(  # noqa: E501
            f"validator hash mismatch: expected {PINNED_VALIDATOR_SHA256}, got {actual}"
        )
    dest = dst / ".godotforge" / "validate_boot.gd"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def _sanitize_result(
    result: ValidationResult, src_root: Path, tmp_root: Path
) -> ValidationResult:
    """Sanitize absolute/temporary paths and bound raw output.

    - Relativize project_root
    - Redact tmp path in command/stderr/stdout
    - Ensure stdout/stderr already bounded by runner CaptureConfig (1MiB)
    """
    tmp_str = str(tmp_root)
    src_str = str(src_root.resolve())
    # Sanitize stages: replace tmp path with TEMP_REDACTED or src
    # We do minimal redaction: replace tmp_str with "<verify-temp>"
    # Keep diagnostics normalized, no env/secrets
    # For now, just ensure project_root is src (not tmp) for envelope
    # Actual sanitization of stdout/stderr is done via runner truncation; keep as is  # noqa: E501
    sanitized_stages = []
    for stage in result.stages:
        cmd = tuple(c.replace(tmp_str, "<verify-temp>") for c in stage.command)
        proc = stage.process
        stdout = proc.stdout.replace(tmp_str, "<verify-temp>").replace(src_str, "<project-root>")
        stderr = proc.stderr.replace(tmp_str, "<verify-temp>").replace(src_str, "<project-root>")
        # Rebuild ProcessResult with sanitized strings (frozen dataclass, need new)
        from godotforge_core.engine.runner import ProcessResult

        new_proc = ProcessResult(
            executable=proc.executable.replace(tmp_str, "<verify-temp>"),
            args=tuple(a.replace(tmp_str, "<verify-temp>") for a in proc.args),
            exit_code=proc.exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=proc.duration_ms,
            timed_out=proc.timed_out,
            launch_error=proc.launch_error,
            stdout_truncated=proc.stdout_truncated,
            stderr_truncated=proc.stderr_truncated,
        )
        from godotforge_core.engine.validate import StageResult

        sanitized_stages.append(
            StageResult(
                stage=stage.stage,
                command=cmd,
                process=new_proc,
                status=stage.status,
                fatal_diagnostics=stage.fatal_diagnostics,
                ignored_diagnostics=stage.ignored_diagnostics,
            )
        )
    from godotforge_core.engine.validate import ValidationResult

    return ValidationResult(
        project_root=str(src_root.resolve()),
        engine=result.engine,
        mode=result.mode,
        stages=tuple(sanitized_stages),
        status=result.status,
        wall_duration_ms=result.wall_duration_ms,
        graph=result.graph,
    )


def verify_creator_project(
    src_root: str | Path,
    manifest_dict: dict,
    *,
    engine_path: str | Path | None = None,
    timeout: float = 60.0,
    mode: str = "full",
) -> VerifyResult:
    """Verify creator project in isolated temporary copy.

    Steps:
      1. Validate manifest (canonical planId, planHash null)
      2. Hash source before
      3. Secure copy to temp (strict symlink reject, size bounds, pruned)
      4. Inject validator
      5. Run validate_project in temp (process-safe, bounded)
      6. Sanitize result
      7. Ensure temp removed even on failure/timeout

    Returns VerifyResult with source_unchanged flag.
    """
    # F-002: check the user-supplied path for a symlink *before* resolve();
    # resolve() dereferences symlinks and would silently accept a linked root.
    src_root = Path(src_root)
    if src_root.is_symlink():
        raise ValueError(f"symlink project root rejected: {src_root}")
    src_root = src_root.resolve()
    manifest = validate_manifest_dict(manifest_dict)
    # planId manifest-derived, planHash null for verify per contract

    plan_id = _plan_id_for(manifest)
    plan_hash: str | None = None

    before = _hash_source_files(src_root)
    tmp = Path(tempfile.mkdtemp(prefix="gdvf-verify-"))
    temp_removed = False
    validation: ValidationResult | None = None
    try:
        _secure_copy(src_root, tmp)
        _inject_validator(tmp)
        # Run validation in temp
        # Use ValidateMode enum conversion
        validation = validate_project(
            tmp,
            mode=ValidateMode(mode) if isinstance(mode, str) else mode,
            engine_path=engine_path,
            timeout=timeout,
        )
        sanitized = _sanitize_result(validation, src_root, tmp)
        validation = sanitized
    finally:
        # Process-safe cleanup: validate_project's run_process already did terminate/wait/kill
        # Now remove temp
        try:
            shutil.rmtree(tmp, ignore_errors=False)
            temp_removed = not tmp.exists()
        except Exception:
            temp_removed = False
        # Hash after to confirm source unchanged (even if validation failed)
    after = _hash_source_files(src_root)
    source_unchanged = before == after
    # If temp not removed, report via validation status? Keep flag
    if validation is None:
        # Should not happen, but create a failed ValidationResult
        from godotforge_core.engine.validate import ValidationResult

        validation = ValidationResult(
            project_root=str(src_root),
            engine=None,
            mode=mode,
            stages=(),
            status="fail",
            wall_duration_ms=0.0,
            graph={"status": "missing"},
        )
    return VerifyResult(
        manifest=manifest,
        plan_id=plan_id,
        plan_hash=plan_hash,
        validation=validation,
        source_before_hash=before,
        source_after_hash=after,
        temp_removed=temp_removed,
        source_unchanged=source_unchanged,
    )
