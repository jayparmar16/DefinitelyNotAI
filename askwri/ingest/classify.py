"""Guess a document's language and type from its file name and the text of its first pages."""

import re
from pathlib import Path


def _words(text: str) -> set[str]:
    return set(text.split())


# Short function-word lists; the language whose words make up the biggest share of the text wins.
STOPWORDS = {
    "en": _words(
        "the of and to in a is that for on with as by are this be from it an at or which has "
        "have was were not can will more their its also these other than such into"
    ),
    "es": _words(
        "el la los las de del y en que un una por con para es se al lo como más su sus este "
        "esta estos estas entre sobre sin son ser también o"
    ),
    "pt": _words(
        "o a os as de do da dos das e em que um uma por com para é se ao como mais seu sua "
        "seus suas este esta estes estas entre sobre sem são ser também ou não"
    ),
    "fr": _words(
        "le la les de du des et en que un une pour par avec est sont se au aux comme plus son "
        "sa ses ce cette ces entre sur sans être aussi ou dans qui ne pas"
    ),
}
MIN_WORDS = 30  # fewer words than this is a cover, a slide or a scan: not enough to judge
MIN_STOPWORD_SHARE = 0.05  # below this the text is not in any language we have words for

# Checked in order, so "technical-note-dataset-..." is a technical note. Each type lists
# file-name phrases (whole words in the dashed name) and cover labels (regular expressions).
DOC_TYPES = [
    (
        "RFP",
        (
            *("rfp", "rfi", "rfq", "tdr", "terms-of-reference"),
            *("request-for-proposal", "request-for-proposals"),
        ),
        ("REQUEST FOR PROPOSALS?", "Request for Proposals?", "TERMS OF REFERENCE"),
    ),
    (
        "newsletter",
        ("newsletter", "hot-science", "hot-sicence", "roundup", "clean-energy-pulse"),
        ("NEWSLETTER",),
    ),
    ("annual report", ("annual-report",), ("ANNUAL REPORT",)),
    ("technical note", ("technical-note", "tech-note"), ("TECHNICAL NOTE",)),
    ("working paper", ("working-paper", "wp"), ("WORKING PAPER",)),
    ("issue brief", ("issue-brief",), ("ISSUE BRIEF",)),
    ("dataset documentation", ("dataset", "changelog", "change-log", "log-of-changes"), ()),
    ("research report", ("report",), ("REPORT",)),
]


def detect_language(text: str) -> str:
    """Name the language of `text`: "en", "es", "pt", "fr", "zh", "other" or "unknown".

    "unknown" means too little text to judge (a cover, a slide deck, a scan). "other" means
    there is text, but it is in a script or language we have no words for, or it is garbled.
    """
    letters = [char for char in text if char.isalpha()]
    non_latin = sum(ord(char) > 0x24F for char in letters)
    if letters and non_latin / len(letters) > 0.3:
        cjk = sum("一" <= char <= "鿿" for char in letters)
        return "zh" if cjk > non_latin / 2 else "other"
    words = re.findall(r"[^\W\d_]+", text.lower())
    if len(words) < MIN_WORDS:
        return "unknown"
    shares = {
        language: sum(word in stopwords for word in words) / len(words)
        for language, stopwords in STOPWORDS.items()
    }
    best = max(shares, key=shares.get)
    return best if shares[best] >= MIN_STOPWORD_SHARE else "other"


def detect_doc_type(pdf_path: Path, first_pages_text: str) -> str:
    """Name the document's type, from the file name first and then the cover text.

    A file name phrase such as "rfp" or "newsletter" decides it. Otherwise a cover label such
    as "WORKING PAPER" does. Labels are matched in capitals only, because "working paper" in
    lower case is usually a citation. Anything else is "other".
    """
    name = f"-{re.sub(r'[^a-z0-9]+', '-', pdf_path.stem.lower()).strip('-')}-"
    text = " ".join(first_pages_text.split())
    for doc_type, phrases, _ in DOC_TYPES:
        if any(f"-{phrase}-" in name for phrase in phrases):
            return doc_type
    for doc_type, _, labels in DOC_TYPES:
        if any(re.search(rf"\b{label}\b", text) for label in labels):
            return doc_type
    return "other"
