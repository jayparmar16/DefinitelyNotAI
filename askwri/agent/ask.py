"""Ask the agent a question from the terminal and print its progress and cited answer.

`uv run python -m askwri.agent.ask "question" [--deep] [--language es] [--session ID]`
calls the deployed runtime askwri_agent; add `--local` to call a local server on port 8080.
Reuse --session to ask a follow-up in the same conversation.
"""

import argparse
import json
import sys
import urllib.request
import uuid

import boto3

RUNTIME_NAME = "askwri_agent"


def runtime_arn() -> str:
    """ARN of the deployed askwri_agent runtime."""
    control = boto3.client("bedrock-agentcore-control")
    for runtime in control.list_agent_runtimes()["agentRuntimes"]:
        if runtime["agentRuntimeName"] == RUNTIME_NAME:
            return runtime["agentRuntimeArn"]
    raise SystemExit(f"no agent runtime named {RUNTIME_NAME}")


def lines_remote(payload: dict, session: str):
    response = boto3.client("bedrock-agentcore").invoke_agent_runtime(
        agentRuntimeArn=runtime_arn(),
        runtimeSessionId=session,
        payload=json.dumps(payload).encode(),
    )
    for line in response["response"].iter_lines():
        yield line.decode()


def lines_local(payload: dict, session: str):
    request = urllib.request.Request(
        "http://localhost:8080/invocations",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session,
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        for line in response:
            yield line.decode().rstrip("\n")


def show(event: dict) -> None:
    """Print one event in a readable form."""
    kind = event["type"]
    if kind == "step" and event["status"] != "next":
        mark = "✓" if event["status"] == "done" else "…"
        detail = f"  ({event['detail']})" if event.get("detail") else ""
        print(f"  {mark} {event['label']}{detail}")
    elif kind == "source-found":
        print(f"    found: {event['title']} ({event.get('year') or 'n.d.'})")
    elif kind == "answer":
        answer = event["answer"]
        print(
            f"\nANSWER ({answer['mode']}, {answer['claimsVerified']} of {answer['claimsTotal']} "
            f"claims verified, {answer['elapsedSeconds']} s"
            f"{', machine-translated' if answer['machineTranslated'] else ''})\n"
        )
        print(f"  {answer.get('scope', '')}  [for: {answer.get('audience')}]\n")
        if answer.get("report"):
            print(f"  {answer['report']['title']}\n  {answer['report']['builtFrom']}\n")
        for paragraph in answer["paragraphs"]:
            print(f"  {paragraph}\n")
        sections = [
            ("POSSIBLE IMPLICATIONS (AskWRI's interpretation, not WRI findings)", "implications"),
            ("WHAT THIS CAN'T TELL YOU", "limits"),
            ("QUESTIONS TO EXPLORE", "questions"),
            ("REMOVED (not supported by the sources)", "removedClaims"),
        ]
        for heading, field in sections:
            if answer.get(field):
                print(heading)
                for item in answer[field]:
                    print(f"  - {item}")
                print()
        print("SOURCES")
        for s in answer["sources"]:
            print(
                f"  [{s['marker']}] {s['title']} · {s['pubType']} · {s.get('year') or 'n.d.'} · "
                f"p. {s.get('printedPage') or s['page']}"
            )
            if s.get("authors"):
                print(f"      authors: {', '.join(s['authors'][:4])}")
        if answer.get("report", {}) and answer["report"].get("thinEvidence"):
            print("\nWHERE THE EVIDENCE IS THIN")
            for gap in answer["report"]["thinEvidence"]:
                print(f"  - {gap}")
    elif kind == "decline":
        decline = event["decline"]
        print(f"\nDECLINED: {decline['message']}\n  searched: {', '.join(decline['searched'])}")
        for item in decline["related"]:
            print(f"  closest: {item['title']} ({item.get('year') or 'n.d.'})")
    elif kind == "error":
        print(f"\nERROR: {event['message']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--deep", action="store_true", help="Deep research instead of Quick answer")
    parser.add_argument("--language", default="en")
    parser.add_argument("--session", default=None, help="reuse to ask a follow-up")
    parser.add_argument(
        "--audience",
        default="auto",
        choices=["auto", "researcher", "policymaker", "partnerships"],
        help="auto (default): the agent infers the reader from the question",
    )
    parser.add_argument("--local", action="store_true", help="call a server on localhost:8080")
    args = parser.parse_args()

    session = args.session or f"askwri-cli-{uuid.uuid4()}"  # runtime session IDs: 33+ characters
    payload = {
        "question": args.question,
        "mode": "deep" if args.deep else "quick",
        "language": args.language,
        "audience": args.audience,
        "format": "summary",
        "filters": {},
        "sessionId": session,
    }
    print(f"session: {session}")
    lines = lines_local if args.local else lines_remote
    for line in lines(payload, session):
        if line.startswith("data:"):
            show(json.loads(line[5:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
