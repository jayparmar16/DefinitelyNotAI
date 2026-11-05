"""Evaluate AskWRI end to end on the test set, then have AgentCore judge the same traces.

    uv run python -m eval.run_eval run [--testset eval/testset.jsonl] [--only F01,U02]
    uv run python -m eval.run_eval judge <run id>      # a few minutes later: traces must be indexed

`run` asks every question through the deployed API (marked as eval traffic), scores the answers
against the test set, writes eval/results/<run id>.json, copies it to the corpus bucket under
eval/results/ and sends the scores to CloudWatch (AskWRI/Eval). `judge` starts an AgentCore batch
evaluation of the run's sessions with the built-in judges, using the test set's figures as
ground-truth assertions, and adds the judged averages to the results. Needs ASKWRI_API_URL and
the team AWS profile; the API key is read from Secrets Manager (askwri/api-key).
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3

RESULTS = Path("eval/results")
NAMESPACE = "AskWRI/Eval"
JUDGES = [
    "Builtin.Correctness",
    "Builtin.Faithfulness",
    "Builtin.Helpfulness",
    "Builtin.ResponseRelevance",
    "Builtin.Refusal",
]
AGENT_SERVICE = "askwri_agent.DEFAULT"  # service.name on the agent's spans
SPANS_LOG_GROUP = "aws/spans"  # where Transaction Search indexes spans
WORKERS = 3  # questions at once; the API allows 5 concurrent requests


# --- asking ---


def ask(api: str, key: str, payload: dict) -> dict:
    """One question through the API; returns the final event, its usage and the seconds taken."""
    request = urllib.request.Request(
        api.rstrip("/") + "/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-AskWRI-Key": key},
    )
    started, final = time.monotonic(), None
    with urllib.request.urlopen(request, timeout=300) as response:
        for line in response:
            line = line.decode().strip()
            if line.startswith("data: "):
                event = json.loads(line[6:])
                if event["type"] in ("answer", "decline", "error"):
                    final = event
    return {"event": final, "seconds": round(time.monotonic() - started, 1)}


def payload(question: dict, session: str) -> dict:
    return {
        "question": question["question"],
        "mode": question.get("mode", "quick"),
        "language": "en",  # the answer follows the question's language on its own
        "audience": "auto",
        "format": "summary",
        "filters": question.get("filters") or {},
        "sessionId": session,
        "source": "eval",
    }


# --- scoring ---


def must_include_rate(text: str, wanted: list[str]) -> float | None:
    """Share of the expected figures and names found in the answer. Thousands separators are
    ignored ('1,000' == '1000'), and a number must match whole ('18' is not found in '181')."""
    if not wanted:
        return None

    def plain(value: str) -> str:
        return re.sub(r"(?<=\d),(?=\d{3})", "", value).lower().strip()

    answer = plain(text)
    found = 0
    for item in map(plain, wanted):
        if re.fullmatch(r"[\d.]+", item):
            found += bool(re.search(rf"(?<![\d.]){re.escape(item)}(?!\d)", answer))
        else:
            found += item in answer
    return found / len(wanted)


def figures_cited(paragraphs: list[str]) -> float | None:
    """Share of answer sentences stating a figure that carry an [n] citation: every factual
    claim must be cited, and a sentence with a number is always factual."""
    sentences = [s for p in paragraphs for s in re.split(r"(?<=[.!?])\s+", p)]
    with_figures = [s for s in sentences if re.search(r"\d", re.sub(r"\[\d+\]", "", s))]
    if not with_figures:
        return None
    return sum(bool(re.search(r"\[\d+\]", s)) for s in with_figures) / len(with_figures)


def score(question: dict, outcome: dict) -> dict:
    """Every metric for one question; None where a metric doesn't apply."""
    event = outcome["event"] or {"type": "error"}
    declined = event["type"] == "decline"
    row = {
        "id": question["id"],
        "category": question["category"],
        "mode": question.get("mode", "quick"),
        "answerable": question["answerable"],
        "outcome": event["type"],
        "declined": declined,
        "decline_correct": declined == (not question["answerable"]),
        "seconds": outcome["seconds"],
        "usage": event.get("usage"),
        "session": outcome["session"],
        "recall_at_5": None,
        "precision_at_5": None,
        "page_hit": None,
        "must_include": None,
        "figures_cited": None,
        "verified_rate": None,
        "audience_ok": None,
        "language_ok": None,
    }
    if event["type"] != "answer":
        return row
    answer = event["answer"]
    docs = list(dict.fromkeys(s["docId"] for s in answer["sources"]))[:5]
    expected = [s for s in question.get("expected_sources", []) if s.get("required", True)]
    if expected:
        wanted = {s["doc_id"] for s in expected}
        row["recall_at_5"] = len(wanted & set(docs)) / len(wanted)
        row["precision_at_5"] = len(wanted & set(docs)) / len(docs) if docs else 0.0
        row["page_hit"] = any(
            s["docId"] == e["doc_id"] and abs(s["page"] - e["pdf_page"]) <= 1
            for s in answer["sources"]
            for e in expected
        )
    text = " ".join(answer["paragraphs"])
    row["must_include"] = must_include_rate(text, question.get("must_include") or [])
    row["figures_cited"] = figures_cited(answer["paragraphs"])
    if answer.get("claimsTotal"):
        row["verified_rate"] = answer["claimsVerified"] / answer["claimsTotal"]
    row["audience_ok"] = answer.get("audience") == question.get("expected_audience")
    if question.get("language", "en") != "en":
        row["language_ok"] = answer.get("language") == question["language"]
    return row


def mean(rows: list[dict], key: str) -> float | None:
    values = [float(r[key]) for r in rows if r[key] is not None]
    return round(sum(values) / len(values), 3) if values else None


def median_seconds(rows: list[dict], mode: str) -> float | None:
    values = [r["seconds"] for r in rows if r["mode"] == mode and r["outcome"] != "error"]
    return round(statistics.median(values), 1) if values else None


def summarise(rows: list[dict]) -> dict:
    costs = [r["usage"]["estimatedCostUsd"] for r in rows if r.get("usage")]
    return {
        "questions": len(rows),
        "errors": sum(r["outcome"] == "error" for r in rows),
        "recall_at_5": mean(rows, "recall_at_5"),
        "precision_at_5": mean(rows, "precision_at_5"),
        "page_hit_rate": mean(rows, "page_hit"),
        "must_include_rate": mean(rows, "must_include"),
        "figures_cited_rate": mean(rows, "figures_cited"),
        "decline_accuracy": mean(rows, "decline_correct"),
        "unanswerable_declined": f"{sum(r['declined'] for r in rows if not r['answerable'])} of "
        f"{sum(not r['answerable'] for r in rows)}",
        "verified_rate": mean(rows, "verified_rate"),
        "audience_accuracy": mean(rows, "audience_ok"),
        "language_accuracy": mean(rows, "language_ok"),
        "median_seconds_quick": median_seconds(rows, "quick"),
        "median_seconds_deep": median_seconds(rows, "deep"),
        "estimated_cost_per_question_usd": round(sum(costs) / len(costs), 4) if costs else None,
        "by_category": {
            category: {
                "questions": len(group),
                "recall_at_5": mean(group, "recall_at_5"),
                "must_include_rate": mean(group, "must_include"),
                "decline_accuracy": mean(group, "decline_correct"),
            }
            for category in sorted({r["category"] for r in rows})
            for group in [[r for r in rows if r["category"] == category]]
        },
    }


# --- storing and publishing ---


METRICS = {
    "recall_at_5": ("RecallAt5", "None"),
    "precision_at_5": ("PrecisionAt5", "None"),
    "page_hit_rate": ("PageHitRate", "None"),
    "must_include_rate": ("MustIncludeRate", "None"),
    "figures_cited_rate": ("FiguresCitedRate", "None"),
    "decline_accuracy": ("DeclineAccuracy", "None"),
    "verified_rate": ("VerifiedRate", "None"),
    "audience_accuracy": ("AudienceAccuracy", "None"),
    "median_seconds_quick": ("MedianSecondsQuick", "Seconds"),
    "median_seconds_deep": ("MedianSecondsDeep", "Seconds"),
    "estimated_cost_per_question_usd": ("EstimatedCostPerQuestionUSD", "None"),
    "questions": ("Questions", "Count"),
}


def publish(summary: dict, when: datetime) -> None:
    """The run's scores as CloudWatch metrics, for the askwri-quality dashboard."""
    data = [
        {"MetricName": name, "Value": float(summary[key]), "Unit": unit, "Timestamp": when}
        for key, (name, unit) in METRICS.items()
        if summary.get(key) is not None
    ]
    boto3.client("cloudwatch").put_metric_data(Namespace=NAMESPACE, MetricData=data)


def save(run: dict) -> Path:
    """Write the run locally and to s3://askwri-corpus-<account>/eval/results/."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{run['run_id']}.json"
    path.write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")
    account = boto3.client("sts").get_caller_identity()["Account"]
    boto3.client("s3").upload_file(
        str(path), f"askwri-corpus-{account}", f"eval/results/{path.name}"
    )
    return path


# --- commands ---


def run(args) -> int:
    api = os.environ["ASKWRI_API_URL"]
    key = boto3.client("secretsmanager").get_secret_value(SecretId="askwri/api-key")["SecretString"]
    questions = [
        json.loads(line)
        for line in Path(args.testset).read_text("utf-8").splitlines()
        if line.strip()
    ]
    if args.only:
        questions = [q for q in questions if q["id"] in args.only.split(",")]
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    sessions = {
        q["id"]: f"askwri-eval-{run_id}-{q['id']}-{uuid.uuid4().hex[:8]}" for q in questions
    }
    for q in questions:  # a follow-up continues its first question's session
        if q.get("follow_up_of") in sessions:
            sessions[q["id"]] = sessions[q["follow_up_of"]]

    def one(question: dict) -> dict:
        session = sessions[question["id"]]
        try:
            outcome = ask(api, key, payload(question, session))
        except (OSError, ValueError) as error:  # network or stream failure: record it, go on
            outcome = {"event": {"type": "error", "message": str(error)[:300]}, "seconds": None}
        outcome["session"] = session
        row = score(question, outcome)
        print(
            f"{row['id']:<4} {row['outcome']:<8} recall={row['recall_at_5']} must={row['must_include']} "
            f"{row['seconds']}s",
            flush=True,
        )
        return row

    first = [q for q in questions if not q.get("follow_up_of")]
    follow = [q for q in questions if q.get("follow_up_of")]
    started = datetime.now(UTC)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows = list(pool.map(one, first))
    rows += [one(q) for q in follow]
    summary = summarise(rows)
    result = {
        "run_id": run_id,
        "started": started.isoformat(),
        "finished": datetime.now(UTC).isoformat(),
        "configuration": "C: agent loop + verify",
        "testset": args.testset,
        "summary": summary,
        "questions": rows,
        "judged": None,
    }
    path = save(result)
    publish(summary, datetime.now(UTC))
    print(json.dumps(summary, indent=1))
    print(f"saved {path}; judge it in a few minutes: uv run python -m eval.run_eval judge {run_id}")
    return 0


def judge(args) -> int:
    path = RESULTS / f"{args.run_id}.json"
    result = json.loads(path.read_text("utf-8"))
    testset = {
        q["id"]: q for q in map(json.loads, Path(result["testset"]).read_text("utf-8").splitlines())
    }
    started = datetime.fromisoformat(result["started"]) - timedelta(minutes=5)
    finished = datetime.fromisoformat(result["finished"]) + timedelta(minutes=5)
    rows = [r for r in result["questions"] if r["outcome"] != "error"]
    metadata = []
    for row in rows:
        question = testset[row["id"]]
        assertions = [
            {"text": f"The answer states {item}."} for item in question.get("must_include") or []
        ]
        if not question["answerable"]:
            assertions = [
                {"text": "The answer declines because WRI's publications don't cover this."}
            ]
        metadata.append(
            {
                "sessionId": row["session"],
                "testScenarioId": row["id"],
                "groundTruth": {
                    "inline": {
                        "turns": [{"input": {"prompt": question["question"]}}],
                        **({"assertions": assertions} if assertions else {}),
                    }
                },
                "metadata": {"category": question["category"]},
            }
        )
    agentcore = boto3.client("bedrock-agentcore")
    started_job = agentcore.start_batch_evaluation(
        batchEvaluationName=f"askwri_eval_{args.run_id.replace('-', '_')}",
        description=f"AskWRI evaluation run {args.run_id}",
        evaluators=[{"evaluatorId": e} for e in JUDGES],
        dataSourceConfig={
            "cloudWatchLogs": {
                "serviceNames": [AGENT_SERVICE],
                "logGroupNames": [SPANS_LOG_GROUP],
                "filterConfig": {
                    "sessionIds": [r["session"] for r in rows],
                    "timeRange": {"startTime": started, "endTime": finished},
                },
            }
        },
        evaluationMetadata={"sessionMetadata": metadata},
    )
    job = started_job["batchEvaluationId"]
    print(f"batch evaluation {job} started", flush=True)
    while True:
        state = agentcore.get_batch_evaluation(batchEvaluationId=job)
        if state["status"] not in ("PENDING", "IN_PROGRESS", "RUNNING", "STARTING"):
            break
        time.sleep(20)
    print("status:", state["status"], state.get("errorDetails") or "")
    result["judged"] = {
        "batch_evaluation_id": job,
        "status": state["status"],
        "evaluators": JUDGES,
        "results": state.get("evaluationResults"),
        "note": "Judged by AgentCore Evaluations' built-in judge models; spot-check by hand.",
    }
    save(result)
    print(json.dumps(state.get("evaluationResults"), indent=1, default=str)[:3000])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="ask every question and score the answers")
    run_parser.add_argument("--testset", default="eval/testset.jsonl")
    run_parser.add_argument("--only", help="comma-separated question ids")
    judge_parser = commands.add_parser("judge", help="AgentCore batch evaluation of a run")
    judge_parser.add_argument("run_id")
    args = parser.parse_args()
    return run(args) if args.command == "run" else judge(args)


if __name__ == "__main__":
    sys.exit(main())
