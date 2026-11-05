"""Ask one Quick answer question from the command line and print each event as a JSON line.

uv run python -m askwri.answer "question" [--passages FILE]
"""

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

from askwri.answer.app import ask_events, payload_problem
from askwri.answer.quick import index_search
from askwri.answer.stream import stream_with_pings
from askwri.answer.verify import guardrail_grounding
from askwri.models import claude_client


def main() -> int:
    """Run one question and print its events; exit 1 if the run ends with an `error` event.

    Calls Claude on Bedrock, and the Guardrails check when `ASKWRI_GUARDRAIL_ID` is set.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument(
        "--passages",
        type=Path,
        help="JSON list of C1 passages that every search returns, instead of the Aurora index",
    )
    args = parser.parse_args()
    request = {
        "action": "ask",
        "question": args.question,
        "mode": "quick",
        "language": "en",
        "audience": "researcher",
        "format": "summary",
        "filters": {},
        "sessionId": f"cli-{uuid.uuid4()}",
    }
    problem = payload_problem(request)
    if problem:
        parser.error(problem)
    if args.passages:
        search = fixed_search(args.passages)
    else:
        try:
            import askwri.search  # noqa: F401
        except ImportError:
            parser.error("askwri.search (#19) isn't merged yet: pass --passages FILE")
        search = index_search

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    del request["action"]
    events = ask_events(
        request, search=search, client=claude_client(), grounding=guardrail_grounding()
    )
    last = None
    for event in stream_with_pings(events):
        print(json.dumps(event, ensure_ascii=False), flush=True)
        last = event
    return 1 if last and last["type"] == "error" else 0


def fixed_search(path: Path):
    """A search that returns the passages in `path` for every query, best score first."""
    passages = [SimpleNamespace(**fields) for fields in json.loads(path.read_text())]
    for p in passages:
        p.authors = tuple(p.authors)
    passages.sort(key=lambda p: p.score, reverse=True)
    return lambda query, filters: passages


if __name__ == "__main__":
    sys.exit(main())
