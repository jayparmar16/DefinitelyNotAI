"""Turn a verified draft into the event the UI shows: an `answer` with numbered sources, or a decline."""

import re
import time
from collections import Counter

from askwri.answer.decline import decline_event, decline_reason
from askwri.answer.verify import Grounding, verify

MAX_PEOPLE = 5
END_PUNCTUATION = re.compile(r"[.!?]+$")


def respond(draft: dict, request: dict, *, grounding: Grounding | None, started_at: float) -> dict:
    """Verify the C2 draft, then return the C5 `decline` or `answer` event.

    `request` is the AskRequest (C5, camelCase keys); `started_at` is a `time.monotonic()`
    reading from when the request arrived. `grounding` is passed to `verify`.
    """
    verification = verify(request["question"], draft, grounding=grounding)
    reason = decline_reason(draft, verification)
    if reason:
        return decline_event(reason, draft)
    return {"type": "answer", "answer": finalize(draft, verification, request, started_at)}


def finalize(draft: dict, verification: dict, request: dict, started_at: float) -> dict:
    """Build the C5 Answer from the sentences that survived verification.

    Markers are renumbered [1] to [k] in order of first use, across paragraphs and then report
    key points, and `sources` holds exactly the cited passages in marker order.
    """
    passages = draft["passages"]
    markers: dict[int, int] = {}
    paragraphs = [
        " ".join(_with_markers(s, markers) for s in paragraph)
        for paragraph in verification["paragraphs"]
    ]
    key_points = [_with_markers(s, markers) for s in verification["key_points"]]
    cited = [passages[cite - 1] for cite in markers]
    sources = [_source(marker, p) for marker, p in enumerate(cited, start=1)]
    return {
        "mode": request["mode"],
        "language": "en",
        "machineTranslated": False,
        "paragraphs": paragraphs,
        "original": None,
        "sources": sources,
        "claimsTotal": verification["claims_total"],
        "claimsVerified": verification["claims_verified"],
        "groundingCheck": verification["grounding_check"],
        "people": _people(cited),
        "suggestions": draft.get("suggestions", []),
        "coverage": None,
        "report": _report(draft["report"], key_points, cited),
        "elapsedSeconds": round(time.monotonic() - started_at, 1),
    }


def _with_markers(sentence: dict, markers: dict[int, int]) -> str:
    """The sentence with its [n] markers before the closing punctuation, numbering new cites."""
    for cite in sentence["cites"]:
        markers.setdefault(cite, len(markers) + 1)
    numbered = "".join(f"[{markers[cite]}]" for cite in dict.fromkeys(sentence["cites"]))
    text = sentence["text"].rstrip()
    end = END_PUNCTUATION.search(text)
    split = end.start() if end else len(text)
    return f"{text[:split]} {numbered}{text[split:]}"


def _source(marker: int, p) -> dict:
    return {
        "marker": marker,
        "chunkId": p.chunk_id,
        "docId": p.doc_id,
        "title": p.doc_title,
        "docType": p.doc_type,
        "wriType": p.wri_type,
        "topic": p.topic,
        "year": p.year,
        "pdfPage": p.pdf_page,
        "pdfPageEnd": p.pdf_page_end,
        "printedPage": p.printed_page,
        "printedPageEnd": p.printed_page_end,
        "printedPageFallback": p.printed_page_fallback,
        "section": p.section,
        "kind": p.kind,
        "passage": p.text,
        "quotable": p.quotable,
        "url": p.link,
        "pdfKey": p.pdf_key,
        "figureImage": p.figure_image,
        "authors": list(p.authors),
    }


def _people(cited: list) -> list[dict]:
    """Authors of the cited passages, most-cited first (ties by first use), at most 5."""
    counts = Counter(author for p in cited for author in p.authors)
    docs: dict[str, list[str]] = {}
    for p in cited:
        for author in p.authors:
            doc_ids = docs.setdefault(author, [])
            if p.doc_id not in doc_ids:
                doc_ids.append(p.doc_id)
    ranked = sorted(docs, key=lambda author: -counts[author])
    return [{"name": author, "docIds": docs[author]} for author in ranked[:MAX_PEOPLE]]


def _report(report: dict | None, key_points: list[str], cited: list) -> dict | None:
    if report is None:
        return None
    return {
        "title": report["title"],
        "audience": report["audience"],
        "format": report["format"],
        "builtFrom": built_from(cited),
        "keyPoints": key_points,
        "thinEvidence": report.get("thin_evidence", []),
        "gaps": report.get("gaps", []),
    }


def built_from(cited: list) -> str:
    """The report's provenance line, e.g. "Built from 9 WRI publications, 2024 to 2026".

    Counts distinct documents. One year reads ", 2025"; unknown years are left out.
    """
    docs = {p.doc_id: p.year for p in cited}
    count = len(docs)
    line = f"Built from {count} WRI publication{'' if count == 1 else 's'}"
    years = sorted(year for year in docs.values() if year is not None)
    if not years:
        return line
    if years[0] == years[-1]:
        return f"{line}, {years[0]}"
    return f"{line}, {years[0]} to {years[-1]}"
