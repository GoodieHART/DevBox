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
import os
import secrets
import sys

import modal

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

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DevBox Console</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px; font: 14px/1.5 ui-sans-serif, system-ui, sans-serif;
         background: #0b0d10; color: #e6e8eb; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: #8b94a3; margin-bottom: 20px; font-size: 12px; }
  .grid { display: grid; gap: 8px; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }
  button { font: inherit; padding: 10px 12px; border-radius: 8px; cursor: pointer;
           border: 1px solid #262b33; background: #14181d; color: #e6e8eb; text-align: left; }
  button:hover { border-color: #3b82f6; }
  button:disabled { opacity: .5; cursor: progress; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th, td { text-align: left; padding: 8px; border-bottom: 1px solid #1c2128; vertical-align: top; }
  th { color: #8b94a3; font-weight: 500; font-size: 12px; }
  code { font-family: ui-monospace, monospace; font-size: 12px; }
  .tag { padding: 1px 6px; border-radius: 999px; font-size: 11px; background: #1c2128; }
  .running { background: #14361f; color: #4ade80; }
  .starting { background: #3a2d10; color: #fbbf24; }
  .error { background: #3b1414; color: #f87171; }
  .stop { border-color: #3b1414; color: #f87171; padding: 4px 8px; font-size: 12px; }
  .msg { margin: 12px 0; padding: 8px 10px; border-radius: 8px; background: #14181d;
         border: 1px solid #262b33; color: #8b94a3; font-size: 12px; display: none; }
  h2 { font-size: 14px; margin: 28px 0 0; color: #8b94a3; font-weight: 500; }
</style>
</head>
<body>
<h1>DevBox Console</h1>
<div class="sub">Boxes publish their tunnels to a Modal Dict. This page refreshes every 5 s.</div>
<div class="grid" id="catalog"></div>
<div class="msg" id="msg"></div>
<h2>Boxes</h2>
<table>
  <thead><tr><th>Box</th><th>Status</th><th>Connection</th><th></th></tr></thead>
  <tbody id="rows"><tr><td colspan="4" style="color:#8b94a3">loading…</td></tr></tbody>
</table>
<script>
const CATALOG = __CATALOG__;
const msg = document.getElementById('msg');
function say(text, ok) {
  msg.textContent = text;
  msg.style.display = text ? 'block' : 'none';
  msg.style.color = ok === false ? '#f87171' : '#8b94a3';
}
function renderCatalog() {
  const root = document.getElementById('catalog');
  root.innerHTML = '';
  for (const [id, label] of Object.entries(CATALOG)) {
    const b = document.createElement('button');
    b.textContent = label;
    b.onclick = () => launch(id, b);
    root.appendChild(b);
  }
}
async function launch(id, btn) {
  btn.disabled = true;
  say('spawning ' + id + '…');
  try {
    const r = await fetch('/api/launch', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({box_type: id})
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.status);
    say('spawned ' + id + ' (call ' + (data.call_id || '?') + '). It appears here once its tunnel opens.',
        true);
    load();
  } catch (e) {
    say('launch failed: ' + e.message, false);
  } finally {
    btn.disabled = false;
  }
}
async function stop(boxId) {
  if (!confirm('Force-stop ' + boxId + '? The exit backup will not run.')) return;
  const r = await fetch('/api/boxes/' + encodeURIComponent(boxId) + '/stop', {method: 'POST'});
  const data = await r.json();
  say(r.ok ? 'stop requested for ' + boxId : 'stop failed: ' + (data.error || r.status), r.ok);
  load();
}
function connection(rec) {
  if (rec.rdp_address) return 'RDP ' + rec.rdp_address + ' · root / ' + (rec.rdp_password || '?');
  const parts = [];
  if (rec.web_url) parts.push('<a href="' + rec.web_url + '" target="_blank">Open web UI</a>');
  if (rec.ssh_command) parts.push('<code>' + rec.ssh_command + '</code>');
  return parts.join('<br>') || '<span style="color:#8b94a3">waiting for tunnel…</span>';
}
async function load() {
  try {
    const r = await fetch('/api/boxes');
    const data = await r.json();
    const rows = document.getElementById('rows');
    if (!r.ok) throw new Error(data.error || r.status);
    if (!data.boxes.length) {
      rows.innerHTML = '<tr><td colspan="4" style="color:#8b94a3">no boxes yet</td></tr>';
      return;
    }
    rows.innerHTML = '';
    for (const rec of data.boxes) {
      const tr = document.createElement('tr');
      const status = rec.status || 'unknown';
      tr.innerHTML = '<td>' + (rec.kind || '?') + '<br><code style="color:#8b94a3">' +
        (rec.box_id || '') + '</code></td>' +
        '<td><span class="tag ' + status + '">' + status + '</span></td>' +
        '<td>' + connection(rec) + '</td>' +
        '<td></td>';
      const cell = tr.lastElementChild;
      if (rec.call_id && status !== 'stopped') {
        const b = document.createElement('button');
        b.className = 'stop';
        b.textContent = 'Stop';
        b.onclick = () => stop(rec.box_id);
        cell.appendChild(b);
      }
      rows.appendChild(tr);
    }
  } catch (e) {
    say('could not load boxes: ' + e.message, false);
  }
}
renderCatalog();
load();
setInterval(load, 5000);
</script>
</body>
</html>
"""


def _render_index():
    import json

    return INDEX_HTML.replace("__CATALOG__", json.dumps({k: v[0] for k, v in CATALOG.items()}))


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
    import json

    body = json.dumps(payload).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"cache-control", b"no-store"),
    ] + (extra_headers or [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def build_app():
    """FastAPI app factory. Split out so `modal serve` reuses the same wiring."""
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="DevBox Console (PoC)", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _render_index()

    @app.get("/api/boxes")
    def boxes():
        return {"boxes": box_registry.list_boxes()}

    @app.post("/api/launch")
    async def launch(request: Request):
        try:
            payload = await request.json()
        except Exception:
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
    .add_local_python_source("runtime.box_registry")
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
    import base64 as _b64

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
    auth = {"Authorization": "Basic " + _b64.b64encode(b"poc:poc-pass").decode()}

    results = {}
    results["index_unauth"] = client.get("/").status_code
    results["boxes_unauth"] = client.get("/api/boxes").status_code
    results["index_auth"] = client.get("/", headers=auth).status_code
    results["index_has_title"] = "DevBox Console" in client.get("/", headers=auth).text
    results["boxes_auth"] = client.get("/api/boxes", headers=auth).status_code
    results["boxes_payload"] = client.get("/api/boxes", headers=auth).json()["boxes"][0]["kind"]
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
