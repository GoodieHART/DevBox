"""PoC box registry: running boxes publish their connection details to a shared Dict.

The web console (`webapp.py`) can only know where a box lives if the box tells it,
because `modal.forward()` tunnels only exist inside the container. So each runtime
writes its tunnel host/port here the moment the tunnel opens, and the console reads
this Dict to render the list.

Deliberately minimal: no heartbeats, no stop flags, no stale detection, no merge
retries. Every function is best-effort and never raises into the box runtime.

Env override for a throwaway registry: DEVBOX_BOX_DICT=<name>.
"""

import os
import sys
import time
import uuid

import modal

DICT_NAME = os.environ.get("DEVBOX_BOX_DICT", "devbox-boxes-poc")
MAX_BOXES = 50

_dict = None


def set_dict_for_testing(fake_dict):
    """Inject a stand-in for `modal.Dict` (unit tests only)."""
    global _dict
    _dict = fake_dict


def _get_dict():
    global _dict
    if _dict is None:
        _dict = modal.Dict.from_name(DICT_NAME, create_if_missing=True)
    return _dict


def _current_call_id():
    """The Modal FunctionCall id, so the console can cancel this exact run."""
    try:
        return modal.current_function_call_id()
    except Exception:
        return None


def _write(box_id, **fields):
    try:
        store = _get_dict()
        try:
            record = dict(store.get(box_id) or {})
        except Exception:
            record = {}
        record.update(fields)
        record["box_id"] = box_id
        record["updated_at"] = int(time.time())
        store.put(box_id, record)
        return True
    except Exception as exc:
        print(f"[box_registry] write failed for {box_id}: {exc}", file=sys.stderr)
        return False


def start(kind, resources=None):
    """Create a `starting` record and return its id."""
    box_id = f"{kind}-{int(time.time())}-{uuid.uuid4().hex[:4]}"
    resources = resources or {}
    _write(
        box_id,
        kind=kind,
        status="starting",
        created_at=int(time.time()),
        call_id=_current_call_id(),
        cpu=resources.get("cpu"),
        memory=resources.get("memory"),
        gpu=resources.get("gpu"),
    )
    return box_id


def update(box_id, **fields):
    """Patch fields without touching `status`."""
    if box_id is None:
        return False
    return _write(box_id, **fields)


def ready(box_id, **fields):
    """Mark the box running and attach its connection details."""
    if box_id is None:
        return False
    return _write(box_id, status="running", ready_at=int(time.time()), **fields)


def fail(box_id, error):
    if box_id is None:
        return False
    return _write(box_id, status="error", error=str(error)[:500])


def stopped(box_id):
    if box_id is None:
        return False
    return _write(box_id, status="stopped", ended_at=int(time.time()))


def get(box_id):
    try:
        return dict(_get_dict().get(box_id) or {})
    except Exception:
        return {}


def list_boxes():
    """Newest-first snapshot; [] when the Dict is unreachable."""
    try:
        store = _get_dict()
        records = []
        for key in store.keys():
            try:
                record = dict(store.get(key) or {})
            except Exception:
                continue
            if record:
                records.append(record)
        records.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
        return records[:MAX_BOXES]
    except Exception as exc:
        print(f"[box_registry] list failed: {exc}", file=sys.stderr)
        return []
