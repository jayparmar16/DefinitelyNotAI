"""Record the demo chats: ask each use-case question on the deployed API and save what it streams.

`AWS_PROFILE=<team profile> uv run python scripts/record_demo_chats.py > web/public/demo-chats.json`
Opening the UI at /?demo=load replaces that browser's chats with these, titled by use case, so a
short demo can open finished answers instead of waiting for each. Uses the server key (Secrets
Manager askwri/api-key) and marks the traffic as eval, so it stays out of the live numbers.
"""

import json
import subprocess
import sys
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

import boto3

# (title, space, mode, question, extra request fields); the order is the sidebar's.
CHATS = [
    ("1 · Every claim verified, cited to the page", None, "quick",
     "How should civil society track adaptation finance?", {}),
    ("2 · Written for a funder, no persona picked", None, "quick",
     "Give me points I can use with a funder on why invest in restoring degraded land", {}),
    ("3 · Policy brief in seconds", None, "deep",
     "Methane mitigation in agriculture", {"format": "issue-brief"}),
    ("4 · Won't make things up", None, "quick",
     "Why did WRI conclude that electric vehicles increase urban air pollution?", {}),
    ("5 · Fact-check a draft", None, "factcheck",
     ("WRI found that 281 of 394 European cities did not meet the 2030 air quality standards, "
     "and that transport is the main source of pollution."), {}),
    ("6 · Ask in Spanish, cite in the original", None, "quick",
     "¿Qué recomienda WRI para reducir el calor extremo en las ciudades?", {}),
    ("7 · How WRI's research connects", None, "explore", "adaptation finance", {}),
    ("8 · Compare 8 papers at once", None, "deep",
     "Adaptation finance accountability", {"format": "dossier"}),
    ("Ocean · what WRI published in 2025", "Ocean", "quick",
     "What did WRI publish in 2025 on ocean?", {}),
]  # fmt: skip
FINAL = {"answer", "decline", "factcheck", "visuals"}


def api_url() -> str:
    """The deployed API's URL, from Terraform's outputs."""
    out = subprocess.run(
        ["terraform", "-chdir=infra", "output", "-raw", "api_url"],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return out.stdout.strip().rstrip("/")


def stream(api: str, key: str, body: dict) -> list[dict]:
    """Every event the API streams for one request."""
    request = urllib.request.Request(
        f"{api}/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-AskWRI-Key": key},
    )
    events = []
    with urllib.request.urlopen(request, timeout=300) as response:
        for line in response:
            line = line.decode().strip()
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def record(api: str, key: str, chat: tuple) -> dict:
    """One demo chat: its question's events, plus the visuals for an answer (ready to open)."""
    title, space, mode, question, extra = chat
    session = f"askwri-demo-{uuid.uuid4()}"
    base = {"language": "en", "audience": "auto", "format": "summary", "sessionId": session,
            "source": "eval", "filters": {"topic": space} if space else {}}  # fmt: skip
    events = stream(api, key, {**base, "question": question, "mode": mode, **extra})
    final = next((e for e in reversed(events) if e.get("type") in FINAL), None)
    if final is None:
        raise RuntimeError(f"{title}: no answer came back: {events[-1:]}")
    if final["type"] == "answer" and mode != "deep":
        answer = final["answer"]
        shown = {"paragraphs": answer["paragraphs"], "sources": answer["sources"]}
        drawn = stream(api, key, {**base, "question": question, "mode": "visuals", "answer": shown})
        events += [e for e in drawn if e.get("type") == "visuals"]
    print(f"{title}: {final['type']}", file=sys.stderr, flush=True)
    return {"title": title, "space": space, "sessionId": session, "question": question,
            "mode": "deep" if mode == "deep" else mode, "events": events}  # fmt: skip


def main() -> int:
    key = boto3.client("secretsmanager").get_secret_value(SecretId="askwri/api-key")["SecretString"]
    api = api_url()
    with ThreadPoolExecutor(3) as pool:
        chats = list(pool.map(lambda chat: record(api, key, chat), CHATS))
    json.dump({"chats": chats}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
