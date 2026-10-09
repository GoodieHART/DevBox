"""Structural tests for the Hermes gateway + dashboard app.

Same convention as test_opencode.py: hermes_app.py performs Modal
Volume/Secret lookups at import time, so verify it by AST + source
inspection instead of importing it.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _tree(name):
    return ast.parse(_source(name))


def _top_level_names(name):
    return {n.name for n in ast.walk(_tree(name)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))} | {
        t.id for n in ast.walk(_tree(name)) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)
    }


def test_hermes_app_structure():
    names = _top_level_names("hermes_app.py")
    for expected in ("gateway", "route", "start_proxy", "app", "hermes_image", "hermes_volume", "HERMES_VOLUME_NAME"):
        assert expected in names


def test_dedicated_volume_isolated_from_devbox():
    src = _source("hermes_app.py")
    assert 'HERMES_VOLUME_NAME = "my-dev-volume"' in src
    assert "Volume.from_name(HERMES_VOLUME_NAME" in src
    assert "DEV_VOLUME_NAME" not in src
    assert 'HERMES_HOME = "/root/.hermes"' in src
    assert 'volumes={HERMES_HOME: hermes_volume}' in src


def test_singleton_guards():
    src = _source("hermes_app.py")
    assert "max_containers=1" in src
    assert "max_inputs=1" in src


def test_single_port_proxy_layout():
    src = _source("hermes_app.py")
    assert "PROXY_PORT" in src
    assert "@modal.web_server(PROXY_PORT)" in src
    assert 'API_PREFIX = "/gateway"' in src
    # Both backends must be children of THIS container (no split-container
    # dashboard: Modal functions share neither PID nor network namespace)
    assert '"hermes", "gateway", "run"' in src
    assert '"hermes", "dashboard"' in src
    assert "--no-open" in src
    assert "threading.Thread(target=supervise, daemon=True).start()" in src


def test_source_installed_clean_image():
    src = _source("hermes_app.py")
    assert "modal.Image.debian_slim(python_version=\"3.11\")" in src
    assert 'apt_install("git")' in src
    assert "git clone --depth 1 https://github.com/NousResearch/hermes-agent.git" in src
    assert "HERMES_NIX_BUILD=1 python -m pip install -e" in src
    assert '"ruamel.yaml"' in src
    assert '"python-dotenv"' in src


def test_proxy_routing_rules_in_source():
    src = _source("hermes_app.py")
    # prefix strip with boundary check so /gatewayfoo stays on the dashboard
    assert 'API_PREFIX + "/"' in src
    # error statuses forwarded (HTTPError), unreachable backends become 502
    assert "HTTPError" in src
    assert "502" in src
    # websocket upgrades rejected with a clear status, not hung
    assert "501" in src
    # gateway redirects rewritten to stay inside /gateway
    assert "location" in src
    # proxy must NOT follow backend redirects internally, or Location
    # rewriting never fires (browser must resolve the next hop itself)
    assert "_NoRedirect" in src
    assert "_direct_opener.open" in src


def test_no_proxy_auth_breaking_openai_clients():
    src = _source("hermes_app.py")
    # Modal-Key headers would lock out stock OpenAI clients; the kwarg must
    # never be *enabled* (docstring may discuss it, code must not set it)
    assert "requires_proxy_auth=True" not in src


def test_readiness_accepts_http_errors_below_500():
    src = _source("hermes_app.py")
    assert "socket.create_connection((\"127.0.0.1\", port), timeout=2)" in src
