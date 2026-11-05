"""Claim verification: drop every draft sentence that its cited passages don't support.

Works on any C2 draft (Quick answer or Deep research). Rules run in order and a sentence is
dropped at the first one it fails: source, quotes, numbers, then the Guardrails grounding check.
"""

import logging
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import boto3

from askwri.ingest.text import comparable, words

log = logging.getLogger(__name__)

# A grounding check scores one sentence: (question, sentence, cited passages' text) -> score.
Grounding = Callable[[str, str, str], float]

QUOTE = re.compile(r"“([^”]+)”|\"([^\"]+)\"")
MIN_QUOTE_WORDS = 4
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# After a footnote marker: the end of the text, or a space and then no lowercase letter.
SENTENCE_END = re.compile(r"\s*$|\s+[^\sa-z]")
# The default Guardrails quota is 106 text units per second; 4 calls in flight stay under it.
GROUNDING_WORKERS = 4
# ApplyGuardrail rejects a query longer than 1,000 characters.
MAX_QUERY_CHARS = 1000

NO_SOURCE = "no source"
QUOTE_NOT_FOUND = "quote not found"
QUOTE_NOT_QUOTABLE = "quote from a passage that may not be quoted"
NUMBER_NOT_IN_SOURCE = "number not in source"
NOT_GROUNDED = "not grounded"


def verify(question: str, draft: dict, *, grounding: Grounding | None) -> dict:
    """Check every sentence in the draft's paragraphs and report key points.

    Returns a dict with the kept `paragraphs` (empty ones removed) and `key_points`, the
    `claims_total` and `claims_verified` counts, every `dropped` sentence with its reason, and
    `grounding_check` ("guardrails", or "skipped" when `grounding` is None). Dropped sentences
    are logged, never shown.
    """
    passages = draft["passages"]
    report = draft.get("report") or {}
    sentences = [s for paragraph in draft["paragraphs"] for s in paragraph]
    sentences += report.get("key_points", [])

    reasons = {id(s): _first_failed_rule(s, passages) for s in sentences}
    if grounding is not None:
        checked = [s for s in sentences if reasons[id(s)] is None]
        for sentence, grounded in zip(
            checked, _grounded(question, checked, passages, grounding), strict=True
        ):
            if not grounded:
                reasons[id(sentence)] = NOT_GROUNDED

    dropped = [{"text": s["text"], "reason": reasons[id(s)]} for s in sentences if reasons[id(s)]]
    for sentence in dropped:
        log.info("Dropped sentence (%s): %s", sentence["reason"], sentence["text"])

    paragraphs = [[s for s in paragraph if not reasons[id(s)]] for paragraph in draft["paragraphs"]]
    return {
        "paragraphs": [paragraph for paragraph in paragraphs if paragraph],
        "key_points": [s for s in report.get("key_points", []) if not reasons[id(s)]],
        "claims_total": len(sentences),
        "claims_verified": len(sentences) - len(dropped),
        "dropped": dropped,
        "grounding_check": "skipped" if grounding is None else "guardrails",
    }


def _first_failed_rule(sentence: dict, passages: list) -> str | None:
    cites = sentence.get("cites") or []
    if not cites or any(not 1 <= cite <= len(passages) for cite in cites):
        return NO_SOURCE
    cited = [passages[cite - 1] for cite in cites]
    return _quote_problem(sentence["text"], cited) or _number_problem(sentence["text"], cited)


def _quote_problem(text: str, cited: list) -> str | None:
    for match in QUOTE.finditer(text):
        quote = match.group(1) or match.group(2)
        if len(words(quote)) < MIN_QUOTE_WORDS:
            continue
        holders = [p for p in cited if comparable(quote) in comparable(p.text)]
        if not holders:
            return QUOTE_NOT_FOUND
        if not any(p.quotable for p in holders):
            return QUOTE_NOT_QUOTABLE
    return None


def _number_problem(text: str, cited: list) -> str | None:
    in_sources = set().union(*(passage_numbers(p.text) for p in cited))
    return NUMBER_NOT_IN_SOURCE if numbers(text) - in_sources else None


def passage_numbers(text: str) -> set[Decimal]:
    """`numbers(text)`, plus each number read without a footnote marker glued to its end.

    Ingest keeps superscript footnote numbers attached to the word before them, so "by 2030"
    with footnote 12 reads "by 2030.12". When the last `.` or `,` part of a number ends a
    sentence (end of text, or a space and then anything but a lowercase letter), the number
    before it counts too. A real decimal mid-sentence ("3.5 percent") gets no extra reading.
    Only the passage side gets this, so it can keep a sentence but never drop one.
    """
    values = numbers(text)
    for match in NUMBER.finditer(text):
        before_marker = re.fullmatch(r"(.+)[.,]\d+", match.group())
        if before_marker and SENTENCE_END.match(text, match.end()):
            values.add(_value(before_marker.group(1)))
    return values


def numbers(text: str) -> set[Decimal]:
    """The numbers written in digits in `text`, as values.

    A `,` or `.` followed by exactly three digits is a thousands separator, any other is a
    decimal point: "2,000", "2.000" and "2000" are all 2000, while "3.5" and "3,5" are 3.5 and
    never 35. A leading "0." is always a decimal point ("0.125"). `%` and units are ignored.
    """
    return {_value(token) for token in NUMBER.findall(text)}


def _value(token: str) -> Decimal:
    parts = re.split(r"[.,]", token)
    if len(parts) > 1 and (len(parts[-1]) != 3 or parts[0] == "0"):
        return Decimal("".join(parts[:-1]) + "." + parts[-1])
    return Decimal("".join(parts))


def _grounded(question: str, sentences: list, passages: list, grounding: Grounding) -> list[bool]:
    threshold = float(os.environ.get("ASKWRI_GROUNDING_THRESHOLD", "0.7"))

    def check(sentence: dict) -> bool:
        source = "\n\n".join(passages[cite - 1].text for cite in dict.fromkeys(sentence["cites"]))
        return grounding(question, sentence["text"], source) >= threshold

    with ThreadPoolExecutor(max_workers=GROUNDING_WORKERS) as pool:
        return list(pool.map(check, sentences))


def guardrail_grounding() -> Grounding | None:
    """The Bedrock Guardrails grounding check, or None when it isn't configured.

    Reads `ASKWRI_GUARDRAIL_ID` and `ASKWRI_GUARDRAIL_VERSION`; with either unset the check is
    skipped. Each call is one `ApplyGuardrail` request on `bedrock-runtime` (#35's settings:
    grounding only, action NONE), and its `guardrailProcessingLatency` is logged.
    """
    guardrail_id = os.environ.get("ASKWRI_GUARDRAIL_ID")
    version = os.environ.get("ASKWRI_GUARDRAIL_VERSION")
    if not (guardrail_id and version):
        return None
    client = boto3.client("bedrock-runtime")

    def grounding_score(question: str, sentence: str, source: str) -> float:
        response = client.apply_guardrail(
            guardrailIdentifier=guardrail_id,
            guardrailVersion=version,
            source="OUTPUT",
            outputScope="FULL",
            content=[
                {"text": {"text": source, "qualifiers": ["grounding_source"]}},
                # shortcut: long questions are cut to the query limit - the check still
                # judges the sentence against its sources, which is what decides the drop.
                {"text": {"text": question[:MAX_QUERY_CHARS], "qualifiers": ["query"]}},
                {"text": {"text": sentence, "qualifiers": ["guard_content"]}},
            ],
        )
        return grounding_score_from(response)

    return grounding_score


def grounding_score_from(response: dict) -> float:
    """The GROUNDING score in an `ApplyGuardrail` response; logs the check's latency."""
    for assessment in response.get("assessments", []):
        latency = assessment.get("invocationMetrics", {}).get("guardrailProcessingLatency")
        log.info("Guardrails grounding check took %s ms", latency)
        for check in assessment.get("contextualGroundingPolicy", {}).get("filters", []):
            if check["type"] == "GROUNDING":
                return check["score"]
    raise RuntimeError("ApplyGuardrail returned no GROUNDING score: is grounding enabled?")
