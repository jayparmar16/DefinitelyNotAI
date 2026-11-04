"""Turning drafted sentences and their passage IDs into the cited answer the UI shows.

The draft model labels each sentence with the passage IDs (P1, P2, ...) it rests on. Here those
become [n] markers numbered by first use, a sources list with one entry per cited passage, and
the deterministic checks that run before any model-based verification.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Sentence:
    """One drafted claim and the passages (by P-label) it cites."""

    text: str
    passages: tuple[str, ...]


def label_passages(results: list[dict]) -> dict[str, dict]:
    """Give each search result a stable label for the draft prompt: P1, P2, ... in order."""
    return {f"P{i}": result for i, result in enumerate(results, start=1)}


def cited_sentences(sentences: list[Sentence], labels: dict[str, dict]) -> list[Sentence]:
    """Keep only sentences that cite at least one real passage; unknown labels are dropped."""
    kept = []
    for sentence in sentences:
        known = tuple(label for label in sentence.passages if label in labels)
        if sentence.text.strip() and known:
            kept.append(Sentence(sentence.text.strip(), known))
    return kept


def with_markers(text: str, markers: list[int]) -> str:
    """Put [n] markers at the end of a sentence, before its final punctuation."""
    tags = "".join(f"[{m}]" for m in markers)
    if text and text[-1] in ".!?":
        return f"{text[:-1]} {tags}{text[-1]}"
    return f"{text} {tags}"


def number_markers(groups: list[list[Sentence]]) -> tuple[list[str], list[str]]:
    """Render groups of sentences (paragraphs or key points) with markers numbered by first use.

    Returns the rendered texts and the P-labels in marker order (marker n = labels[n - 1]).
    """
    order: list[str] = []
    texts = []
    for group in groups:
        rendered = []
        for sentence in group:
            for label in sentence.passages:
                if label not in order:
                    order.append(label)
            rendered.append(
                with_markers(sentence.text, [order.index(p) + 1 for p in sentence.passages])
            )
        texts.append(" ".join(rendered))
    return texts, order


def source_entry(marker: int, result: dict, authors: list[str]) -> dict:
    """One sources-list entry in the UI's Source shape (web/src/lib/agent.ts)."""
    return {
        "marker": marker,
        "chunkId": result["chunk_id"],
        "docId": result["doc_id"],
        "title": result["title"],
        "pubType": result.get("pub_type") or "Publication",
        "year": result.get("year"),
        "dateConfidence": result.get("date_confidence") or "undated",
        "office": result.get("office") or "WRI",
        "page": result["page"],
        "printedPage": result.get("printed_page"),
        "pageCount": None,
        "passage": result["passage"],
        "quotable": result.get("quotable", True),
        "url": result.get("url"),
        "doi": result.get("doi"),
        "pdfKey": result.get("pdf_key"),
        "authors": authors,
        "why": result.get("why"),
    }


def drop_unsupported(groups: list[list[Sentence]], supported: set[int]) -> list[list[Sentence]]:
    """Keep only sentences whose position (counted across all groups, from 0) is supported.

    Groups left empty are removed, so no blank paragraph or key point reaches the user.
    """
    kept, position = [], 0
    for group in groups:
        survivors = []
        for sentence in group:
            if position in supported:
                survivors.append(sentence)
            position += 1
        if survivors:
            kept.append(survivors)
    return kept


NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_not_in(text: str, source: str) -> list[str]:
    """Numbers in `text` that never appear in `source`, compared as digits only (so "1,000"
    matches "1000"). An implication that introduces one states a fact no passage gave."""
    known = {re.sub(r"\D", "", n) for n in NUMBER.findall(source)}
    return [n for n in NUMBER.findall(text) if re.sub(r"\D", "", n) not in known]
