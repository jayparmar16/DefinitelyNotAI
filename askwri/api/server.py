"""HTTP routes: POST /chat (server-sent events), POST /warm, GET /sources/download?key=...,
GET /ping. /warm starts a session's agent runtime while the user is still typing.

Environment: ASKWRI_RUNTIME_ARN (the agent), ASKWRI_CORPUS_BUCKET (stored PDFs),
ASKWRI_ALLOWED_ORIGINS (comma-separated browser origins for CORS), ASKWRI_API_KEY_SECRET
(optional: when set, requests must send its value in the X-AskWRI-Key header), PORT (8080).
"""

import hmac
import json
import logging
import os
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import boto3
from botocore.exceptions import ClientError

DOWNLOAD_SECONDS = 300  # the design's 5-minute presigned link
SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{33,100}$")  # AgentCore runtime session IDs: 33+ chars
PDF_KEY = re.compile(r"^raw/[^/]+\.pdf$")
MODES, FORMATS = {"quick", "deep"}, {"summary", "issue-brief", "talking-points"}
log = logging.getLogger("askwri.api")
STARTING_RETRIES, STARTING_WAIT_SECONDS = 4, 2


def invoke_agent(agentcore, *, sleep=time.sleep, **request) -> dict:
    """InvokeAgentRuntime, retried while the session's runtime is still starting.

    A call that arrives while another call (the UI's warm-up) is starting the same session's
    runtime gets a 502 from it. Nothing has been sent to the browser yet, so retrying is safe.
    """
    for attempt in range(STARTING_RETRIES):
        try:
            return agentcore.invoke_agent_runtime(**request)
        except ClientError as error:
            starting = error.response["Error"]["Code"] == "RuntimeClientError" and "(502)" in str(
                error
            )
            if not starting or attempt == STARTING_RETRIES - 1:
                raise
            log.info("runtime still starting; retry %d", attempt + 1)
            sleep(STARTING_WAIT_SECONDS)
    raise AssertionError("unreachable")


class BadRequest(Exception):
    """The request can't be served; the message is safe to show the caller."""


def chat_payload(body: dict) -> dict:
    """Validate a chat request (the UI's AskRequest) and return the agent payload.

    A missing or malformed session ID gets a fresh one, so the agent always has a session.
    """
    question = (body.get("question") or "").strip()
    if not question or len(question) > 4000:
        raise BadRequest("question must be 1 to 4000 characters")
    session = body.get("sessionId") or ""
    if not SESSION_ID.match(session):
        session = f"askwri-{uuid.uuid4()}"
    filters = body.get("filters") or {}
    return {
        "question": question,
        "mode": body.get("mode") if body.get("mode") in MODES else "quick",
        "language": str(body.get("language") or "en")[:5],
        "audience": str(body.get("audience") or "auto")[:40],
        "format": body.get("format") if body.get("format") in FORMATS else "summary",
        "filters": {k: filters[k] for k in ("yearFrom", "pubType") if filters.get(k)},
        "sessionId": session,
    }


def warm_session(body: dict) -> str:
    """The session ID to warm up; it must already be a valid runtime session ID."""
    session = body.get("sessionId") or ""
    if not SESSION_ID.match(session):
        raise BadRequest("sessionId must be 33 to 100 letters, digits, '-' or '_'")
    return session


def download_key(query: str) -> str:
    """The stored-PDF key from ?key=..., refusing anything outside raw/*.pdf."""
    key = (parse_qs(query).get("key") or [""])[0]
    if not PDF_KEY.match(key) or ".." in key:
        raise BadRequest("key must name a stored PDF under raw/")
    return key


def key_matches(expected: str | None, sent: str | None) -> bool:
    """True when no key is required, or the sent key equals it (constant-time compare)."""
    return expected is None or (sent is not None and hmac.compare_digest(expected, sent))


class Api:
    """The API's AWS clients and settings, built once per process."""

    def __init__(self):
        self.runtime_arn = os.environ["ASKWRI_RUNTIME_ARN"]
        self.bucket = os.environ["ASKWRI_CORPUS_BUCKET"]
        self.origins = {
            o.strip() for o in os.environ.get("ASKWRI_ALLOWED_ORIGINS", "").split(",") if o.strip()
        }
        self.agentcore = boto3.client("bedrock-agentcore")
        self.s3 = boto3.client("s3")
        secret = os.environ.get("ASKWRI_API_KEY_SECRET")
        self.api_key = (
            boto3.client("secretsmanager").get_secret_value(SecretId=secret)["SecretString"]
            if secret
            else None
        )


class Handler(BaseHTTPRequestHandler):
    api: Api  # set by serve()
    # HTTP/1.1 chunked responses stream through the Lambda Web Adapter; HTTP/1.0 ones are held
    # until they end.
    protocol_version = "HTTP/1.1"

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin and origin in self.api.origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        if key_matches(self.api.api_key, self.headers.get("X-AskWRI-Key")):
            return True
        self._json(401, {"error": "missing or wrong X-AskWRI-Key"})
        return False

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-AskWRI-Key")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/ping":
            self._json(200, {"status": "Healthy"})
            return
        if url.path != "/sources/download":
            self._json(404, {"error": "not found"})
            return
        if not self._authorized():
            return
        try:
            key = download_key(url.query)
        except BadRequest as error:
            self._json(400, {"error": str(error)})
            return
        # Served as an inline PDF so the UI's side panel can show the cited page; PDFs loaded
        # before load.py set a content type are stored as binary/octet-stream.
        params = {
            "Bucket": self.api.bucket,
            "Key": key,
            "ResponseContentType": "application/pdf",
            "ResponseContentDisposition": "inline",
        }
        link = self.api.s3.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=DOWNLOAD_SECONDS
        )
        self._json(200, {"url": link, "expiresIn": DOWNLOAD_SECONDS})

    def do_POST(self):
        # Read the body before any early answer: connections are reused (HTTP/1.1 keep-alive),
        # and an unread body would be parsed as the start of the next request.
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length)
        path = urlsplit(self.path).path
        if path not in ("/chat", "/warm"):
            self._json(404, {"error": "not found"})
            return
        if not self._authorized():
            return
        if path == "/warm":
            self._warm(body)
            return
        try:
            if length > 100_000:
                raise BadRequest("request body too large")
            payload = chat_payload(json.loads(body or b"{}"))
        except (BadRequest, ValueError) as error:
            self._json(400, {"error": str(error)})
            return
        try:
            response = invoke_agent(
                self.api.agentcore,
                agentRuntimeArn=self.api.runtime_arn,
                runtimeSessionId=payload["sessionId"],
                payload=json.dumps(payload).encode(),
            )
        except ClientError as error:
            # Answer with CORS headers, or the browser only reports "Failed to fetch".
            log.error("agent call failed: %s", error)
            self._json(502, {"error": "The AskWRI agent didn't answer. Please try again."})
            return
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        # The agent already sends server-sent events: forward each event (its lines up to the
        # blank line that ends it) as one chunk, as soon as it arrives.
        event = b""
        # chunk_size=1: a bigger read waits until that many bytes arrive, which holds back the
        # end of each small event until the next one starts. These streams are a few kB.
        for line in response["response"].iter_lines(chunk_size=1):
            event += line + b"\n"
            if not line:
                self._chunk(event)
                event = b""
        if event:
            self._chunk(event)
        self._chunk(b"")  # the empty chunk ends the response

    def _warm(self, body: bytes) -> None:
        """Start the agent runtime for a session; answers once it is up (cold start ~6-9 s)."""
        try:
            session = warm_session(json.loads(body or b"{}"))
        except (BadRequest, ValueError) as error:
            self._json(400, {"error": str(error)})
            return
        try:
            response = invoke_agent(
                self.api.agentcore,
                agentRuntimeArn=self.api.runtime_arn,
                runtimeSessionId=session,
                payload=json.dumps({"warmup": True}).encode(),
            )
        except ClientError as error:
            log.error("warm-up failed: %s", error)
            self._json(502, {"error": "warm-up failed"})
            return
        response["response"].read()
        self._json(200, {"status": "warm"})

    def _chunk(self, data: bytes) -> None:
        """Send one chunk of a chunked response; empty data ends it."""
        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def log_message(self, format, *args):
        log.info(format, *args)


def serve() -> None:
    """Serve on PORT (default 8080), one thread per request."""
    logging.basicConfig(level=logging.INFO)
    Handler.api = Api()
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
