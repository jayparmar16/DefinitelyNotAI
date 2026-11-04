"""Calls the gateway's tools over MCP (JSON-RPC over HTTPS) with a Cognito access token.

Reads ASKWRI_GATEWAY_URL and ASKWRI_GATEWAY_SECRET (the Secrets Manager secret with the client
ID, client secret, token URL and scope). Tokens are cached until a minute before they expire.
"""

import base64
import json
import os
import time
import urllib.parse
import urllib.request

import boto3

from askwri.agent.tracing import finish_tool_span, tool_span

# The gateway names each tool "<target>___<tool>".
TOOL_NAMES = {
    "search": "search___search",
    "get_passage": "get-passage___get_passage",
    "coverage": "coverage___coverage",
    "authors": "authors___authors",
    "translate": "translate___translate",
    "links": "links___links",
}
TIMEOUT = 120  # seconds; a tool may wait for Aurora to resume from auto-pause


class ToolError(Exception):
    """A tool call failed; the message names the tool and the gateway's error text."""


def parse_mcp_reply(raw: str) -> dict:
    """The JSON-RPC message from a reply sent as JSON or as server-sent events."""
    if raw.lstrip().startswith("{"):
        return json.loads(raw)
    data = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
    if not data:
        raise ToolError(f"gateway reply has no data: {raw[:200]!r}")
    return json.loads(data[-1])


def tool_result(tool: str, message: dict) -> dict:
    """The tool's JSON result from a tools/call reply; raises ToolError for any error."""
    if "error" in message:
        raise ToolError(f"{tool}: {message['error'].get('message', message['error'])}")
    result = message["result"]
    text = "".join(part.get("text", "") for part in result.get("content", []))
    if result.get("isError"):
        raise ToolError(f"{tool}: {text[:500]}")
    return json.loads(text)


class Gateway:
    """MCP client for askwri-gateway."""

    def __init__(self, secrets_client=None):
        self._url = os.environ["ASKWRI_GATEWAY_URL"]
        self._secret_id = os.environ["ASKWRI_GATEWAY_SECRET"]
        self._secrets = secrets_client or boto3.client("secretsmanager")
        self._token, self._expires = None, 0.0
        self._next_id = 0

    def _bearer(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        secret = json.loads(
            self._secrets.get_secret_value(SecretId=self._secret_id)["SecretString"]
        )
        basic = base64.b64encode(f"{secret['client_id']}:{secret['client_secret']}".encode())
        body = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": secret["scope"]}
        ).encode()
        request = urllib.request.Request(
            secret["token_url"],
            data=body,
            headers={
                "Authorization": f"Basic {basic.decode()}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            token = json.loads(response.read())
        self._token, self._expires = token["access_token"], time.time() + token["expires_in"]
        return self._token

    def call(self, tool: str, arguments: dict) -> dict:
        """Call one tool (search, get_passage, coverage, authors, translate); returns its JSON."""
        self._next_id += 1
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": self._next_id,
                "method": "tools/call",
                "params": {"name": TOOL_NAMES[tool], "arguments": arguments},
            }
        ).encode()
        request = urllib.request.Request(
            self._url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._bearer()}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
        with tool_span(tool, arguments) as span:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                result = tool_result(tool, parse_mcp_reply(response.read().decode()))
            finish_tool_span(span, result)
        return result
