"""
EXA Search Proxy for llama.cpp Research Center.

Transparent reverse proxy that sits between the WebUI browser and llama-server,
intercepting /v1/chat/completions to inject tool definitions and handle
function calling for EXA web search automatically.

Architecture:
  Browser -> EXA Proxy (:8081) -> llama-server (:8080)
                                     |
                              exa_helper.search_web()
"""

import json
import http.server
import urllib.request
import urllib.error
import threading
from typing import Optional

from exa_helper import search_web, EXA_SEARCH_TOOL

LLAMA_TARGET = "http://127.0.0.1:8080"
PROXY_PORT = 8081


class EXAProxyHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self._proxy_transparent("GET")

    def do_HEAD(self):
        self._proxy_transparent("HEAD")

    def do_DELETE(self):
        self._proxy_transparent("DELETE")

    def do_PATCH(self):
        self._proxy_transparent("PATCH")

    def do_PUT(self):
        self._proxy_transparent("PUT")

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            self._handle_chat_completion()
        else:
            self._proxy_transparent("POST")

    def _handle_chat_completion(self):
        """Inject EXA tools, proxy to llama-server, execute any tool calls, and return final response."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            request_data = json.loads(body)
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON in request body")
            return

        client_wants_stream = request_data.get("stream", False)
        request_data["tools"] = [EXA_SEARCH_TOOL]
        request_data["tool_choice"] = "auto"
        request_data["stream"] = False

        response_data = self._forward_to_llama(request_data)
        if response_data is None:
            self._send_error(502, "llama-server upstream error on first pass")
            return

        tool_calls = self._extract_tool_calls(response_data)
        if tool_calls:
            response_data = self._execute_tool_loop(request_data, response_data, tool_calls)

        self._send_response_to_client(response_data, client_wants_stream)

    def _execute_tool_loop(
        self,
        request_data: dict,
        response_data: dict,
        tool_calls: list,
        max_turns: int = 5,
    ) -> dict:
        messages = list(request_data.get("messages", []))
        current_tool_calls = tool_calls
        current_response = response_data

        for turn in range(max_turns):
            assistant_msg = current_response["choices"][0].get("message", {})
            if assistant_msg:
                messages.append(assistant_msg)

            has_results = False
            for tc in current_tool_calls:
                result = self._execute_single_tool(tc)
                if result is not None:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", "call_unknown"),
                        "content": result,
                    })
                    has_results = True

            if not has_results:
                break

            updated_request = dict(request_data)
            updated_request["messages"] = messages
            current_response = self._forward_to_llama(updated_request)
            if current_response is None:
                return {"error": "Upstream error during tool loop"}

            current_tool_calls = self._extract_tool_calls(current_response)
            if not current_tool_calls:
                break

        return current_response

    def _extract_tool_calls(self, response_data: dict) -> list:
        try:
            message = response_data["choices"][0]["message"]
            return message.get("tool_calls", [])
        except (KeyError, IndexError, TypeError):
            return []

    def _execute_single_tool(self, tool_call: dict) -> Optional[str]:
        try:
            func = tool_call.get("function", {})
            func_name = func.get("name", "")
            raw_args = func.get("arguments", "{}")

            if isinstance(raw_args, str):
                arguments = json.loads(raw_args)
            else:
                arguments = raw_args

            if func_name == "web_search":
                query = arguments.get("query", "")
                num_results = arguments.get("num_results", 5)
                print(f"  [Proxy] web_search(query='{query[:60]}...')")
                return search_web(query, num_results=num_results)

            return f"Unknown tool: {func_name}. Available tools: web_search"

        except json.JSONDecodeError:
            return f"Error: could not parse tool arguments: {raw_args}"
        except Exception as e:
            return f"Error executing tool: {str(e)}"

    def _forward_to_llama(self, data: dict) -> Optional[dict]:
        url = f"{LLAMA_TARGET}{self.path}"
        body = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"  [Proxy] Upstream HTTP {e.code}: {e.reason}")
            return None
        except urllib.error.URLError as e:
            print(f"  [Proxy] Upstream URL error: {e.reason}")
            return None
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"  [Proxy] Upstream error: {e}")
            return None

    def _send_response_to_client(self, response_data: dict, stream: bool):
        if stream:
            self._send_sse_response(response_data)
        else:
            self._send_json_response(response_data)

    def _send_json_response(self, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_sse_response(self, data: dict):
        """Convert buffered non-streaming response to SSE for stream=True clients."""
        content = ""
        finish_reason = "stop"
        try:
            content = data["choices"][0]["message"].get("content", "")
            finish_reason = data["choices"][0]["finish_reason"]
        except (KeyError, IndexError):
            pass

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if content:
            chunk = json.dumps({
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }]
            }, ensure_ascii=False)
            self.wfile.write(f"data: {chunk}\n\n".encode("utf-8"))

        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _send_error(self, code: int, message: str):
        body = json.dumps({"error": {"message": message, "type": "proxy_error"}}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _proxy_transparent(self, method: str):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        url = f"{LLAMA_TARGET}{self.path}"
        req = urllib.request.Request(url, data=body, method=method)

        for header_name in [
            "Content-Type", "Accept", "Accept-Encoding", "Authorization",
            "If-None-Match", "If-Modified-Since", "Range",
        ]:
            if header_name in self.headers:
                req.add_header(header_name, self.headers[header_name])

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for header_name in [
                    "Content-Type", "Content-Length", "Content-Encoding",
                    "Cache-Control", "Etag", "Last-Modified", "Accept-Ranges",
                    "Access-Control-Allow-Origin",
                ]:
                    if header_name in resp.headers:
                        self.send_header(header_name, resp.headers[header_name])
                self.end_headers()
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                self.wfile.flush()

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            body_content = e.read()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body_content)))
            self.end_headers()
            self.wfile.write(body_content)

        except urllib.error.URLError as e:
            self._send_error(502, f"Upstream connection error: {e.reason}")
        except (OSError, ConnectionError) as e:
            self._send_error(502, f"Proxy error: {str(e)}")


def start_exa_proxy(
    port: int = PROXY_PORT,
    target_port: int = 8080,
    daemon: bool = True,
) -> threading.Thread:
    """
    Start the EXA Search proxy server in a background thread.

    Args:
        port: Port for the proxy to listen on (default: 8081).
        target_port: Port of the llama-server instance (default: 8080).
        daemon: Whether the thread should be a daemon.

    Returns:
        The background thread running the proxy server.
    """
    global LLAMA_TARGET
    LLAMA_TARGET = f"http://127.0.0.1:{target_port}"

    server = http.server.ThreadingHTTPServer(
        ("0.0.0.0", port),
        EXAProxyHandler,
    )

    thread = threading.Thread(
        target=server.serve_forever,
        daemon=daemon,
        name="exa-proxy",
    )
    thread.start()

    print(f"  [Proxy] EXA Search active on port {port} -> llama-server:{target_port}")
    return thread
