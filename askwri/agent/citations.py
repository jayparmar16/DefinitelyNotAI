"""Turning drafted sentences and their passage IDs into the cited answer the UI shows.

The draft model labels each sentence with the passage IDs (P1, P2, ...) it rests on. Here those
become [n] markers numbered by first use, a sources list with one entry per cited passage, and
the deterministic checks that run before any model-based verification.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Sentence:
    """One drafted sentence and the passages (by P-label) it cites. A sentence with no passages
    is a connective: framing or a transition between claims that states no fact of its own."""

    text: str
    passages: tuple[str, ...]


def label_passages(results: list[dict]) -> dict[str, dict]:
    """Give each search result a stable label for the draft prompt: P1, P2, ... in order."""
    return {f"P{i}": result for i, result in enumerate(results, start=1)}


def cited_sentences(sentences: list[Sentence], labels: dict[str, dict]) -> list[Sentence]:
    """Keep sentences that cite at least one real passage (unknown labels are dropped), plus
    connectives that lead into one. A connective with a number, or one citing only unknown
    labels, is a claim in disguise and is dropped."""
    kept: list[Sentence] = []
    for sentence in sentences:
        text = sentence.text.strip()
        known = tuple(label for label in sentence.passages if label in labels)
        if text and known:
            kept.append(Sentence(text, known))
        elif text and not sentence.passages and not NUMBER.search(text):
            kept.append(Sentence(text, ()))
    return trim_connectives(kept)


def trim_connectives(sentences: list[Sentence]) -> list[Sentence]:
    """Drop connectives that no longer lead into a claim (trailing ones, or all of them when
    the group has no claim left), so no transition is left pointing at nothing."""
    while sentences and not sentences[-1].passages:
        sentences = sentences[:-1]
    return sentences


def with_markers(text: str, markers: list[int]) -> str:
    """Put [n] markers at the end of a sentence, before its final punctuation."""
    if not markers:
        return text
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
        "topics": result.get("topics") or [],
        "abstract": result.get("abstract"),
    }


def drop_unsupported(groups: list[list[Sentence]], supported: set[int]) -> list[list[Sentence]]:
    """Keep only claims whose position (counted across all groups' claims, from 0, skipping
    connectives) is supported, and the connectives still leading into one.

    Groups left empty are removed, so no blank paragraph or key point reaches the user.
    """
    kept, position = [], 0
    for group in groups:
        survivors = []
        for sentence in group:
            if not sentence.passages:
                survivors.append(sentence)
                continue
            if position in supported:
                survivors.append(sentence)
            position += 1
        survivors = trim_connectives(survivors)
        if survivors:
            kept.append(survivors)
    return kept


NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_not_in(text: str, source: str) -> list[str]:
    """Numbers in `text` that never appear in `source`, compared as digits only (so "1,000"
    matches "1000"). An implication that introduces one states a fact no passage gave."""
    known = {re.sub(r"\D", "", n) for n in NUMBER.findall(source)}
    return [n for n in NUMBER.findall(text) if re.sub(r"\D", "", n) not in known]


PASSAGES_WORD = re.compile(
    r"\b(?:(the|these|those|its|their|a|an|one)\s+)?(passages?)\b", re.IGNORECASE
)


def readers_words(text: str) -> str:
    """Replace "passage(s)", the agent's internal word, with what readers see: the cited WRI
    publication(s). Models told not to say it still sometimes do."""

    def replace(match: re.Match) -> str:
        plural = match.group(2).lower().endswith("s")
        words = "the cited WRI publications" if plural else "a cited WRI publication"
        return words[0].upper() + words[1:] if match.group(0)[0].isupper() else words

    return PASSAGES_WORD.sub(replace, text)
