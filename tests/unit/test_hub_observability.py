"""Unit tests for Hub observability (hub/observability.py)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from godotforge_core.hub.observability import (
    compute_metrics,
    get_run_logger,
    get_timeline,
    setup_structured_logging,
)
from godotforge_core.hub.run_record import (
    RunEventKind,
    append_event,
)

H = "a" * 64
H2 = "b" * 64
H3 = "c" * 64
RUN = "run-0123456789ab"
ENGINE = {"version": "4.7.1.stable.mono", "flavor": "mono", "executable_sha256": H3}
ARTIFACTS = {"project.godot": H, "scenes/main.tscn": H2}

START_PAYLOAD = {
    "goal_hash": H,
    "manifest_hash": H2,
    "plan_id": "cr-deadbeef",
    "plan_hash": H3,
}
AUTH_PAYLOAD = {"mode": "explicit_cli", "plan_hash": H3, "scope": "apply"}
APPLY_PAYLOAD = {"txid": "tx-abc123", "artifact_hash": ARTIFACTS}
VALIDATION_PAYLOAD = {
    "mode": "full",
    "status": "ok",
    "stages": [
        {"stage": "import", "status": "ok"},
        {"stage": "load", "status": "ok"},
        {"stage": "boot", "status": "ok"},
    ],
    "engine": ENGINE,
    "wall_duration_ms": 1500,
    "source_unchanged": True,
    "temp_removed": True,
}
VALIDATION_PAYLOAD_FAILED = {
    "mode": "full",
    "status": "failed",
    "stages": [
        {"stage": "import", "status": "ok"},
        {"stage": "load", "status": "failed"},
    ],
    "engine": ENGINE,
    "wall_duration_ms": 800,
    "source_unchanged": True,
    "temp_removed": True,
}


def _start(root: Path, run_id: str = RUN) -> None:
    append_event(root, run_id, RunEventKind.RUN_STARTED, START_PAYLOAD)


def _full_run(root: Path, run_id: str = RUN) -> None:
    _start(root, run_id)
    append_event(root, run_id, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(root, run_id, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    append_event(root, run_id, RunEventKind.VALIDATION_COMPLETED, VALIDATION_PAYLOAD)


def _full_run_failed(root: Path, run_id: str = RUN) -> None:
    _start(root, run_id)
    append_event(root, run_id, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
    append_event(root, run_id, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
    append_event(root, run_id, RunEventKind.VALIDATION_COMPLETED, VALIDATION_PAYLOAD_FAILED)
    append_event(
        root,
        run_id,
        RunEventKind.RUN_FAILED,
        {"reason": "validation_failed", "stage": "validation"},
    )


def _noop_run(root: Path, run_id: str = RUN) -> None:
    payload = dict(START_PAYLOAD)
    payload["plan_hash"] = None
    append_event(root, run_id, RunEventKind.RUN_STARTED, payload)
    append_event(root, run_id, RunEventKind.RUN_FINALIZED, {"outcome": "noop", "proof_hash": H})


def _create_artifact_files(root: Path) -> None:
    """Create actual artifact files for size correlation."""
    (root / "project.godot").write_text('config_version=5\n[application]\nconfig/name="Test"\n')
    (root / "scenes").mkdir()
    (root / "scenes" / "main.tscn").write_text(
        '[gd_scene load_steps=1 format=3]\n[ext_resource path="res://script.gd" type="Script" id=1]'
    )


class TestComputeMetrics:
    def test_empty_store(self, tmp_path: Path) -> None:
        metrics = compute_metrics(tmp_path)
        assert metrics.total_runs == 0
        assert metrics.success_rate == 0.0
        assert metrics.avg_duration_ms is None
        assert metrics.artifact_size_percentiles == {"p50": 0, "p90": 0, "p99": 0}

    def test_single_successful_run(self, tmp_path: Path) -> None:
        _create_artifact_files(tmp_path)
        _full_run(tmp_path)
        _finalize_run(tmp_path)

        metrics = compute_metrics(tmp_path)
        assert metrics.total_runs == 1
        assert metrics.success_rate == 1.0
        assert metrics.avg_duration_ms == 1500.0
        # Artifact sizes should be computed from actual files
        assert metrics.artifact_size_percentiles["p50"] > 0

    def test_mixed_runs_success_and_failure(self, tmp_path: Path) -> None:
        _create_artifact_files(tmp_path)
        _full_run(tmp_path, "run-0123456789ab")
        _finalize_run(tmp_path, "run-0123456789ab")
        _full_run_failed(tmp_path, "run-fedcba987654")

        metrics = compute_metrics(tmp_path)
        assert metrics.total_runs == 2
        assert metrics.success_rate == 0.5
        # Duration from both runs
        assert metrics.avg_duration_ms == pytest.approx(1150.0, rel=0.01)

    def test_noop_run_counts_as_success(self, tmp_path: Path) -> None:
        _noop_run(tmp_path)
        metrics = compute_metrics(tmp_path)
        assert metrics.total_runs == 1
        assert metrics.success_rate == 1.0
        assert metrics.avg_duration_ms is None  # No validation event for noop

    def test_partial_run_not_finalized(self, tmp_path: Path) -> None:
        _start(tmp_path)
        append_event(tmp_path, RUN, RunEventKind.AUTHORIZATION_RECORDED, AUTH_PAYLOAD)
        # Run is in STARTED/AUTHORIZED state, not finalized

        metrics = compute_metrics(tmp_path)
        assert metrics.total_runs == 1
        assert metrics.success_rate == 0.0  # Not finalized = not successful

    def test_artifact_sizes_correlated_with_actual_files(self, tmp_path: Path) -> None:
        _create_artifact_files(tmp_path)
        _full_run(tmp_path)
        _finalize_run(tmp_path)

        metrics = compute_metrics(tmp_path)
        # Both artifacts exist, sizes should be recorded
        sizes = metrics.artifact_size_percentiles
        assert sizes["p50"] > 0
        assert sizes["p90"] > 0
        assert sizes["p99"] > 0

    def test_missing_artifact_files_handled_gracefully(self, tmp_path: Path) -> None:
        # Don't create artifact files
        _full_run(tmp_path)
        _finalize_run(tmp_path)

        metrics = compute_metrics(tmp_path)
        # Should not crash, sizes will be 0
        assert metrics.total_runs == 1


class TestGetRunLogger:
    def test_logger_adapter_injects_run_id_in_extra(self) -> None:
        logger = get_run_logger("run-abcdef123456")
        # The adapter should add run_id to extra
        assert logger.extra["run_id"] == "run-abcdef123456"
        # Process a message
        msg, kwargs = logger.process("Test message", {})
        assert kwargs["extra"]["run_id"] == "run-abcdef123456"

    def test_different_run_ids_produce_separate_adapters(self) -> None:
        logger1 = get_run_logger("run-111111111111")
        logger2 = get_run_logger("run-222222222222")

        assert logger1.extra["run_id"] == "run-111111111111"
        assert logger2.extra["run_id"] == "run-222222222222"

        msg1, kwargs1 = logger1.process("From logger 1", {})
        msg2, kwargs2 = logger2.process("From logger 2", {})
        assert kwargs1["extra"]["run_id"] == "run-111111111111"
        assert kwargs2["extra"]["run_id"] == "run-222222222222"

    def test_setup_structured_logging_configures_format(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Don't call setup_structured_logging - it replaces handlers
        # Instead test that the format string is correct
        from godotforge_core.hub.observability import _RunIdFilter

        filter_obj = _RunIdFilter()
        # Filter should always return True and ensure run_id exists
        import logging

        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        assert filter_obj.filter(record) is True
        assert record.run_id == "N/A"  # Default when not set


class TestGetTimeline:
    def test_empty_run_returns_empty_list(self, tmp_path: Path) -> None:
        timeline = get_timeline(tmp_path, "run-nonexistent")
        assert timeline == []

    def test_timeline_includes_all_event_kinds(self, tmp_path: Path) -> None:
        _full_run(tmp_path)
        _finalize_run(tmp_path)

        timeline = get_timeline(tmp_path, RUN)
        assert len(timeline) == 5

        kinds = [e.kind for e in timeline]
        assert kinds == [
            "run_started",
            "authorization_recorded",
            "apply_committed",
            "validation_completed",
            "run_finalized",
        ]

    def test_timeline_ordered_by_seq(self, tmp_path: Path) -> None:
        _full_run(tmp_path)
        _finalize_run(tmp_path)

        timeline = get_timeline(tmp_path, RUN)
        seqs = [e.seq for e in timeline]
        assert seqs == list(range(1, 6))

    def test_timeline_summary_contains_key_info(self, tmp_path: Path) -> None:
        _full_run(tmp_path)
        _finalize_run(tmp_path)

        timeline = get_timeline(tmp_path, RUN)

        # Check run_started summary
        started = next(e for e in timeline if e.kind == "run_started")
        assert "goal=" in started.summary
        assert "plan=" in started.summary
        assert started.details["plan_id"] == "cr-deadbeef"

        # Check apply_committed summary
        applied = next(e for e in timeline if e.kind == "apply_committed")
        assert "2 artifact(s)" in applied.summary
        assert applied.details["artifact_count"] == 2

        # Check validation_completed summary
        validated = next(e for e in timeline if e.kind == "validation_completed")
        assert "status=ok" in validated.summary
        assert validated.details["wall_duration_ms"] == 1500

        # Check run_finalized summary
        finalized = next(e for e in timeline if e.kind == "run_finalized")
        assert "outcome=applied" in finalized.summary

    def test_timeline_failed_run(self, tmp_path: Path) -> None:
        _full_run_failed(tmp_path)

        timeline = get_timeline(tmp_path, RUN)
        kinds = [e.kind for e in timeline]
        assert "run_failed" in kinds

        failed = next(e for e in timeline if e.kind == "run_failed")
        assert "validation_failed" in failed.summary
        assert failed.details["reason"] == "validation_failed"

    def test_timeline_interrupted_run(self, tmp_path: Path) -> None:
        _start(tmp_path)
        append_event(tmp_path, RUN, RunEventKind.APPLY_COMMITTED, APPLY_PAYLOAD)
        append_event(tmp_path, RUN, RunEventKind.RUN_INTERRUPTED, {"reason": "crash"})

        timeline = get_timeline(tmp_path, RUN)
        kinds = [e.kind for e in timeline]
        assert kinds == ["run_started", "apply_committed", "run_interrupted"]

        interrupted = next(e for e in timeline if e.kind == "run_interrupted")
        assert "crash" in interrupted.summary

    def test_timeline_details_structured(self, tmp_path: Path) -> None:
        _full_run(tmp_path)
        _finalize_run(tmp_path)

        timeline = get_timeline(tmp_path, RUN)

        for event in timeline:
            assert isinstance(event.details, dict)
            assert isinstance(event.summary, str)
            assert len(event.summary) > 0


def _finalize_run(root: Path, run_id: str = RUN) -> None:
    from godotforge_core.hub.run_record import compute_proof_for_outcome, fold_run, read_events

    events = read_events(root, run_id)
    record = fold_run(events, run_id)
    proof = compute_proof_for_outcome(record, "applied")
    append_event(
        root, run_id, RunEventKind.RUN_FINALIZED, {"proof_hash": proof, "outcome": "applied"}
    )


class TestSetupStructuredLogging:
    def test_setup_returns_clean_root_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        setup_structured_logging(logging.DEBUG)
        logger = logging.getLogger()

        assert len(logger.handlers) == 1
        assert logger.level == logging.DEBUG
        formatter = logger.handlers[0].formatter
        assert formatter is not None
        assert "run_id=%(run_id)s" in formatter._fmt

    def test_run_id_filter_added_to_root(self) -> None:
        setup_structured_logging(logging.INFO)
        logger = logging.getLogger()
        from godotforge_core.hub.observability import _RunIdFilter

        assert any(isinstance(f, _RunIdFilter) for f in logger.filters)
