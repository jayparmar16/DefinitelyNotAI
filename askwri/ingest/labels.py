"""Document labels: WRI's own from its wri.org page, the labeler model's where the page has none."""

import html
import re
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from pathlib import Path

import pymupdf

from askwri.ingest.classify import detect_doc_type
from askwri.ingest.model_labels import TOPICS, label_from_text, topic_from_text
from askwri.ingest.text import comparable
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
        labels = replace(labels, topic=topic, topic_source="model")
    return labels


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
    """The label fields every chunk of the document carries, for filtering at search time."""
    return {
        "label_source": labels.label_source,
        "link": labels.link,
        "year": int(labels.published[:4]) if labels.published else None,
        "topic": labels.topic,
        "wri_type": labels.wri_type,
        "tags": labels.tags,
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
    )


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
