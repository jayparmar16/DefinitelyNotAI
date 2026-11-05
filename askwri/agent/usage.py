"""What each answer used: tokens per step and model, an estimated cost, and live CloudWatch metrics.

Each AgentCore runtime session answers one question at a time, so one tally per process is
enough: the loop resets it when a question starts and reads it when the question ends.
Translation runs in the translate tool (a Lambda), so its tokens are not counted here.
"""

import threading
from collections import defaultdict

import boto3
from botocore.exceptions import BotoCoreError, ClientError

NAMESPACE = "AskWRI/Live"
# Estimated list prices in USD per million input and output tokens, matched on the model ID.
# shortcut: a fixed price table - update it when prices change; costs are labelled "estimated".
PRICES = {"haiku": (1.0, 5.0), "sonnet": (3.0, 15.0)}

_lock = threading.Lock()
_calls: list[tuple[str, str, int, int]] = []  # (step, model, input tokens, output tokens)


def reset() -> None:
    """Start counting a new question."""
    with _lock:
        _calls.clear()


def record(step: str, model: str, tokens_in: int, tokens_out: int) -> None:
    """Count one model call (called from llm.ask_json, possibly from worker threads)."""
    with _lock:
        _calls.append((step, model, tokens_in, tokens_out))


def price(model: str) -> tuple[float, float]:
    return next((p for name, p in PRICES.items() if name in model), PRICES["sonnet"])


def summary() -> dict:
    """Tokens in and out, per step, and the estimated cost of the question so far."""
    with _lock:
        calls = list(_calls)
    by_step: dict[str, dict[str, int]] = defaultdict(lambda: {"in": 0, "out": 0})
    cost = 0.0
    for step, model, tokens_in, tokens_out in calls:
        by_step[step]["in"] += tokens_in
        by_step[step]["out"] += tokens_out
        price_in, price_out = price(model)
        cost += (tokens_in * price_in + tokens_out * price_out) / 1_000_000
    return {
        "tokensIn": sum(c[2] for c in calls),
        "tokensOut": sum(c[3] for c in calls),
        "modelCalls": len(calls),
        "byStep": dict(by_step),
        "estimatedCostUsd": round(cost, 5),
    }


def metric_data(
    used: dict, mode: str, source: str, seconds: float, outcome: str, removed: int
) -> list:
    """The CloudWatch datapoints for one question, by mode and traffic source."""
    dimensions = [{"Name": "Mode", "Value": mode}, {"Name": "Source", "Value": source}]

    def point(name, value, unit):
        return {"MetricName": name, "Dimensions": dimensions, "Value": value, "Unit": unit}

    return [
        point("Questions", 1, "Count"),
        point("Declined", 1 if outcome == "decline" else 0, "Count"),
        point("Failed", 1 if outcome == "error" else 0, "Count"),
        point("LatencySeconds", seconds, "Seconds"),
        point("TokensIn", used["tokensIn"], "Count"),
        point("TokensOut", used["tokensOut"], "Count"),
        point("EstimatedCostUSD", used["estimatedCostUsd"], "None"),
        point("ClaimsRemoved", removed, "Count"),
    ]


def publish(points: list) -> None:
    """Send the datapoints in the background, so the answer is never held up by metrics."""

    def send():
        try:
            boto3.client("cloudwatch").put_metric_data(Namespace=NAMESPACE, MetricData=points)
        except (BotoCoreError, ClientError) as error:  # best effort: never break an answer
            print(f"usage metrics not sent: {error}", flush=True)

    threading.Thread(target=send, daemon=True).start()
