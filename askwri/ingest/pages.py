"""Printed page numbers: the number a reader sees on each page, which differs from its PDF position."""

import re
from collections import Counter
from dataclasses import dataclass

ROMAN = re.compile(r"^(?=[ivxlc])c{0,3}(?:x[cl]|l?x{0,3})(?:i[xv]|v?i{0,3})$", re.IGNORECASE)
ROMAN_DIGITS = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}
PUNCTUATION_ONLY = re.compile(r"^[\W_]+$")


@dataclass(frozen=True)
class PrintedPage:
    """What a reader sees as the page number, and whether it had to be guessed."""

    label: str  # "iv", "12" or, when nothing was found, the PDF page number
    fallback: bool  # True when no printed number was found and label is the PDF page number


def printed_pages(labels: list[str], region_texts: list[list[str]]) -> list[PrintedPage]:
    """Printed number of every page: the PDF's page label, else a number read from the page edges.

    labels: the PDF's page label for each page ("" where the PDF defines none).
    region_texts: the text of each page's page-header and page-footer regions.
    Numbers read from the regions are trusted only when at least two pages agree on the same
    offset from the PDF page (page 3 printed "1" and page 4 printed "2"), which rejects
    stray numbers such as "Chapter 2" or a year. When a page has several trusted numbers the
    one that most pages agree on wins. A page with no label and no trusted number
    falls back to its PDF page number and is flagged.
    """
    candidates = [_candidates(texts) for texts in region_texts]
    runs = Counter(
        (is_roman, value - pdf_page)
        for pdf_page, page_candidates in enumerate(candidates, start=1)
        for is_roman, value, _ in page_candidates
    )
    pages = []
    for pdf_page, (label, page_candidates) in enumerate(zip(labels, candidates, strict=True), 1):
        trusted = {
            text: runs[(is_roman, value - pdf_page)]
            for is_roman, value, text in page_candidates
            if runs[(is_roman, value - pdf_page)] >= 2
        }
        if label:
            pages.append(PrintedPage(label=label, fallback=False))
        elif trusted:
            pages.append(PrintedPage(label=max(trusted, key=trusted.get), fallback=False))
        else:
            pages.append(PrintedPage(label=str(pdf_page), fallback=True))
    return pages


def _candidates(region_texts: list[str]) -> list[tuple[bool, int, str]]:
    """Page-number-like tokens at the start or end of each region: (is_roman, value, text)."""
    found = []
    for region in region_texts:
        tokens = [t for t in region.split() if not PUNCTUATION_ONLY.match(t)]
        for token in dict.fromkeys(tokens[:1] + tokens[-1:]):
            if re.fullmatch(r"\d{1,3}", token):
                found.append((False, int(token), token))
            elif ROMAN.match(token):
                found.append((True, _roman_value(token), token))
    return found


def _roman_value(numeral: str) -> int:
    values = [ROMAN_DIGITS[char] for char in numeral.lower()]
    followed_by = [*values[1:], 0]
    return sum(-v if v < f else v for v, f in zip(values, followed_by, strict=True))
