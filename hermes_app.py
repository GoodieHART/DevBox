"""Hermes gateway + dashboard as a SEPARATE Modal App on its own volume.

Why separate: Modal's unit of deployment is the App. Keeping Hermes out of
``devbox.py`` means DevBox boxes keep their own timeouts/idle kills while
Hermes gets its own image, schedule, and stable web URL.

Shared volume: mounts DevBox's ``my-dev-volume`` directly at Hermes's final
home path, ``/root/.hermes``. The clean Debian image avoids the prebuilt image's
non-empty home mount conflict, while direct mounting avoids nested volume-path
initialization failures. Hermes state shares the volume with DevBox files, so
avoid concurrent bulk writes to the volume while Hermes is checkpointing state.

Docker-image provision used: ``modal.Image.from_registry`` (no Docker daemon
involved -- Modal re-materializes the registry layers; see
https://modal.com/docs/guide/existing-images). Constraints honored:
linux/amd64 tag, ``.entrypoint([])`` override so Modal's runtime entrypoint
is the one that execs (Hermes dispatcher is bypassed; we invoke ``hermes``
directly), root execution (Modal always uid 0), no reliance on EXPOSE/VOLUME.

Single-port layout (Modal exposes ONE port per ``web_server`` function, and
Hermes only supports a split-container dashboard with shared PID/network,
which Modal functions don't have -- so both processes share this container
behind a stdlib reverse proxy):

    https://<ws>--hermes-gateway.modal.run/            -> dashboard (9119)
    https://<ws>--hermes-gateway.modal.run/gateway/... -> API server (8642, prefix stripped)

OpenAI-compatible clients: set base URL to ``.../gateway/v1``.

Ops rules (read before deploy):
- SINGLETON: ``max_containers=1`` + ``max_inputs=1``. Never run two gateway
  containers against one home -- session/memory stores corrupt (same rule as
  Hermes Docker docs for shared data dirs).
- SQLITE: set ``database.journal_mode: delete`` in the Hermes config. WAL
  needs co-located shm and is unsupported on network volumes.
- SHARED STORAGE: this app uses DevBox's ``my-dev-volume`` at a separate home
  path. Avoid concurrent bulk volume writes while the gateway checkpoints state.
- LIFECYCLE: ``modal deploy hermes_app.py`` (persistent URL). ``modal run``
  is ephemeral. Containers recycle at the 24h function cap; both processes
  re-read ``hermes-home/`` on boot (Telegram getUpdates resumes from stored
  offset; Discord websocket reconnects).
- NO ``requires_proxy_auth``: it demands Modal-Key/Modal-Secret headers that
  standard OpenAI clients cannot send. Auth stays at the app layer
  (``API_SERVER_KEY`` + dashboard basic auth below).

First-time setup (one-off, before first deploy):
    modal shell hermes_app.py   # then: HERMES_HOME=/root/.hermes hermes setup
or create the ``hermes-env`` secret below and let the gateway start cold.

Secrets: create ONE secret holding gateway + dashboard env:
    modal secret create hermes-env \\
        API_SERVER_ENABLED=true \\
        API_SERVER_HOST=0.0.0.0 \\
        API_SERVER_KEY="$(openssl rand -hex 32)" \\
        TELEGRAM_BOT_TOKEN="..."  # only the platforms you use
        HERMES_DASHBOARD_BASIC_AUTH_USERNAME="admin" \\
        HERMES_DASHBOARD_BASIC_AUTH_PASSWORD="<strong-password>" \\
        HERMES_DASHBOARD_BASIC_AUTH_SECRET="$(openssl rand -base64 32)"
Dashboard binds 0.0.0.0 (non-loopback), so Hermes fails closed without the
basic-auth provider -- there is no anonymous mode. Verify post-deploy:
    curl https://<url>/api/status  # auth_required:true, providers:["basic"]

Known limitation: WebSocket upgrades (dashboard chat tab) get HTTP 501
through the proxy -- plain HTTP views, sessions, and the OpenAI API work.
"""

import http.server
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

import modal

HERMES_VOLUME_NAME = "my-dev-volume"
HERMES_HOME = "/root/.hermes"
GATEWAY_PORT = 8642  # Hermes OpenAI-compatible API + health endpoint
DASH_PORT = 9119  # Hermes web dashboard
PROXY_PORT = 8000  # the ONE port Modal exposes; routes to both above
API_PREFIX = "/gateway"  # paths under here (prefix stripped) go to the API

app = modal.App(name="hermes-gateway")

hermes_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .run_commands(
        "git clone --depth 1 https://github.com/NousResearch/hermes-agent.git /opt/hermes-src",
        "cd /opt/hermes-src && HERMES_NIX_BUILD=1 python -m pip install -e '.[messaging,mcp,cron,cli]'",
    )
    .pip_install("modal>=1.0.0,<2", "ruamel.yaml", "python-dotenv")
)

hermes_volume = modal.Volume.from_name(HERMES_VOLUME_NAME, create_if_missing=True)
hermes_env = modal.Secret.from_name("hermes-env")

_HOP_BY_HOP = frozenset({
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow redirects internally: 3xx responses (with rewritten
    Location) must reach the client so the browser resolves the next hop
    against the proxy's own URL space."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN002, ANN202
        return None


_direct_opener = urllib.request.build_opener(_NoRedirect)


def route(path: str) -> tuple[int, str]:
    """Map a proxy path to ``(target_port, backend_path)``.

    ``/gateway`` and ``/gateway/...`` go to the API server with the prefix
    stripped; everything else (including lookalikes like ``/gatewayfoo``)
    goes to the dashboard.
    """
    if path == API_PREFIX or path.startswith(API_PREFIX + "/"):
        stripped = path[len(API_PREFIX):]
        return GATEWAY_PORT, stripped or "/"
    return DASH_PORT, path


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    """Minimal reverse proxy: stdlib only, streams bodies both ways."""

    server_version = "HermesProxy/1.0"

    def _forward(self) -> None:
        if "websocket" in self.headers.get("Upgrade", "").lower():
            self.send_error(501, "WebSocket upgrades are not supported "
                                 "through the single-port proxy")
            return
        target_port, backend_path = route(self.path)
        length = self.headers.get("Content-Length")
        body = self.rfile.read(int(length)) if length else None
        fwd_headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in _HOP_BY_HOP}
        fwd_headers["X-Forwarded-For"] = self.client_address[0]
        fwd_headers["X-Forwarded-Proto"] = "https"
        req = urllib.request.Request(
            f"http://127.0.0.1:{target_port}{backend_path}",
            data=body,
            headers=fwd_headers,
            method=self.command,
        )
        try:
            resp = _direct_opener.open(req, timeout=300)
        except urllib.error.HTTPError as e:
            resp = e  # forward backend error statuses, not 502s
        except Exception as e:
            self.send_error(502, f"backend unreachable: {e}")
            return
        status = getattr(resp, "status", None)
        if not isinstance(status, int):
            status = getattr(resp, "code", None)
        if not isinstance(status, int):
            status = 200
        self.send_response(status)
        for k, v in resp.headers.items():
            if k.lower() in _HOP_BY_HOP:
                continue
            if (status in (301, 302, 303, 307, 308)
                    and k.lower() == "location"
                    and target_port == GATEWAY_PORT
                    and v.startswith("/")):
                v = API_PREFIX + v  # keep API redirects inside /gateway
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            shutil.copyfileobj(resp, self.wfile)  # stream; SSE-safe

    do_GET = _forward
    do_POST = _forward
    do_PUT = _forward
    do_PATCH = _forward
    do_DELETE = _forward
    do_HEAD = _forward
    do_OPTIONS = _forward

    def log_message(self, format, *args):  # noqa: A002 - must match base signature
        pass  # container logs stay for gateway/dashboard, not proxy chatter


def start_proxy(port: int = PROXY_PORT):
    """Serve the reverse proxy in a daemon thread; returns the server."""
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), _ProxyHandler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True
    )
    thread.start()
    return server


def _wait_ready(port: int, path: str, attempts: int = 60) -> None:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}{path}", timeout=2
            ) as resp:
                if resp.status < 500:  # redirects (login gate) count as alive
                    return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"Hermes process on :{port}{path} never became ready")


@app.function(
    image=hermes_image,
    volumes={HERMES_HOME: hermes_volume},
    secrets=[hermes_env],
    timeout=86400,  # 24h platform cap; container recycles, state re-reads from volume
    min_containers=1,  # keep warm (requires `modal deploy`, costs idle)
    max_containers=1,  # singleton: two gateways on one home corrupts state
    scaledown_window=1200,
)
@modal.concurrent(max_inputs=1)
@modal.web_server(PROXY_PORT)
def gateway():
    """Run gateway + dashboard side by side behind the single-port proxy."""
    import os

    os.environ["HERMES_HOME"] = HERMES_HOME
    env = {**os.environ, "HERMES_HOME": HERMES_HOME}

    gw_proc = subprocess.Popen(
        ["hermes", "gateway", "run", "--external-supervisor"], env=env
    )
    dash_proc = subprocess.Popen(
        ["hermes", "dashboard", "--host", "0.0.0.0",
         "--port", str(DASH_PORT), "--no-open"],
        env=env,
    )
    _wait_ready(GATEWAY_PORT, "/")
    _wait_ready(DASH_PORT, "/api/status")

    proxy = start_proxy(PROXY_PORT)
    try:
        while True:  # supervise: either child dying recycles the container
            for name, proc in (("gateway", gw_proc), ("dashboard", dash_proc)):
                code = proc.poll()
                if code is not None:
                    # 75 = supervisor-restart request; any exit relaunches
                    # everything fresh on the replacement container.
                    raise RuntimeError(
                        f"Hermes {name} exited with code {code} -- recycling"
                    )
            time.sleep(5)
    finally:
        proxy.shutdown()
        for proc in (gw_proc, dash_proc):
            if proc.poll() is None:
                proc.terminate()
