"""The AgentCore Runtime HTTP contract on port 8080: GET /ping and POST /invocations.

/invocations streams the agent's events as server-sent events, one JSON object per "data:" line.
A failure mid-run is sent as a final {"type": "error"} event, after whatever was already shown.
"""

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3

from askwri.agent import llm
from askwri.agent.gateway import Gateway
from askwri.agent.loop import Agent, Deps, Settings
from askwri.agent.memory import Memory

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"
PADDING = 4096  # bytes of SSE comment after each "now" step (see _event)
log = logging.getLogger("askwri.agent")


def build_agent() -> Agent:
    """The agent wired to its real dependencies, configured from environment variables."""
    deps = Deps(
        llm=llm.client(),
        gateway=Gateway(),
        memory=Memory(),
        bedrock=boto3.client("bedrock-runtime"),
    )
    return Agent(deps, Settings.from_env())


class Handler(BaseHTTPRequestHandler):
    agent: Agent  # set by serve()
    # HTTP/1.1 chunked responses: AgentCore Runtime passes chunks on as they arrive, but holds an
    # HTTP/1.0 response (no length, ended by closing) until it is complete.
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        if self.path != "/ping":
            self.send_error(404)
            return
        self._json(200, {"status": "Healthy"})

    def do_POST(self):
        # Read the body first: on a reused (keep-alive) connection an unread body would be parsed
        # as the start of the next request.
        body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        if self.path != "/invocations":
            self.send_error(404)
            return
        request = json.loads(body or b"{}")
        if request.get("warmup"):
            # Sent while the user is still typing, so this session's runtime is up before they ask.
            self._json(200, {"status": "warm"})
            return
        if not (request.get("question") or "").strip():
            self._json(400, {"error": "question is required"})
            return
        request.setdefault("sessionId", self.headers.get(SESSION_HEADER, ""))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for event in self.agent.run(request):
                self._event(event)
        except Exception as error:  # the stream is already open: report the failure in it
            log.exception("run failed")
            self._event({"type": "error", "message": f"{type(error).__name__}: {error}"})
        self._chunk(b"")  # the empty chunk ends the response

    def _event(self, event: dict) -> None:
        self._chunk(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
        if event["type"] == "step" and event["status"] == "now":
            # shortcut: an SSE comment as padding - AgentCore Runtime appears to hold small
            # writes until more data follows, so a step's "now" arrived only with its "done".
            self._chunk(b":" + b" " * PADDING + b"\n\n")

    def _chunk(self, data: bytes) -> None:
        """Send one chunk of a chunked response; empty data ends it."""
        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):  # route access logs through logging, not stderr
        log.info(format, *args)


def serve(port: int = 8080) -> None:
    """Serve forever on 0.0.0.0:port, one thread per request."""
    logging.basicConfig(level=logging.INFO)
    Handler.agent = build_agent()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
