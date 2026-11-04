"""Document labels from wri.org, driven through synthetic PDFs and a fake web."""

import json
from pathlib import Path

import pymupdf
import pytest

from askwri.ingest.__main__ import write_catalog, write_chunks
from askwri.ingest.document import ingest_document
from askwri.ingest.labels import label_document
from askwri.ingest.wri_site import Response, WriSite, part_of

OWN_DOI = "10.46830/wrirpt.24.00006"
CITED_DOI = "10.46830/wrirpt.21.00145"
TITLE = "Restoring Degraded Land"
FULL_TITLE = "Restoring Degraded Land: A Guide for Landscape Planners"
PAGE_URL = "https://www.wri.org/research/restoring-degraded-land-guide-landscape-planners"
SITEMAP = "https://www.wri.org/sitemap.xml"


def report_pdf(path: Path, printed_doi: str | None = f"doi.org/{OWN_DOI}") -> Path:
    """A report whose body cites another WRI DOI before its own suggested-citation block."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), TITLE, fontsize=22, fontname="hebo")
    page.insert_textbox(
        pymupdf.Rect(50, 120, 550, 200),
        f"This builds on earlier work, see https://doi.org/{CITED_DOI} for the method.",
        fontsize=10,
    )
    citation = "Suggested citation: Doe, J. 2025. Restoring Degraded Land. Report. Washington, DC: "
    citation += "World Resources Institute."
    if printed_doi:
        citation += f" Available online at {printed_doi}."
    page.insert_textbox(pymupdf.Rect(50, 220, 550, 320), citation, fontsize=10)
    doc.set_metadata({"title": TITLE})
    doc.save(path)
    return path


def wri_page(
    title: str = FULL_TITLE,
    topic: str | None = "Equity &amp; Governance",
    published: str | None = "2023-16-05",
    long_date: str | None = "May 16 2023",
    tags: tuple[str, ...] = ("land restoration", "Equity"),
) -> str:
    """The head of a wri.org research page, with the meta tags the pipeline reads."""
    tags_html = [
        f'<meta name="citation_title" content="{title}" />',
        '<meta name="wri_type" content="Research" />',
        '<meta name="citation_author" content="Jane Doe" />',
        '<meta name="citation_author" content="Ravi Rao" />',
        *[f'<meta property="article:tag" content="{tag}" />' for tag in tags],
    ]
    if published:
        tags_html.append(f'<meta name="citation_publication_date" content="{published}" />')
    if long_date:
        tags_html.append(f'<meta name="wri_published" content="{long_date}" />')
    if topic:
        tags_html.append(f'<meta name="wri_topic" content="{topic}" />')
    return "<html><head>" + "".join(tags_html) + "</head><body></body></html>"


class FakeWeb:
    """Answers fetches from a dict of URL to response, and remembers every URL asked for."""

    def __init__(self, pages: dict[str, Response]):
        self.pages = pages
        self.requested: list[str] = []

    def __call__(self, url: str) -> Response:
        self.requested.append(url)
        return self.pages.get(url, Response(url, 404, ""))


def web(doi_page: str | None = None, sitemap_slugs: tuple[str, ...] = (), **pages: str) -> FakeWeb:
    """A fake web: the DOI redirects to PAGE_URL, and the sitemap lists the given research slugs."""
    responses = {url: Response(url, 200, html) for url, html in pages.items()}
    if doi_page is not None:
        responses[f"https://doi.org/{OWN_DOI}"] = Response(PAGE_URL + "?auHash=x", 200, doi_page)
    child = f"{SITEMAP}?page=1"
    responses[SITEMAP] = Response(SITEMAP, 200, f"<sitemapindex><loc>{child}</loc></sitemapindex>")
    urls = "".join(
        f"<url><loc>https://www.wri.org/research/{slug}</loc></url>" for slug in sitemap_slugs
    )
    urls += "<url><loc>https://www.wri.org/climate</loc></url>"
    responses[child] = Response(child, 200, f"<urlset>{urls}</urlset>")
    return FakeWeb(responses)


def test_the_documents_own_doi_is_used_not_one_it_cites(tmp_path):
    fake = web(doi_page=wri_page())
    fake.pages[f"https://doi.org/{CITED_DOI}"] = Response(
        "https://www.wri.org/research/other", 200, wri_page(title="Something Else Entirely")
    )

    labels = label_document(report_pdf(tmp_path / "r.pdf"), TITLE, WriSite(fake))

    assert (labels.doi, labels.link, labels.label_source) == (OWN_DOI, PAGE_URL, "wri.org")
    assert labels.page_match == "doi"
    assert f"https://doi.org/{CITED_DOI}" not in fake.requested


def test_a_doi_broken_by_a_space_after_the_slash_is_still_found(tmp_path):
    pdf = report_pdf(tmp_path / "r.pdf", printed_doi=OWN_DOI.replace("/", "/ "))

    labels = label_document(pdf, TITLE, WriSite(web(wri_page())))

    assert (labels.doi, labels.page_match) == (OWN_DOI, "doi")


def test_labels_come_from_the_page_meta_tags(tmp_path):
    labels = label_document(report_pdf(tmp_path / "r.pdf"), TITLE, WriSite(web(wri_page())))

    assert labels.title == FULL_TITLE
    assert labels.topic == "Equity"
    assert labels.wri_type == "Research"
    assert labels.authors == ("Jane Doe", "Ravi Rao")
    assert labels.tags == ("land restoration", "Equity")
    assert labels.published == "2023-05-16"


@pytest.mark.parametrize(
    ("site_topic", "topic"),
    [("Equity &amp; Governance", "Equity"), ("Equity & Governance", "Equity"), ("Ocean", "Ocean")],
)
def test_site_topics_map_onto_the_eleven_topics(tmp_path, site_topic, topic):
    page = wri_page(topic=site_topic)

    labels = label_document(report_pdf(tmp_path / "r.pdf"), TITLE, WriSite(web(page)))

    assert labels.topic == topic


@pytest.mark.parametrize(
    ("site_topic", "tags", "topic", "kept_tags"),
    [
        ("Climate", ("Finance",), "Climate", ("Finance",)),  # the site topic wins over tags
        (
            None,
            ("mitigation", "Climate", "Finance"),
            "Climate",
            ("mitigation", "Climate", "Finance"),
        ),
        ("Africa", ("Finance",), "Finance", ("Finance", "Africa")),  # off-list value kept as a tag
        ("Africa", ("land use",), None, ("land use", "Africa")),
        (None, ("land use",), None, ("land use",)),
    ],
)
def test_the_topic_falls_back_to_a_tag_and_never_stops_the_run(
    tmp_path, site_topic, tags, topic, kept_tags
):
    page = wri_page(topic=site_topic, tags=tags)

    labels = label_document(report_pdf(tmp_path / "r.pdf"), TITLE, WriSite(web(page)))

    assert (labels.topic, labels.tags) == (topic, kept_tags)
    assert labels.label_source == "wri.org"


@pytest.mark.parametrize(
    ("published", "long_date", "expected"),
    [
        ("2025-10-06", "June 10 2025", "2025-06-10"),  # wri_published wins over the stamp
        ("2025-10-06", "October 6 2025", "2025-10-06"),
        ("2023-16-05", None, "2023-05-16"),  # no wri_published: the stamp is year-day-month
        ("2024-09-12", None, "2024-12-09"),
        ("1988-01-01", None, "1988-01-01"),
        (None, None, None),  # no date at all: left empty, no error
        ("garbled", None, None),
    ],
)
def test_the_publication_date_comes_from_wri_published_else_the_stamp(
    tmp_path, published, long_date, expected
):
    page = wri_page(published=published, long_date=long_date)

    labels = label_document(report_pdf(tmp_path / "r.pdf"), TITLE, WriSite(web(page)))

    assert labels.published == expected


def test_without_a_doi_the_pdf_title_is_matched_against_the_sitemap(tmp_path):
    slug = "restoring-degraded-land-guide-landscape-planners"
    fake = web(
        sitemap_slugs=("unrelated-report", slug),
        **{f"https://www.wri.org/research/{slug}": wri_page()},
    )

    labels = label_document(report_pdf(tmp_path / "r.pdf", printed_doi=None), TITLE, WriSite(fake))

    assert (labels.link, labels.page_match, labels.doi) == (PAGE_URL, "title", None)
    assert labels.topic == "Equity"
    assert "https://www.wri.org/research/unrelated-report" not in fake.requested


def test_a_doi_that_resolves_to_a_different_title_falls_back_to_the_sitemap(tmp_path):
    slug = "restoring-degraded-land-guide-landscape-planners"
    fake = web(
        doi_page=wri_page(title="Restauración de tierras degradadas"),
        sitemap_slugs=(slug,),
        **{f"https://www.wri.org/research/{slug}": wri_page()},
    )

    labels = label_document(report_pdf(tmp_path / "r.pdf"), TITLE, WriSite(fake))

    assert (labels.link, labels.page_match, labels.doi) == (PAGE_URL, "title", OWN_DOI)


def test_a_sitemap_page_whose_title_differs_is_not_accepted(tmp_path):
    slug = "restoring-degraded-land-guide-landscape-planners"
    other = wri_page(title="Protecting Wetlands: A Guide for Landscape Planners")
    fake = web(sitemap_slugs=(slug,), **{f"https://www.wri.org/research/{slug}": other})

    labels = label_document(report_pdf(tmp_path / "r.pdf", printed_doi=None), TITLE, WriSite(fake))

    assert labels.label_source == "no page"
    assert labels.link is None


def test_no_page_found_leaves_only_the_source_recorded(tmp_path):
    fake = web(sitemap_slugs=("unrelated-report",))

    labels = label_document(report_pdf(tmp_path / "r.pdf"), TITLE, WriSite(fake))

    assert labels.label_source == "no page"
    assert (labels.link, labels.page_match, labels.topic, labels.published) == (None,) * 4
    assert (labels.authors, labels.tags) == ((), ())
    assert labels.doi == OWN_DOI  # printed in the PDF even though its page could not be found


def test_the_sitemap_is_fetched_once_per_run(tmp_path):
    fake = web(sitemap_slugs=("unrelated-report",))
    site = WriSite(fake)

    for name in ("a.pdf", "b.pdf"):
        label_document(report_pdf(tmp_path / name, printed_doi=None), TITLE, site)

    assert fake.requested.count(SITEMAP) == 1


def test_ingest_puts_the_filter_labels_on_every_chunk_and_the_catalog_row(tmp_path):
    pdf = report_pdf(tmp_path / "Restoring Degraded Land.pdf")

    result = ingest_document(pdf, WriSite(web(wri_page())))
    write_chunks(result.chunks, tmp_path / "out")
    write_catalog([result], tmp_path / "out")

    assert result.chunks
    for chunk in result.chunks:
        assert (chunk.topic, chunk.year, chunk.link, chunk.label_source, chunk.wri_type) == (
            "Equity",
            2023,
            PAGE_URL,
            "wri.org",
            "Research",
        )
        assert chunk.tags == ("land restoration", "Equity")
    sidecar = next((tmp_path / "out").glob("*/*.metadata.json"))
    attributes = json.loads(sidecar.read_text())["metadataAttributes"]
    assert attributes["topic"] == "Equity"
    assert attributes["year"] == 2023
    assert attributes["link"] == PAGE_URL
    assert attributes["label_source"] == "wri.org"
    assert attributes["tags"] == ["land restoration", "Equity"]
    (row,) = json.loads((tmp_path / "out" / "catalog.json").read_text())
    assert row["doc_id"] == "restoring-degraded-land"
    assert row["pdf_file"] == "Restoring Degraded Land.pdf"
    assert (row["topic"], row["published"], row["doi"], row["link"]) == (
        "Equity",
        "2023-05-16",
        OWN_DOI,
        PAGE_URL,
    )


def test_a_document_without_a_page_cites_its_pdf_and_records_why(tmp_path):
    pdf = report_pdf(tmp_path / "r.pdf", printed_doi=None)

    result = ingest_document(pdf, WriSite(web(sitemap_slugs=())))
    write_chunks(result.chunks, tmp_path / "out")
    write_catalog([result], tmp_path / "out")

    assert {(c.label_source, c.link, c.topic, c.year) for c in result.chunks} == {
        ("no page", None, None, None)
    }
    sidecar = next((tmp_path / "out").glob("*/*.metadata.json"))
    attributes = json.loads(sidecar.read_text())["metadataAttributes"]
    assert attributes["label_source"] == "no page"
    assert not {"topic", "year", "link", "tags"} & attributes.keys()
    (row,) = json.loads((tmp_path / "out" / "catalog.json").read_text())
    assert (row["label_source"], row["link"], row["pdf_file"]) == ("no page", None, "r.pdf")


def test_part_of_reads_initiatives_and_programs_from_the_taxonomy_line():
    # As wri.org writes it, with two spaces after "div".
    page = (
        '<div  class="narrative-taxonomy">\n  <p>This Working Paper is part of '
        '<a href="/initiatives/ocean-climate-diplomacy">Ocean Climate Diplomacy</a> within '
        '<a href="/energy">Energy</a> and <a href="/initiatives/clean-energy-supply">Clean '
        'Energy</a>. Reach out to <a href="/project-experts/1">an Initiative Expert</a>.</p>'
    )

    assert part_of(page) == (("Ocean Climate Diplomacy",), ("Energy", "Clean Energy"))
    assert part_of("<p>No taxonomy line here.</p>") == ((), ())
