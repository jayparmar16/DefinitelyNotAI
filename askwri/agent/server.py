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

    def do_GET(self):
        if self.path != "/ping":
            self.send_error(404)
            return
        self._json(200, {"status": "Healthy"})

    def do_POST(self):
        if self.path != "/invocations":
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if not (request.get("question") or "").strip():
            self._json(400, {"error": "question is required"})
            return
        request.setdefault("sessionId", self.headers.get(SESSION_HEADER, ""))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for event in self.agent.run(request):
                self._event(event)
        except Exception as error:  # the stream is already open: report the failure in it
            log.exception("run failed")
            self._event({"type": "error", "message": f"{type(error).__name__}: {error}"})

    def _event(self, event: dict) -> None:
        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
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
