"""Sort the corpus: drop duplicates, non-English files and older versions, and type each document.

Run `python -m askwri.ingest.sort <folder>...` to print the sorting report for folders of PDFs.
"""

import argparse
import hashlib
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from askwri.ingest.classify import detect_doc_type, detect_language
from askwri.ingest.document import doc_id_for

DUPLICATE = "duplicate"
OLDER_VERSION = "older version"
NOT_ENGLISH = "not English"

FIRST_PAGES = 5
# "unknown" is a file with too little text to judge (a scan or a slide deck). It is kept: the
# ingestion audit reports pages without a text layer, and dropping on no evidence loses documents.
KEPT_LANGUAGES = {"en", "unknown"}

# "_0", "_1": the copy suffix WRI's site adds when the same file name is uploaded again.
COPY_SUFFIX = re.compile(r"_(\d)$")
# "(Version 2.1)", "-version-2", "_v1-1", "-v5": the number is what orders a family.
VERSION_MARKER = re.compile(r"\(?(?:\bversion[\s_-]*|(?<![a-z0-9])v)(\d+(?:[._-]\d+)*)\)?")
LANGUAGE_MARKERS = {
    "en", "es", "fr", "pt", "cn", "zh", "por", "english", "spanish", "espanol", "french",
    "francais", "portuguese", "portugues", "chinese", "simplified",
}  # fmt: skip


@dataclass(frozen=True)
class KeptDocument:
    """A PDF that goes on to ingestion."""

    path: Path
    doc_id: str
    language: str  # "en", or "unknown" when the first pages have too little text to judge
    doc_type: str
    replaces: tuple[Path, ...]  # older versions dropped in favour of this one


@dataclass(frozen=True)
class DroppedDocument:
    """A PDF that is not ingested, with why."""

    path: Path
    reason: str  # DUPLICATE, OLDER_VERSION or NOT_ENGLISH
    detail: str


@dataclass(frozen=True)
class SortedCorpus:
    """The sorting result: every input PDF is in exactly one of the two lists."""

    kept: list[KeptDocument]
    dropped: list[DroppedDocument]


def sort_corpus(pdfs: list[Path]) -> SortedCorpus:
    """Split PDFs into kept and dropped documents, each dropped one with its reason.

    In order: exact duplicates (same bytes) are dropped, then files whose first pages are not
    English, then every family of versions of one document is cut to its latest version.
    Raises ValueError if two kept documents would get the same doc_id.
    """
    unique, dropped = _drop_duplicates(sorted(pdfs))
    texts = {pdf: _first_pages_text(pdf) for pdf in unique}
    languages = {pdf: detect_language(text) for pdf, text in texts.items()}
    english = [pdf for pdf in unique if languages[pdf] in KEPT_LANGUAGES]
    replaced = _latest_versions(english)

    kept = [
        KeptDocument(
            path=pdf,
            doc_id=doc_id_for(pdf),
            language=languages[pdf],
            doc_type=detect_doc_type(pdf, texts[pdf]),
            replaces=tuple(replaced[pdf]),
        )
        for pdf in replaced
    ]
    _require_unique_doc_ids(kept)
    for latest in kept:
        dropped += [
            DroppedDocument(old, OLDER_VERSION, f"replaced by {_label(latest.path)}")
            for old in latest.replaces
        ]
    twins = {_twin_key(doc.path): doc.path for doc in kept}
    for pdf in unique:
        if languages[pdf] not in KEPT_LANGUAGES:
            twin = twins.get(_twin_key(pdf))
            twin_note = f"English twin kept: {_label(twin)}" if twin else "no English twin found"
            dropped.append(DroppedDocument(pdf, NOT_ENGLISH, f"{languages[pdf]}; {twin_note}"))
    return SortedCorpus(
        kept=sorted(kept, key=lambda doc: doc.path),
        dropped=sorted(dropped, key=lambda doc: (doc.reason, doc.path)),
    )


def _drop_duplicates(pdfs: list[Path]) -> tuple[list[Path], list[DroppedDocument]]:
    """Keep one file per content hash: the one without a copy suffix, then the shortest name."""
    by_hash = defaultdict(list)
    for pdf in pdfs:
        with pdf.open("rb") as handle:
            by_hash[hashlib.file_digest(handle, "sha256").hexdigest()].append(pdf)
    unique, dropped = [], []
    for same in by_hash.values():
        keeper, *copies = sorted(same, key=_duplicate_rank)
        unique.append(keeper)
        dropped += [
            DroppedDocument(copy, DUPLICATE, f"same content as {_label(keeper)}") for copy in copies
        ]
    return sorted(unique), dropped


def _duplicate_rank(pdf: Path) -> tuple[bool, int, Path]:
    return (COPY_SUFFIX.search(pdf.stem) is not None, len(pdf.stem), pdf)


def _first_pages_text(pdf: Path) -> str:
    with pymupdf.open(pdf) as doc:
        return "\n".join(doc[number].get_text() for number in range(min(FIRST_PAGES, len(doc))))


def _latest_versions(pdfs: list[Path]) -> dict[Path, list[Path]]:
    """Group PDFs into version families and map each family's latest PDF to the older ones.

    A family is every file with the same name once copy suffixes and version markers are
    removed. The latest has the highest version number, then the latest year folder, then the
    highest copy suffix. Files whose names differ otherwise (other months, other years in the
    name, "trucks" versus "vehicles") are different documents.
    """
    # shortcut: families match on the file name only - PDF titles would also catch renamed
    # re-uploads, but they merged distinct documents (one form per fiscal year) in the corpus
    families = defaultdict(list)
    for pdf in pdfs:
        families[_family_key(pdf)].append(pdf)
    latest = {}
    for family in families.values():
        *older, newest = sorted(family, key=_version_rank)
        latest[newest] = older
    return latest


def _family_key(pdf: Path) -> str:
    name = VERSION_MARKER.sub("", COPY_SUFFIX.sub("", pdf.stem.lower()))
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def _version_rank(pdf: Path) -> tuple[tuple[int, ...], int, int, Path]:
    marker = VERSION_MARKER.search(pdf.stem.lower())
    version = tuple(int(part) for part in re.split(r"[._-]", marker[1])) if marker else ()
    year = re.search(r"\d{4}", pdf.parent.name)
    copy = COPY_SUFFIX.search(pdf.stem)
    return (version, int(year[0]) if year else 0, int(copy[1]) + 1 if copy else 0, pdf)


def _twin_key(pdf: Path) -> str:
    """The family key without language words, so "report-espanol" and "report" match."""
    return "-".join(word for word in _family_key(pdf).split("-") if word not in LANGUAGE_MARKERS)


def _require_unique_doc_ids(kept: list[KeptDocument]) -> None:
    """Fail loudly rather than let two documents share chunk IDs; a rename fixes it."""
    paths_by_id = defaultdict(list)
    for doc in kept:
        paths_by_id[doc.doc_id].append(_label(doc.path))
    clashes = {doc_id: paths for doc_id, paths in paths_by_id.items() if len(paths) > 1}
    if clashes:
        raise ValueError(f"kept documents share a doc_id: {clashes}")


def _label(pdf: Path) -> str:
    return f"{pdf.parent.name}/{pdf.name}"


def format_report(corpus: SortedCorpus) -> str:
    """Render the sorting result: counts, then the version families, then every dropped file."""
    total = len(corpus.kept) + len(corpus.dropped)
    lines = [f"{total} PDFs: {len(corpus.kept)} kept, {len(corpus.dropped)} dropped", ""]
    lines += _counts("Dropped by reason", Counter(d.reason for d in corpus.dropped))
    lines += _counts("Kept by document type", Counter(d.doc_type for d in corpus.kept))
    lines += _counts("Kept by language", Counter(d.language for d in corpus.kept))
    lines.append("Version families (kept, then what it replaces)")
    for doc in corpus.kept:
        if doc.replaces:
            lines.append(f"  {_label(doc.path)}")
            lines += [f"      replaces {_label(old)}" for old in doc.replaces]
    lines += ["", "Dropped files"]
    lines += [f"  [{d.reason}] {_label(d.path)}: {d.detail}" for d in corpus.dropped]
    return "\n".join(lines)


def _counts(title: str, counts: Counter) -> list[str]:
    return [title, *(f"  {name}: {n}" for name, n in counts.most_common()), ""]


def main() -> int:
    """Sort the PDFs in the given folders and print the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", type=Path, help="folders of PDFs")
    args = parser.parse_args()
    pdfs = [pdf for folder in args.folders for pdf in sorted(folder.glob("*.pdf"))]
    if not pdfs:
        parser.error("no PDFs found in the given folders")
    print(format_report(sort_corpus(pdfs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
