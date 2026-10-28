"""DevBox web console (PoC) - launch boxes and read their connection details from a browser.

Deliberately small: one page, four endpoints, one shared password. It does not
replace the CLI, does not do heartbeats, and does not wait for a box to come up.

Prereqs (one time):

    modal secret create devbox-console-auth CONSOLE_USER=you CONSOLE_PASSWORD='...'
    modal deploy devbox.py            # the console spawns launchers by name
    DEVBOX_CPU_ONLY=1 modal deploy devbox.py    # if the account has no GPU payment method

Then:

    modal deploy webapp.py            # prints the console URL
    modal serve webapp.py             # or hot-reload locally
"""

import base64
import json
import os
import secrets
import sys
import time

import modal

from console_ui import render_index
from runtime import box_registry

LAUNCHER_APP = "personal-devbox-launcher"

# id -> (label, Modal function name). The two llama.cpp boxes are excluded on
# purpose: they ask for a model interactively, so they cannot be launched blind.
CATALOG = {
    "standard": ("Standard DevBox", "launch_devbox"),
    "standard_t4": ("Standard + T4", "launch_devbox_t4"),
    "standard_l4": ("Standard + L4", "launch_devbox_l4"),
    "standard_a10g": ("Standard + A10G", "launch_devbox_a10g"),
    "standard_l40s": ("Standard + L40S", "launch_devbox_l40s"),
    "rdp": ("RDP Desktop", "launch_rdp_devbox"),
    "rdp_t4": ("RDP + T4", "launch_rdp_devbox_t4"),
    "rdp_l4": ("RDP + L4", "launch_rdp_devbox_l4"),
    "rdp_a10g": ("RDP + A10G", "launch_rdp_devbox_a10g"),
    "rdp_l40s": ("RDP + L40S", "launch_rdp_devbox_l40s"),
    "doc_processor": ("Document Processing", "launch_doc_processor"),
    "assisted_coding": ("AI Coding (OpenCode)", "launch_assisted_coding"),
    "llm_playroom": ("LLM Playroom (Ollama)", "launch_llm_playroom"),
    "forensics": ("Forensics / RE", "launch_forensics_image"),
}


def _parse_launch_body(raw):
    """The launch payload, or None when `raw` is not a JSON object.

    `json.loads` raises ValueError subclasses for both malformed JSON and
    non-UTF-8 bytes, so a bad body is a 400 rather than a 500.
    """
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


class BasicAuthMiddleware:
    """Fail-closed HTTP Basic auth. No user/password configured -> 503, never open."""

    def __init__(self, app, username, password):
        self.app = app
        self.username = username
        self.password = password

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not self.username or not self.password:
            await _send_json(send, 503, {"error": "CONSOLE_USER/CONSOLE_PASSWORD not configured"})
            return
        headers = dict(scope.get("headers") or [])
        raw = headers.get(b"authorization", b"").decode("latin-1")
        ok = False
        if raw.lower().startswith("basic "):
            try:
                decoded = base64.b64decode(raw[6:].strip(), validate=True).decode("utf-8")
                user, _, password = decoded.partition(":")
                ok = secrets.compare_digest(user, self.username) & secrets.compare_digest(
                    password, self.password
                )
            except Exception:
                ok = False
        if not ok:
            await _send_json(
                send,
                401,
                {"error": "authentication required"},
                extra_headers=[(b"www-authenticate", b'Basic realm="DevBox Console", charset="UTF-8"')],
            )
            return
        await self.app(scope, receive, send)


async def _send_json(send, status, payload, extra_headers=None):
    body = json.dumps(payload).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"cache-control", b"no-store"),
    ] + (extra_headers or [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


TERMINAL_STATUSES = {"stopped", "finished", "expired", "lost", "error"}
PROVISIONING_AFTER_S = 120


def _call_state(call_id):
    """Non-blocking liveness check for a spawned call.

    Returns 'running', 'finished', 'expired', 'lost', or 'error:<message>'.
    This is the console's only liveness signal - boxes do not send heartbeats.
    """
    try:
        modal.FunctionCall.from_id(call_id).get(timeout=0)
        return "finished"
    except modal.exception.OutputExpiredError:
        return "finished"
    except modal.exception.NotFoundError:
        return "lost"
    except (TimeoutError, modal.exception.TimeoutError):
        return "running"
    except Exception as exc:
        return f"error:{type(exc).__name__}: {exc}"[:300]


def _snapshot():
    """List boxes, polling Modal for anything not already in a terminal state."""
    now = int(time.time())
    records = []
    for record in box_registry.list_boxes():
        status = record.get("status") or "unknown"
        call_id = record.get("call_id")
        box_id = record.get("box_id")

        if status not in TERMINAL_STATUSES and call_id and box_id:
            state = _call_state(call_id)
            if state == "finished":
                box_registry.finish(box_id, "finished")
                status = "finished"
            elif state == "lost":
                box_registry.finish(box_id, "lost")
                status = "lost"
            elif state.startswith("error:"):
                box_registry.finish(box_id, "error", state.removeprefix("error:"))
                status = "error"
            if status != record.get("status"):
                record = box_registry.get(box_id) or record
                status = record.get("status") or status

        if status == "starting" and now - (record.get("created_at") or now) > PROVISIONING_AFTER_S:
            status = "provisioning"

        record["status"] = status
        record["age_s"] = max(0, now - int(record.get("created_at") or now))
        records.append(record)
    return records


def build_app():
    """FastAPI app factory. Split out so `modal serve` reuses the same wiring."""
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="DevBox Console (PoC)", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return render_index(CATALOG)

    @app.get("/api/boxes")
    def boxes():
        try:
            return {"boxes": _snapshot(), "server_time": int(time.time())}
        except Exception as exc:
            return JSONResponse({"error": f"snapshot failed: {exc}"}, status_code=503)

    @app.post("/api/launch")
    async def launch(request: Request):
        payload = _parse_launch_body(await request.body())
        if payload is None:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        box_type = str(payload.get("box_type") or "")
        entry = CATALOG.get(box_type)
        if entry is None:
            return JSONResponse({"error": f"unknown box type {box_type!r}"}, status_code=404)
        try:
            fn = modal.Function.from_name(LAUNCHER_APP, entry[1])
            call = fn.spawn()
        except modal.exception.NotFoundError:
            return JSONResponse(
                {"error": f"{LAUNCHER_APP} is not deployed - run `modal deploy devbox.py`"},
                status_code=503,
            )
        except Exception as exc:
            return JSONResponse({"error": f"spawn failed: {exc}"}, status_code=503)
        return JSONResponse({"box_type": box_type, "call_id": call.object_id}, status_code=202)

    @app.post("/api/boxes/{box_id}/stop")
    def stop(box_id: str):
        record = box_registry.get(box_id)
        if not record:
            return JSONResponse({"error": f"unknown box {box_id!r}"}, status_code=404)
        call_id = record.get("call_id")
        if not call_id:
            return JSONResponse({"error": "box has no recorded call id"}, status_code=409)
        try:
            modal.FunctionCall.from_id(call_id).cancel(terminate_containers=True)
        except modal.exception.NotFoundError:
            return JSONResponse({"error": "call already finished"}, status_code=409)
        except Exception as exc:
            return JSONResponse({"error": f"stop failed: {exc}"}, status_code=503)
        box_registry.stopped(box_id)
        return JSONResponse({"box_id": box_id, "status": "stopped"}, status_code=202)

    return BasicAuthMiddleware(
        app,
        username=os.environ.get("CONSOLE_USER", ""),
        password=os.environ.get("CONSOLE_PASSWORD", ""),
    )


console_image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_pip_install("fastapi", "httpx")
    # Local modules must be named here: Modal mounts the entrypoint module
    # itself plus imported *packages*, but not loose top-level modules.
    .add_local_python_source("runtime.box_registry", "console_ui")
)


def _auth_secret():
    """Secret with CONSOLE_USER / CONSOLE_PASSWORD.

    Falls back to an empty secret so the module stays importable (local lint,
    `modal run` helpers). The app then fails closed: every request gets 503.
    """
    try:
        return modal.Secret.from_name("devbox-console-auth")
    except Exception as exc:
        print(f"[webapp] devbox-console-auth unavailable ({exc}); console will fail closed.", file=sys.stderr)
        return modal.Secret.from_dict({})


app = modal.App(name="devbox-console-poc")


@app.function(
    image=console_image,
    secrets=[_auth_secret()],
    timeout=600,
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def console():
    return build_app()


@app.function(image=console_image)
def _selfcheck():
    """Exercise the real routes and auth against the deployed-image env, no deploy needed.

    Run with: modal run webapp.py::_selfcheck
    """
    from fastapi.testclient import TestClient

    class FakeDict:
        def __init__(self):
            self.data = {
                "standard_devbox-1-abcd": {
                    "box_id": "standard_devbox-1-abcd",
                    "kind": "standard_devbox",
                    "status": "running",
                    "created_at": 1,
                    "ssh_command": "ssh root@example -p 1234 -t \"tmux attach -t devbox\"",
                }
            }

        def get(self, key):
            return self.data.get(key)

        def put(self, key, value):
            self.data[key] = value

        def keys(self):
            return list(self.data)

    box_registry.set_dict_for_testing(FakeDict())
    os.environ["CONSOLE_USER"] = "poc"
    os.environ["CONSOLE_PASSWORD"] = "poc-pass"

    client = TestClient(build_app())
    auth = {"Authorization": "Basic " + base64.b64encode(b"poc:poc-pass").decode()}

    results = {}
    results["index_unauth"] = client.get("/").status_code
    results["boxes_unauth"] = client.get("/api/boxes").status_code
    index = client.get("/", headers=auth)
    boxes = client.get("/api/boxes", headers=auth)
    results["index_auth"] = index.status_code
    results["index_has_title"] = "DevBox Console" in index.text
    results["boxes_auth"] = boxes.status_code
    results["boxes_payload"] = boxes.json()["boxes"][0]["kind"]
    results["launch_unknown"] = client.post("/api/launch", json={"box_type": "nope"}, headers=auth).status_code
    results["stop_unknown"] = client.post("/api/boxes/ghost/stop", headers=auth).status_code
    print(results)
    assert results["index_unauth"] == 401, results
    assert results["boxes_unauth"] == 401, results
    assert results["index_auth"] == 200, results
    assert results["boxes_auth"] == 200, results
    assert results["boxes_payload"] == "standard_devbox", results
    assert results["launch_unknown"] == 404, results
    assert results["stop_unknown"] == 404, results
    return results
