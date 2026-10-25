"""Cost tracking for DevBox launches.

Records per-session resource usage and an estimated USD cost to a durable
ledger under /data/.cost/ (on the my-dev-volume volume). Mirrors the atexit
pattern used by runtime/backup_utils.register_custom_backup.

Estimates only — reconcile against `modal billing report` for authoritative
numbers.
"""

import atexit
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

COST_DIR = "/data/.cost"
SESSIONS_DIR = os.path.join(COST_DIR, "sessions")


def _cost_dir() -> str:
    return os.environ.get("DEVBOX_COST_DIR", COST_DIR)


def _sessions_dir() -> str:
    return os.path.join(_cost_dir(), "sessions")

_session: dict[str, Any] | None = None
_registered: bool = False


def _ensure_dirs() -> None:
    os.makedirs(_sessions_dir(), exist_ok=True)


def _session_path(session: dict[str, Any]) -> str:
    return os.path.join(_sessions_dir(), f"{session['session_id']}.json")


def _modal_fc_id() -> str | None:
    try:
        import modal

        return modal.current_function_call_id()
    except Exception:
        return None


def _modal_container_id() -> str | None:
    return os.environ.get("MODAL_TASK_ID")


def _cost_estimate(session: dict[str, Any]) -> float:
    try:
        from devbox_core.config import estimate_cost_usd

        return float(
            estimate_cost_usd(
                session.get("cpu", 0.0),
                session.get("memory_mb", 0),
                session.get("gpu", None),
                session.get("elapsed_s", 0.0),
            )
        )
    except Exception:
        return 0.0


def _write(session: dict[str, Any]) -> None:
    try:
        _ensure_dirs()
        path = _session_path(session)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(session, f, indent=2, sort_keys=True)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception as e:  # pragma: no cover - best effort
        print(f"[cost_tracker] write failed: {e}", file=sys.stderr)


def start_session(
    devbox_type: str,
    resources: dict[str, Any] | None = None,
    modal_fc_id: str | None = None,
    modal_container_id: str | None = None,
) -> dict[str, Any]:
    """Begin tracking a session. Returns the session dict."""
    global _session
    resources = resources or {}
    cpu = resources.get("cpu", 0.0)
    memory_mb = resources.get("memory", 0)
    gpu = resources.get("gpu", None)
    timeout = resources.get("timeout", None)

    short = uuid.uuid4().hex[:6]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    session_id = f"{ts}_{devbox_type}_{short}"

    pricing_version = None
    try:
        from devbox_core.config import MODAL_PRICING_VERSION

        pricing_version = MODAL_PRICING_VERSION
    except Exception:
        pass

    _session = {
        "session_id": session_id,
        "devbox_type": devbox_type,
        "cpu": cpu,
        "memory_mb": memory_mb,
        "gpu": gpu,
        "timeout_s": timeout,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "elapsed_s": 0.0,
        "billed_s": 0.0,
        "estimated_cost_usd": 0.0,
        "status": "running",
        "pricing_version": pricing_version,
        "modal_function_call_id": modal_fc_id
        if modal_fc_id is not None
        else _modal_fc_id(),
        "modal_container_id": modal_container_id
        if modal_container_id is not None
        else _modal_container_id(),
        "start_monotonic": time.monotonic(),
    }
    _ensure_dirs()
    _write(_session)
    return _session


def checkpoint() -> None:
    """Refresh the current session file with elapsed time (crash safety)."""
    global _session
    if _session is None or "start_monotonic" not in _session:
        return
    try:
        _session["elapsed_s"] = round(time.monotonic() - _session["start_monotonic"], 3)
        _session["estimated_cost_usd"] = _cost_estimate(_session)
        _write(_session)
    except Exception as e:  # pragma: no cover
        print(f"[cost_tracker] checkpoint failed: {e}", file=sys.stderr)


def register_cost_flush(session: dict[str, Any] | None = None) -> None:
    """Register an atexit handler that finalizes the session on shutdown."""
    global _session, _registered
    if session is not None:
        _session = session
    if _session is None:
        return
    if "start_monotonic" not in _session:
        _session["start_monotonic"] = time.monotonic()
    _write(_session)
    if _registered:
        return
    atexit.register(_flush)
    _registered = True


def flush() -> None:
    """Public alias for the final flush (useful for tests)."""
    _flush()


def _flush() -> None:
    global _session
    if _session is None:
        return
    try:
        _session["elapsed_s"] = round(
            time.monotonic() - _session.get("start_monotonic", time.monotonic()), 3
        )
        _session["ended_at"] = datetime.now(timezone.utc).isoformat()
        _session["estimated_cost_usd"] = _cost_estimate(_session)
        _session["billed_s"] = _session["elapsed_s"]
        if _session.get("status") == "running":
            _session["status"] = "completed"
        _write(_session)
    except Exception as e:  # pragma: no cover
        print(f"[cost_tracker] flush failed: {e}", file=sys.stderr)


def list_sessions() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        _ensure_dirs()
        for name in os.listdir(_sessions_dir()):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(_sessions_dir(), name)) as f:
                    out.append(json.load(f))
            except Exception:
                continue
    except Exception:
        pass
    return sorted(out, key=lambda s: s.get("started_at", "") or "")


def summarize(sessions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    sessions = sessions if sessions is not None else list_sessions()
    total_elapsed = sum((s.get("elapsed_s", 0) or 0) for s in sessions)
    total_cost = sum((s.get("estimated_cost_usd", 0) or 0) for s in sessions)
    by_type: dict[str, dict[str, Any]] = {}
    for s in sessions:
        t = s.get("devbox_type", "unknown")
        bucket = by_type.setdefault(t, {"sessions": 0, "elapsed_s": 0.0, "cost": 0.0})
        bucket["sessions"] += 1
        bucket["elapsed_s"] += s.get("elapsed_s", 0) or 0
        bucket["cost"] += s.get("estimated_cost_usd", 0) or 0
    return {
        "sessions": len(sessions),
        "total_elapsed_s": round(total_elapsed, 3),
        "total_estimated_cost_usd": round(total_cost, 6),
        "by_type": by_type,
    }


def cost_estimate(cpu, memory_mb, gpu, elapsed_s) -> float:
    """Public estimate helper (delegates to config)."""
    return _cost_estimate(
        {"cpu": cpu, "memory_mb": memory_mb, "gpu": gpu, "elapsed_s": elapsed_s}
    )


def reset_for_testing() -> None:
    """Reset module state (tests only)."""
    global _session, _registered
    _session = None
    _registered = False
