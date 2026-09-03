"""Hub approval gate — recorded authorization, separate from execution.

The approval gate records operator authorization bound to the exact
``planHash`` before any mutation (``docs/contracts/hub-v1.md`` §5) and
checks that binding before the patch engine is invoked. Hub v1 records
``explicit_cli`` authorizations only; interactive prompts and CI tokens are
deferred. The gate never executes anything itself — it appends and reads
run-record events only.

Offline, deterministic, no AI, network, telemetry, or credentials.
"""

from __future__ import annotations

from pathlib import Path

from godotforge_core.hub.run_record import (
    Authorization,
    RunEvent,
    RunEventKind,
    append_event,
)

APPROVAL_MODE_EXPLICIT_CLI = "explicit_cli"
APPROVAL_SCOPE_APPLY = "apply"


def record_explicit_cli_authorization(
    root: Path | str,
    run_id: str,
    plan_hash: str,
    *,
    scope: str = APPROVAL_SCOPE_APPLY,
) -> RunEvent:
    """Record an ``explicit_cli`` authorization bound to an exact planHash.

    The authorization is persisted only as an ``authorization_recorded``
    run-record event; there is no separate approval file. Raises
    ``ValueError`` for malformed run ids, hashes, modes, or scopes.
    """
    authorization = Authorization(mode=APPROVAL_MODE_EXPLICIT_CLI, plan_hash=plan_hash, scope=scope)
    return append_event(root, run_id, RunEventKind.AUTHORIZATION_RECORDED, authorization.as_dict())


def require_authorization(
    events: tuple[RunEvent, ...] | list[RunEvent], plan_hash: str
) -> Authorization:
    """Return the recorded authorization iff it covers applying ``plan_hash``.

    Searches one run's events for ``authorization_recorded`` and returns the
    authorization only when its ``plan_hash`` matches exactly and its scope
    is ``apply``. Raises ``ValueError`` when no authorization is recorded or
    the binding differs — an authorization for plan A is invalid for plan B,
    no exceptions (hub-v1 §5).
    """
    for event in events:
        if event.kind is not RunEventKind.AUTHORIZATION_RECORDED:
            continue
        authorization = Authorization.from_dict(event.payload)
        if authorization.plan_hash != plan_hash:
            raise ValueError(
                f"authorization plan_hash {authorization.plan_hash!r} does not "
                f"match current plan hash {plan_hash!r}"
            )
        if authorization.scope != APPROVAL_SCOPE_APPLY:
            raise ValueError(f"authorization scope {authorization.scope!r} does not cover apply")
        return authorization
    raise ValueError("no recorded authorization for this run")
