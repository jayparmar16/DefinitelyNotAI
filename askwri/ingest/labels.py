"""Document labels: WRI's own from its wri.org page, the labeler model's where the page has none.

Also what is built from them: the year fallback, the chunk context line and the document card.
"""

import html
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from itertools import chain
from pathlib import Path

import pymupdf

from askwri.ingest.classify import detect_doc_type
from askwri.ingest.model_labels import (
    NO_TOPIC,
    TOPICS,
    Enrichment,
    label_from_text,
    topic_from_text,
)
from askwri.ingest.text import comparable
from askwri.ingest.vocabulary import CONCEPTS
from askwri.ingest.wri_site import Page, WriSite

# Site topic names that differ from the 11 menu topics. Any other value is an error.
SITE_TOPICS = {**{topic: topic for topic in TOPICS}, "Equity & Governance": "Equity"}
FRONT_PAGES = 5  # a document's own DOI and date sit in the first pages; later DOIs are cited
# PDF text sometimes breaks a DOI with a space after the slash: "doi.org/10.46830/ wrirpt.24.1"
WRI_DOI = re.compile(r"10\.46830/ ?[A-Za-z0-9.\-]*[A-Za-z0-9]")
CITATION_MARKER = re.compile(r"suggested citation|available online at", re.IGNORECASE)
DOI_REACH = 600  # characters after a citation marker in which its DOI must start
SUGGESTED_CITATION = re.compile(r"suggested citation", re.IGNORECASE)
QUOTED_TITLE = re.compile(r"[\u201c\"]([^\u201d\"]{8,}?)[\u201d\"]")
TITLE_REACH = 800  # a long author list can sit between the marker and the quoted title
# The corpus is filed in one folder per publication year: "2025" or "2025_publications".
FOLDER_YEAR = re.compile(r"(\d{4})(?!\d)")
CONCEPT_BY_KEY = {concept.casefold(): concept for concept in CONCEPTS}
# A chunk's context line names only the first few: a long list would crowd out the passage.
CONTEXT_CONCEPTS = 6
CONTEXT_PLACES = 6


@dataclass(frozen=True)
class DocumentLabels:
    """One document's labels. A label nobody could supply is empty, never an error."""

    # "wri.org", "model" (no page, so the labeler read the document), or "no page" (no model
    # client was given; the citation then falls back to the stored PDF)
    label_source: str
    title: str  # the wri.org page's title, else the labeler's, else the PDF's
    doi: str | None  # the document's own WRI DOI as printed in the PDF
    link: str | None  # the wri.org page, checked to resolve
    page_match: str | None  # "doi" or "title"
    topic: str | None  # one of TOPICS, or "none" when the labeler found no fitting topic
    topic_source: str | None  # "wri.org" or "model": a page without a usable topic gets the model's
    wri_type: str | None
    authors: tuple[str, ...]
    published: str | None  # ISO date
    tags: tuple[str, ...]  # secondary tags: feed search filters, never counts
    doc_type: str | None  # the labeler's reading of the type; wri.org documents use wri_type
    countries: tuple[str, ...]  # from the labeler
    summary: str | None  # from the labeler
    deadline: str | None  # RFPs the labeler read, ISO date
    year: int | None = None  # from `published`, else the corpus folder's year (with_year)
    date_source: str | None = None  # where `year` came from: "wri.org", "model" or "folder"
    abstract: str | None = None  # the wri.org page's description: WRI's own words
    initiatives: tuple[str, ...] = ()  # from the page's "part of ... within ..." line
    programs: tuple[str, ...] = ()
    # Every topic the document covers, `topic` first. `topic` stays the one that is counted.
    topics: tuple[str, ...] = ()
    concepts: tuple[str, ...] = ()  # of vocabulary.CONCEPTS: WRI's tags, then the labeler's
    acronyms: tuple[str, ...] = ()  # "OSW = Offshore wind", as the text defines them
    # From the labeler's enrichment call (with_enrichment); empty without a model client.
    keywords: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    key_findings: tuple[str, ...] = ()  # model-written: searchable, never quoted
    genre: str | None = None
    coverage_start: int | None = None  # the years the document's data or analysis covers
    coverage_end: int | None = None


def label_document(pdf_path: Path, title: str, site: WriSite | None, client=None) -> DocumentLabels:
    """Find the document's wri.org page and read its labels; else ask the labeler model.

    The page is looked up by DOI and by title. If that fails, the title quoted in the PDF's
    suggested-citation block is tried too, because the metadata title is often unusable.
    A page's own labels are never overwritten; if it has no usable topic, the model picks one.
    With no page the model labels the whole document. With no `client` the model is never
    called, and a document without a page is just "no page"; with no `site`, nothing is
    looked up. Raises ModelError if the model fails, and ValueError if it returns a topic
    outside the 11 and "none".
    """
    front_text = _front_text(pdf_path)
    doi = own_doi(front_text)
    page = _find_page(site, title, front_text, doi)
    if page is None:
        labels = _no_page_labels(title, doi)
        if client is None:
            return labels
        return _model_labels(client, pdf_path, front_text, labels)
    labels = _page_labels(page, doi)
    if labels.topic is None and client is not None:
        topic = topic_from_text(client, pdf_path.name, front_text)
        labels = replace(
            labels, topic=topic, topic_source="model", topics=_topics(topic, labels.tags)
        )
    return labels


def with_year(labels: DocumentLabels, pdf_path: Path) -> DocumentLabels:
    """Set `year` and `date_source`: the publication date's year, else the corpus folder's.

    A folder name that does not start with a year (not "2025" or "2025_publications") leaves
    an undated document undated.
    """
    if labels.published:
        source = "wri.org" if labels.label_source == "wri.org" else "model"
        return replace(labels, year=int(labels.published[:4]), date_source=source)
    if folder := FOLDER_YEAR.match(pdf_path.parent.name):
        return replace(labels, year=int(folder.group(1)), date_source="folder")
    return labels


def with_enrichment(labels: DocumentLabels, more: Enrichment) -> DocumentLabels:
    """Add the labeler's richer labels after the document's own; none of them is replaced."""
    return replace(
        labels,
        topics=_merged(labels.topics, more.topics),
        concepts=_merged(labels.concepts, more.concepts),
        countries=_merged(labels.countries, more.countries),
        keywords=more.keywords,
        regions=more.regions,
        key_findings=more.key_findings,
        genre=more.genre,
        coverage_start=more.coverage_start,
        coverage_end=more.coverage_end,
    )


def _merged(*groups: Iterable[str]) -> tuple[str, ...]:
    """Every value of the groups in order, each once (ignoring case), empties dropped."""
    seen: dict[str, str] = {}
    for value in chain(*groups):
        if value:
            seen.setdefault(value.casefold(), value)
    return tuple(seen.values())


def chunk_context(labels: DocumentLabels) -> str:
    """The document's year, topics, concepts, initiatives and places as one line.

    It is embedded with each chunk, so a passage that never names its year, topic or place
    still matches a question that does. For example "2025 · Energy, Ocean · offshore wind,
    renewable energy · Ocean Climate Diplomacy · India, South Asia". Empty when the document
    has none of these labels.
    """
    parts = (
        str(labels.year or ""),
        ", ".join(labels.topics),
        ", ".join(labels.concepts[:CONTEXT_CONCEPTS]),
        ", ".join(labels.initiatives),
        ", ".join((*labels.countries, *labels.regions)[:CONTEXT_PLACES]),
    )
    return " · ".join(part for part in parts if part)


def document_card(labels: DocumentLabels) -> str:
    """The document as one text for document-level search.

    Title, the wri.org abstract (else the labeler's summary), the labels and the key findings.
    Parts are model-written, so the card is for finding documents, never for quoting.
    """
    lines = (
        labels.title,
        labels.abstract or labels.summary or "",
        _card_line("Published", [str(labels.year)] if labels.year else []),
        _card_line("Genre", [labels.genre] if labels.genre else []),
        _card_line("Part of", [*labels.initiatives, *labels.programs]),
        _card_line("Topics", labels.topics),
        _card_line("Concepts", labels.concepts),
        _card_line("Keywords", labels.keywords),
        _card_line("Places", [*labels.countries, *labels.regions]),
        _card_line("Key findings", labels.key_findings, " "),
    )
    return "\n".join(line for line in lines if line)


def citation_title(front_text: str) -> str | None:
    """The title quoted after "Suggested citation" (authors, year, then the title), else None."""
    marker = SUGGESTED_CITATION.search(front_text)
    if marker is None:
        return None
    quoted = QUOTED_TITLE.search(front_text, marker.end(), marker.end() + TITLE_REACH)
    return quoted.group(1).strip(" .,") if quoted else None


def own_doi(front_text: str) -> str | None:
    """The WRI DOI in the document's suggested-citation block, else None.

    Reports also print the DOIs of works they cite, and some of those resolve to translations,
    so only a DOI that follows "Suggested citation" or "Available online at" counts.
    """
    for marker in CITATION_MARKER.finditer(front_text):
        if doi := WRI_DOI.search(front_text, marker.end(), marker.end() + DOI_REACH):
            return doi.group(0).replace(" ", "")
    return None


def catalog_row(doc_id: str, pdf_file: str, labels: DocumentLabels) -> dict:
    """One catalog row: the document's labels, plus the stored PDF a citation falls back to."""
    return {"doc_id": doc_id, "pdf_file": pdf_file, **asdict(labels)}


def chunk_label_fields(labels: DocumentLabels) -> dict:
    """The label fields every chunk of the document carries: filters, and the context line."""
    return {
        "label_source": labels.label_source,
        "link": labels.link,
        "year": labels.year,
        "topic": labels.topic,
        "wri_type": labels.wri_type,
        "tags": labels.tags,
        "context": chunk_context(labels),
    }


def _find_page(site: WriSite | None, title: str, front_text: str, doi: str | None) -> Page | None:
    if site is None:
        return None
    page = site.find_page(title, doi)
    cited = citation_title(front_text)
    if page is None and cited and comparable(cited) != comparable(title):
        page = site.find_page(cited, doi)
    return page


def _no_page_labels(title: str, doi: str | None) -> DocumentLabels:
    return DocumentLabels(
        label_source="no page",
        title=title,
        doi=doi,
        link=None,
        page_match=None,
        topic=None,
        topic_source=None,
        wri_type=None,
        authors=(),
        published=None,
        tags=(),
        doc_type=None,
        countries=(),
        summary=None,
        deadline=None,
    )


def _model_labels(
    client, pdf_path: Path, front_text: str, labels: DocumentLabels
) -> DocumentLabels:
    is_rfp = detect_doc_type(pdf_path, front_text) == "RFP"
    read = label_from_text(client, pdf_path.name, front_text, is_rfp)
    return replace(
        labels,
        label_source="model",
        title=read.title or labels.title,
        topic=read.topic,
        topics=_topics(read.topic, ()),
        topic_source="model",
        published=read.published,
        doc_type=read.doc_type,
        countries=read.countries,
        summary=read.summary,
        deadline=read.deadline,
    )


def _page_labels(page: Page, doi: str | None) -> DocumentLabels:
    meta = page.meta
    topic, tags = _topic_and_tags(meta)
    return replace(
        _no_page_labels(page.title, doi),
        label_source="wri.org",
        link=page.url,
        page_match=page.match,
        topic=topic,
        topic_source="wri.org" if topic else None,
        wri_type=_first(meta, "wri_type"),
        authors=tuple(meta.get("citation_author", [])),
        published=_published(meta),
        tags=tags,
        abstract=_abstract(meta),
        initiatives=page.initiatives,
        programs=page.programs,
        topics=_topics(topic, tags),
        concepts=_merged(CONCEPT_BY_KEY.get(tag.casefold(), "") for tag in tags),
    )


def _topics(topic: str | None, tags: Iterable[str]) -> tuple[str, ...]:
    """The main topic first, then every other one of the 11 that WRI's tags name."""
    main = [topic] if topic and topic != NO_TOPIC else []
    return _merged(main, (SITE_TOPICS.get(tag, "") for tag in tags))


def _abstract(meta: dict[str, list[str]]) -> str | None:
    return (
        html.unescape(_first(meta, "description") or _first(meta, "og:description") or "") or None
    )


def _card_line(name: str, values: Iterable[str], separator: str = ", ") -> str:
    values = list(values)
    return f"{name}: {separator.join(values)}" if values else ""


def _front_text(pdf_path: Path) -> str:
    with pymupdf.open(pdf_path) as doc:
        return " ".join(" ".join(page.get_text().split()) for page in list(doc)[:FRONT_PAGES])


def _first(meta: dict[str, list[str]], key: str) -> str | None:
    return meta[key][0] if meta.get(key) else None


def _topic_and_tags(meta: dict[str, list[str]]) -> tuple[str | None, tuple[str, ...]]:
    """The main topic and the secondary tags.

    The topic is `wri_topic` when it maps onto the 11 topics, else the first `article:tag` that
    is one of them, else None (the labeler of a later ticket fills it). An off-list
    `wri_topic` such as the region "Africa" is kept as a tag.
    """
    tags = list(meta.get("article:tag", []))
    site_topic = html.unescape(_first(meta, "wri_topic") or "")
    topic = SITE_TOPICS.get(site_topic)
    if topic is None and site_topic and site_topic not in tags:
        tags.append(site_topic)
    if topic is None:
        topic = next((SITE_TOPICS[tag] for tag in tags if tag in SITE_TOPICS), None)
    return topic, tuple(tags)


def _published(meta: dict[str, list[str]]) -> str | None:
    """The publication date as YYYY-MM-DD, or None.

    `wri_published` ("June 10 2025") is unambiguous. Without it, `citation_publication_date`
    is read as YYYY-DD-MM, the format the site writes it in.
    """
    try:
        if long_date := _first(meta, "wri_published"):
            return datetime.strptime(long_date, "%B %d %Y").date().isoformat()
        if stamp := _first(meta, "citation_publication_date"):
            year, day, month = (int(part) for part in stamp.split("-"))
            return date(year, month, day).isoformat()
    except ValueError:
        return None
    return None
