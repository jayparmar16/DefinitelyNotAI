"""The admin page's data: one query-log record per question, and the numbers built from them.

The API writes a record after every answer (askwri-query-log, DynamoDB). The admin page shows
the latest evaluation run (eval/results in the corpus bucket) next to live numbers from the log.
Nothing here invents a number: a value with no data is None, which the page shows as
"No data yet". Costs are estimated from tokens and a price table, and labelled so.
"""

import json
import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta

SANDBOX_CAP_USD = 500
WINDOWS = {"24h": 1, "7d": 7, "30d": 30}  # days
KINDS = ("Quick answer", "Quick answer with a retry", "Deep research", "Translated answer")


def kind(record: dict) -> str:
    """The question's kind for cost reporting (the dashboard spec's four, plus the tools)."""
    if record.get("translated"):
        return "Translated answer"
    if record["mode"] == "deep":
        return "Deep research"
    if record["mode"] == "factcheck":
        return "Fact-check"
    if record["mode"] in ("explore", "visuals"):
        return "Visuals and Explore"
    return "Quick answer with a retry" if record.get("rounds", 1) > 1 else "Quick answer"


def query_record(
    payload: dict, events: list[dict], seconds: float, now: datetime, rid: str
) -> dict:
    """What the log keeps about one question, from the request and the events streamed back."""
    final = next(
        (
            e
            for e in reversed(events)
            if e.get("type") in ("answer", "decline", "factcheck", "visuals")
        ),
        None,
    )
    rounds = max(
        (
            int(e["id"].rsplit("-", 1)[1])
            for e in events
            if e.get("type") == "step" and str(e.get("id", "")).startswith("search-")
        ),
        default=1,
    )
    record = {
        "id": rid,
        "ts": now.isoformat(),
        "source": payload.get("source", "user"),
        "session": payload.get("sessionId"),
        "question": payload["question"][:2000],
        "mode": payload.get("mode", "quick"),
        "rounds": rounds,
        "seconds": round(seconds, 1),
        "status": "error"
        if final is None
        else ("declined" if final["type"] == "decline" else "answered"),
        "usage": (final or {}).get("usage"),
        "translated": False,
        "audience": None,
        "claims_total": None,
        "claims_verified": None,
        "removed_claims": [],
        "paragraphs": [],
        "sources": [],
    }
    answer = (final or {}).get("answer")
    if answer:
        record |= {
            "translated": bool(answer.get("machineTranslated")),
            "language": answer.get("language"),
            "audience": answer.get("audience"),
            "claims_total": answer.get("claimsTotal"),
            "claims_verified": answer.get("claimsVerified"),
            "removed_claims": answer.get("removedClaims") or [],
            "paragraphs": answer.get("paragraphs", []),
            "sources": [
                {
                    "marker": s["marker"],
                    "title": s["title"],
                    "page": s["page"],
                    "url": s.get("url"),
                    "passage": s["passage"][:600],
                }
                for s in answer.get("sources", [])
            ],
        }
    record["kind"] = kind(record)
    return record


def cost(record: dict) -> float | None:
    return (record.get("usage") or {}).get("estimatedCostUsd")


def tokens(record: dict) -> int | None:
    used = record.get("usage")
    return used["tokensIn"] + used["tokensOut"] if used else None


def median(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 1) if values else None


def mean(values: list, digits: int = 4) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), digits) if values else None


def live(records: list[dict], window_records: list[dict], now: datetime) -> dict:
    """Sections 2 and 3: what questions cost and whether quality holds, for one window.
    `records` covers 30 days (for the cap and the 7-day token view), `window_records` the
    chosen window and traffic source."""
    costs = [cost(r) for r in window_records]
    priced = [c for c in costs if c is not None]
    spend_by_day: dict[str, dict] = defaultdict(
        lambda: {"cost_usd": 0.0, "tokens": 0, "questions": 0}
    )
    for r in window_records:
        day = spend_by_day[r["ts"][:10]]
        day["questions"] += 1
        day["cost_usd"] = round(day["cost_usd"] + (cost(r) or 0), 5)
        day["tokens"] += tokens(r) or 0
    total = sum(priced)
    by_kind = []
    for name in sorted({r["kind"] for r in window_records}):
        group = [cost(r) for r in window_records if r["kind"] == name and cost(r) is not None]
        if group:
            by_kind.append(
                {
                    "kind": name,
                    "questions": len(group),
                    "avg_cost_usd": mean(group, 5),
                    "share": round(sum(group) / total, 3) if total else None,
                }
            )
    week = [r for r in records if r["ts"] >= (now - timedelta(days=7)).isoformat()]
    by_step: dict[str, dict] = defaultdict(lambda: {"in": 0, "out": 0})
    for r in week:
        for step, used in ((r.get("usage") or {}).get("byStep") or {}).items():
            by_step[step]["in"] += used["in"]
            by_step[step]["out"] += used["out"]
    answered = [r for r in window_records if r["status"] != "error"]
    return {
        "questions": len(window_records),
        "cost_per_answer_usd": mean(priced, 5),
        "projected_per_1000_usd": round(mean(priced, 6) * 1000, 2) if priced else None,
        "tokens_per_answer_median": median([tokens(r) for r in window_records]),
        "spend_30d_usd": round(sum(c for c in map(cost, records) if c is not None), 2)
        if records
        else None,
        "sandbox_cap_usd": SANDBOX_CAP_USD,
        "spend_per_day": [{"day": d, **v} for d, v in sorted(spend_by_day.items())],
        "by_kind": by_kind,
        "tokens_by_step": [
            {"step": s, **v}
            for s, v in sorted(by_step.items(), key=lambda kv: -(kv[1]["in"] + kv[1]["out"]))
        ],
        "most_expensive": [
            {
                "id": r["id"],
                "question": r["question"][:200],
                "kind": r["kind"],
                "tokens": tokens(r),
                "cost_usd": cost(r),
            }
            for r in sorted(
                (r for r in window_records if cost(r) is not None), key=cost, reverse=True
            )[:5]
        ],
        "claims_removed_per_answer": mean([len(r["removed_claims"]) for r in answered], 2),
        "declined_share": round(sum(r["status"] == "declined" for r in answered) / len(answered), 3)
        if answered
        else None,
        "thumbs_down": None,  # the UI has no feedback buttons yet
        "median_seconds": {
            mode: median([r["seconds"] for r in answered if r["mode"] == mode])
            for mode in ("quick", "deep")
        },
    }


def scorecard(run: dict | None) -> dict | None:
    """Section 1 from the latest evaluation run (None before the first run)."""
    if not run:
        return None
    summary = run["summary"]
    return {
        "run_id": run["run_id"],
        "run_date": run["finished"],
        "configuration": run.get("configuration"),
        "questions": summary["questions"],
        "figures_cited_rate": summary.get("figures_cited_rate"),
        "recall_at_5": summary.get("recall_at_5"),
        "precision_at_5": summary.get("precision_at_5"),
        "unanswerable_declined": summary.get("unanswerable_declined"),
        "decline_accuracy": summary.get("decline_accuracy"),
        "must_include_rate": summary.get("must_include_rate"),
        "verified_rate": summary.get("verified_rate"),
        "audience_accuracy": summary.get("audience_accuracy"),
        "median_seconds_quick": summary.get("median_seconds_quick"),
        "median_seconds_deep": summary.get("median_seconds_deep"),
        "judged": bool(run.get("judged") and run["judged"].get("results")),
        "judges": judge_scores(run),
    }


def judge_scores(run: dict) -> dict[str, float] | None:
    """AgentCore Evaluations' average score per judge ("Faithfulness": 0.82), or None if unjudged."""
    results = (run.get("judged") or {}).get("results") or {}
    summaries = results.get("evaluatorSummaries") or []
    scores = {
        e["evaluatorId"].removeprefix("Builtin."): e["statistics"]["averageScore"]
        for e in summaries
        if e.get("statistics", {}).get("averageScore") is not None
    }
    return scores or None


def window_start(window: str, now: datetime) -> datetime:
    if window not in WINDOWS:
        raise ValueError(f"window must be one of {', '.join(WINDOWS)}")
    return now - timedelta(days=WINDOWS[window])


def days(start: datetime, now: datetime) -> list[str]:
    """The UTC dates from start to now: the log's partition keys to read."""
    out, day = [], start.date()
    while day <= now.date():
        out.append(day.isoformat())
        day += timedelta(days=1)
    return out


def item(record: dict) -> dict:
    """The DynamoDB item for a record: partitioned by UTC day, kept 90 days."""
    ts = datetime.fromisoformat(record["ts"])
    return {
        "day": record["ts"][:10],
        "sk": record["id"].split(".", 1)[1],
        "record": json.dumps(record, ensure_ascii=False),
        "expires": int((ts + timedelta(days=90)).timestamp()),
    }


def new_id(now: datetime, suffix: str) -> str:
    """'<day>.<time>-<suffix>': the day and sort key of the item, so review links find it."""
    return f"{now.date().isoformat()}.{now.strftime('%H%M%S%f')}-{suffix}"


def utc_now() -> datetime:
    return datetime.now(UTC)
