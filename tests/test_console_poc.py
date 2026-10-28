"""Regression tests for the PoC web console and its box registry.

No Modal credentials, no network, no FastAPI: `webapp._call_state` is the only
place that talks to Modal, and every test stubs it out.
"""

import ast
import asyncio
import base64
import pathlib
import time

import pytest

import console_ui
import webapp
from runtime import box_registry

ROOT = pathlib.Path(__file__).resolve().parent.parent


class FakeDict:
    """The subset of `modal.Dict` that `box_registry` uses."""

    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value

    def keys(self):
        return list(self.data)


@pytest.fixture
def store():
    fake = FakeDict()
    box_registry.set_dict_for_testing(fake)
    yield fake
    box_registry.set_dict_for_testing(None)


class BrokenDict(FakeDict):
    def put(self, key, value):
        raise RuntimeError("dict write failed")


def test_start_writes_starting_record(store):
    box_id = box_registry.start("standard_devbox", {"cpu": 0.5, "memory": 1024})
    assert box_id.startswith("standard_devbox-")
    record = store.data[box_id]
    assert record["status"] == "starting"
    assert record["kind"] == "standard_devbox"
    assert record["cpu"] == 0.5
    assert "call_id" in record and "created_at" in record


def test_ready_then_update_keeps_running_status(store):
    box_id = box_registry.start("rdp_devbox", {})
    box_registry.ready(box_id, rdp_address="h:1")
    assert store.data[box_id]["status"] == "running"
    assert store.data[box_id]["rdp_address"] == "h:1"

    box_registry.update(box_id, web_url="http://h:2")
    assert store.data[box_id]["status"] == "running"
    assert store.data[box_id]["web_url"] == "http://h:2"


def test_finish_records_terminal_status_and_error(store):
    box_id = box_registry.start("standard_devbox", {})
    box_registry.finish(box_id, "error", "boom")
    assert store.data[box_id]["status"] == "error"
    assert store.data[box_id]["error"] == "boom"
    assert "ended_at" in store.data[box_id]


def test_list_boxes_is_newest_first(store):
    older = box_registry.start("a", {})
    newer = box_registry.start("b", {})
    store.data[older]["created_at"] = 1
    store.data[newer]["created_at"] = 2
    assert [r["box_id"] for r in box_registry.list_boxes()] == [newer, older]


def test_none_box_id_is_a_noop():
    assert box_registry.update(None, x=1) is False
    assert box_registry.ready(None, x=1) is False
    assert box_registry.fail(None, "x") is False
    assert box_registry.stopped(None) is False
    assert box_registry.finish(None, "stopped") is False


def test_write_failures_do_not_raise(store):
    box_registry.set_dict_for_testing(BrokenDict())
    box_id = box_registry.start("standard_devbox", {})
    assert isinstance(box_id, str)
    assert box_registry.list_boxes() == []


def _seed(store, kind, status, call_id, created_at=None):
    box_id = f"{kind}-1"
    store.data[box_id] = {
        "box_id": box_id,
        "kind": kind,
        "status": status,
        "created_at": created_at or int(time.time()),
        "call_id": call_id,
    }
    return box_id


def test_snapshot_marks_and_persists_finished(store, monkeypatch):
    box_id = _seed(store, "a", "running", "fc-done")
    monkeypatch.setattr(webapp, "_call_state", lambda call_id: "finished")
    snapshot = {rec["box_id"]: rec for rec in webapp._snapshot()}
    assert snapshot[box_id]["status"] == "finished"
    assert store.data[box_id]["status"] == "finished"


def test_snapshot_leaves_running_box_alone(store, monkeypatch):
    box_id = _seed(store, "a", "running", "fc-run")
    monkeypatch.setattr(webapp, "_call_state", lambda call_id: "running")
    snapshot = {rec["box_id"]: rec for rec in webapp._snapshot()}
    assert snapshot[box_id]["status"] == "running"
    assert store.data[box_id]["status"] == "running"
    assert snapshot[box_id]["age_s"] >= 0


def test_snapshot_maps_error_and_lost(store, monkeypatch):
    error_id = _seed(store, "a", "running", "fc-err")
    lost_id = _seed(store, "b", "running", "fc-lost")
    states = {"fc-err": "error:UserCodeException: boom", "fc-lost": "lost"}
    monkeypatch.setattr(webapp, "_call_state", lambda call_id: states[call_id])
    snapshot = {rec["box_id"]: rec for rec in webapp._snapshot()}
    assert snapshot[error_id]["status"] == "error"
    assert snapshot[lost_id]["status"] == "lost"


def test_snapshot_labels_slow_build_as_provisioning(store, monkeypatch):
    box_id = _seed(store, "a", "starting", "fc-build", created_at=int(time.time()) - 300)
    monkeypatch.setattr(webapp, "_call_state", lambda call_id: "running")
    snapshot = {rec["box_id"]: rec for rec in webapp._snapshot()}
    assert snapshot[box_id]["status"] == "provisioning"


def test_call_state_maps_modal_outcomes(monkeypatch):
    class Call:
        def __init__(self, behaviour):
            self.behaviour = behaviour

        def get(self, timeout=None):
            if isinstance(self.behaviour, Exception):
                raise self.behaviour
            return self.behaviour

    import modal

    cases = {
        None: "finished",
        TimeoutError(): "running",
        modal.exception.TimeoutError(): "running",
        modal.exception.OutputExpiredError(): "finished",
        modal.exception.NotFoundError(): "lost",
        ValueError("nope"): "error:ValueError: nope",
    }
    for behaviour, expected in cases.items():
        monkeypatch.setattr(
            modal, "FunctionCall", type("FC", (), {"from_id": staticmethod(lambda _id, b=behaviour: Call(b))})
        )
        assert webapp._call_state("fc-1") == expected


def _drive(middleware, headers):
    status = {}
    reached = []

    async def spy(scope, receive, send):
        reached.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    wrapped = middleware(spy)

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
            status["headers"] = dict(message["headers"])

    scope = {"type": "http", "method": "GET", "path": "/", "headers": headers, "client": ("1.2.3.4", 0)}
    asyncio.run(wrapped(scope, receive, send))
    return status, reached


def _basic(user, password):
    return ("Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()).encode()


def test_auth_rejects_missing_and_wrong_credentials():
    middleware = lambda app: webapp.BasicAuthMiddleware(app, "u", "p")
    status, reached = _drive(middleware, [])
    assert status["code"] == 401 and reached == []
    assert b"www-authenticate" in status["headers"]

    status, reached = _drive(middleware, [(b"authorization", _basic("u", "wrong"))])
    assert status["code"] == 401 and reached == []

    status, reached = _drive(middleware, [(b"authorization", b"Basic !!!")])
    assert status["code"] == 401 and reached == []


def test_auth_accepts_valid_credentials():
    status, reached = _drive(lambda app: webapp.BasicAuthMiddleware(app, "u", "p"), [(b"authorization", _basic("u", "p"))])
    assert status["code"] == 200 and reached == ["/"]


def test_auth_fails_closed_when_unconfigured():
    status, reached = _drive(lambda app: webapp.BasicAuthMiddleware(app, "", ""), [(b"authorization", _basic("u", "p"))])
    assert status["code"] == 503 and reached == []


def test_catalog_matches_launchers_in_devbox_py():
    tree = ast.parse((ROOT / "devbox.py").read_text(encoding="utf-8"))
    launchers = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert len(webapp.CATALOG) == 14
    for _, function_name in webapp.CATALOG.values():
        assert function_name in launchers, f"{function_name} is not defined in devbox.py"
    assert not any("llamacpp" in name for _, name in webapp.CATALOG.values())


def test_render_index_injects_catalog_labels():
    html = console_ui.render_index(webapp.CATALOG)
    assert "__CATALOG__" not in html
    assert "Standard DevBox" in html


def test_parse_launch_body_accepts_json_object():
    assert webapp._parse_launch_body(b'{"box_type": "standard"}') == {"box_type": "standard"}


@pytest.mark.parametrize("raw", [b"", b"{", b"[]", b'"text"', b"null", b"\xff"])
def test_parse_launch_body_rejects_non_objects(raw):
    assert webapp._parse_launch_body(raw) is None


def _runtime_function_calls(function_name):
    tree = ast.parse((ROOT / "runtime" / "shared_runtime.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return {
                sub.func.attr
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                and isinstance(sub.func.value, ast.Name) and sub.func.value.id == "box_registry"
            }
    raise AssertionError(f"{function_name} not found")


@pytest.mark.parametrize("function_name", ["run_devbox_shared", "run_rdp_devbox_shared", "run_opencode_shared"])
def test_every_runtime_publishes_to_the_registry(function_name):
    calls = _runtime_function_calls(function_name)
    assert "start" in calls, calls
    assert "ready" in calls, calls
