"""Labels from the labeler model when wri.org gives none, driven by the fake Claude client."""

import json
from pathlib import Path

import pymupdf
import pytest

from askwri.ingest.__main__ import write_catalog
from askwri.ingest.document import ingest_document
from askwri.ingest.labels import citation_title, label_document
from askwri.ingest.wri_site import WriSite
from askwri.models import MODELS, ModelError
from tests.fake_claude import FakeClaude
from tests.test_wri_labels import FULL_TITLE, OWN_DOI, PAGE_URL, web, wri_page

COVER = "Request for Proposals: Hydrological modelling for the Tana basin"
PARAGRAPH = (
    "Rivers feed farms and cities, and WRI seeks a consultant to model how water moves "
    "through the basin, from rainfall to erosion, so that planners can protect supplies."
)
MODEL_REPLY = {
    "title": "Hydrological modelling for the Tana basin",
    "date": "2025-03-04",
    "doc_type": "RFP",
    "topic": "Freshwater",
    "countries": ["Kenya"],
    "summary": "WRI seeks a consultant to model the Tana basin's hydrology.",
    "deadline": "2025-04-30",
}


def pdf_with_text(
    path: Path, text: str, metadata_title: str = "Untitled", fontsize: int = 10
) -> Path:
    """A one-page PDF holding `text`, long enough to be read as English."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 700), text, fontsize=fontsize)
    doc.set_metadata({"title": metadata_title})
    doc.save(path)
    return path


def reply(**changes) -> str:
    return json.dumps(MODEL_REPLY | changes)


def test_a_document_with_no_page_gets_its_labels_from_the_model(tmp_path):
    pdf = pdf_with_text(tmp_path / "newsletter-march.pdf", "Our March newsletter on rivers.")
    client = FakeClaude(reply(doc_type="newsletter"))

    labels = label_document(pdf, "newsletter-march", WriSite(web()), client)

    assert labels.label_source == "model"
    assert labels.title == MODEL_REPLY["title"]
    assert labels.published == "2025-03-04"
    assert (labels.doc_type, labels.topic, labels.topic_source) == (
        "newsletter",
        "Freshwater",
        "model",
    )
    assert labels.countries == ("Kenya",)
    assert labels.summary == MODEL_REPLY["summary"]
    assert (labels.link, labels.wri_type, labels.page_match) == (None, None, None)


def test_the_model_reads_only_the_first_pages_as_text_with_the_labeler_role(tmp_path):
    doc = pymupdf.open()
    for number in range(1, 8):
        doc.new_page().insert_text((50, 70), f"Words on page {number}.")
    doc.save(tmp_path / "newsletter-march.pdf")
    client = FakeClaude(reply(doc_type="newsletter"))

    label_document(tmp_path / "newsletter-march.pdf", "t", WriSite(web()), client)

    (request,) = client.requests
    assert request["model"] == MODELS["labeler"]
    (message,) = request["messages"]
    assert [block["type"] for block in message["content"]] == ["text"]
    prompt = message["content"][0]["text"]
    assert "Words on page 1." in prompt
    assert "Words on page 7." not in prompt
    assert request["output_config"]["format"]["type"] == "json_schema"


def test_the_text_sent_to_the_model_is_capped(tmp_path):
    long_text = "Opening words. " + "filler " * 4000 + "Closing words."
    pdf = pdf_with_text(tmp_path / "newsletter-march.pdf", long_text, fontsize=3)
    client = FakeClaude(reply(doc_type="newsletter"))

    label_document(pdf, "t", WriSite(web()), client)

    prompt = client.requests[0]["messages"][0]["content"][0]["text"]
    assert "Opening words." in prompt
    assert "Closing words." not in prompt


def test_an_rfp_also_gets_a_deadline_and_its_country_in_countries(tmp_path):
    pdf = pdf_with_text(tmp_path / "rfp-tana-basin.pdf", COVER)
    client = FakeClaude(reply())

    labels = label_document(pdf, "rfp-tana-basin", WriSite(web()), client)

    assert (labels.countries, labels.deadline) == (("Kenya",), "2025-04-30")
    schema = client.requests[0]["output_config"]["format"]["schema"]
    assert "deadline" in schema["properties"]
    assert "country" not in schema["properties"]


def test_other_documents_are_not_asked_for_a_deadline(tmp_path):
    pdf = pdf_with_text(tmp_path / "newsletter-march.pdf", "Our March newsletter on rivers.")
    client = FakeClaude(reply(doc_type="newsletter"))

    labels = label_document(pdf, "newsletter-march", WriSite(web()), client)

    schema = client.requests[0]["output_config"]["format"]["schema"]
    assert "deadline" not in schema["properties"]
    assert labels.deadline is None


def test_the_topic_is_limited_to_the_eleven_or_none(tmp_path):
    pdf = pdf_with_text(tmp_path / "rfp-tana-basin.pdf", COVER)
    schema_client = FakeClaude(reply())
    label_document(pdf, "t", WriSite(web()), schema_client)
    topics = schema_client.requests[0]["output_config"]["format"]["schema"]["properties"]["topic"]
    assert len(topics["enum"]) == 12
    assert "none" in topics["enum"]

    assert label_document(pdf, "t", WriSite(web()), FakeClaude(reply(topic="none"))).topic == "none"
    with pytest.raises(ValueError, match="Water"):
        label_document(pdf, "t", WriSite(web()), FakeClaude(reply(topic="Water")))


def test_a_date_the_model_cannot_give_is_left_empty(tmp_path):
    pdf = pdf_with_text(tmp_path / "rfp-tana-basin.pdf", COVER)

    labels = label_document(pdf, "t", WriSite(web()), FakeClaude(reply(date="", deadline="soon")))

    assert (labels.published, labels.deadline) == (None, None)


def test_a_refusal_fails_the_document_loudly(tmp_path):
    pdf = pdf_with_text(tmp_path / "rfp-tana-basin.pdf", COVER)

    with pytest.raises(ModelError, match="rfp-tana-basin.pdf"):
        label_document(pdf, "t", WriSite(web()), FakeClaude({"stop_reason": "refusal"}))


def test_without_a_client_a_document_with_no_page_stays_no_page(tmp_path):
    pdf = pdf_with_text(tmp_path / "rfp-tana-basin.pdf", COVER)

    labels = label_document(pdf, "t", WriSite(web()))

    assert (labels.label_source, labels.topic, labels.topic_source) == ("no page", None, None)


def report_with_citation(path: Path, metadata_title: str) -> Path:
    """A report whose suggested citation quotes its real title but whose metadata does not.

    The quotes are straight because the built-in PDF font has no curly ones.
    """
    text = (
        f'Suggested citation: Doe, J., and R. Rao. 2025. "{FULL_TITLE}." Report. '
        f"Washington, DC: World Resources Institute. Available online at doi.org/{OWN_DOI}."
    )
    return pdf_with_text(path, text, metadata_title)


@pytest.mark.parametrize("bad_title", ["HIGHLIGHTS", "wri-report-final-v3"])
def test_the_citation_title_finds_the_page_when_the_metadata_title_is_unusable(tmp_path, bad_title):
    pdf = report_with_citation(tmp_path / "r.pdf", bad_title)
    client = FakeClaude()

    labels = label_document(pdf, bad_title, WriSite(web(doi_page=wri_page())), client)

    assert (labels.label_source, labels.link, labels.title) == ("wri.org", PAGE_URL, FULL_TITLE)
    assert client.requests == []


def test_the_citation_title_is_not_retried_when_it_is_the_title_already_tried(tmp_path):
    pdf = report_with_citation(tmp_path / "r.pdf", FULL_TITLE)
    fake = web(doi_page=wri_page(title="Something Else Entirely"))

    labels = label_document(pdf, FULL_TITLE, WriSite(fake), FakeClaude(reply(doc_type="other")))

    assert labels.label_source == "model"
    assert fake.requested.count(f"https://doi.org/{OWN_DOI}") == 1


def test_the_model_is_used_when_the_citation_title_finds_no_page_either(tmp_path):
    pdf = report_with_citation(tmp_path / "r.pdf", "HIGHLIGHTS")
    client = FakeClaude(reply(doc_type="other"))

    labels = label_document(pdf, "HIGHLIGHTS", WriSite(web()), client)

    assert (labels.label_source, labels.link) == ("model", None)


def test_citation_title_reads_the_quoted_title_after_the_suggested_citation():
    text = 'Foreword. "A quoted aside." Suggested Citation: Doe, J. 2025. “Driving Forward.” Note.'

    assert citation_title(text) == "Driving Forward"
    assert citation_title("Available online at doi.org/10.46830/x. “Later quote here.”") is None
    assert citation_title("no citation block") is None


def test_a_page_with_a_topic_keeps_every_wri_value_and_never_calls_the_model(tmp_path):
    pdf = report_with_citation(tmp_path / "r.pdf", FULL_TITLE)
    client = FakeClaude()

    labels = label_document(pdf, FULL_TITLE, WriSite(web(doi_page=wri_page())), client)

    assert (labels.topic, labels.topic_source) == ("Equity", "wri.org")
    assert client.requests == []


def test_a_page_with_no_usable_topic_gets_only_its_topic_from_the_model(tmp_path):
    pdf = report_with_citation(tmp_path / "r.pdf", FULL_TITLE)
    page = wri_page(topic="Africa", tags=("land use",))
    client = FakeClaude(json.dumps({"topic": "Forests"}))

    labels = label_document(pdf, FULL_TITLE, WriSite(web(doi_page=page)), client)

    assert (labels.label_source, labels.topic, labels.topic_source) == (
        "wri.org",
        "Forests",
        "model",
    )
    assert (labels.title, labels.link, labels.published) == (FULL_TITLE, PAGE_URL, "2023-05-16")
    assert labels.tags == ("land use", "Africa")
    assert labels.summary is None
    schema = client.requests[0]["output_config"]["format"]["schema"]
    assert list(schema["properties"]) == ["topic"]


def test_an_off_list_topic_for_a_page_is_rejected_too(tmp_path):
    pdf = report_with_citation(tmp_path / "r.pdf", FULL_TITLE)
    page = wri_page(topic=None, tags=())

    with pytest.raises(ValueError, match="Water"):
        label_document(
            pdf, FULL_TITLE, WriSite(web(doi_page=page)), FakeClaude(json.dumps({"topic": "Water"}))
        )


def test_ingest_records_the_model_as_the_source_in_the_catalog_and_on_every_chunk(tmp_path):
    pdf = tmp_path / "rfp-tana-basin.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), "Hydrological modelling", fontsize=22, fontname="hebo")
    page.insert_textbox(pymupdf.Rect(50, 100, 550, 300), COVER + ". " + PARAGRAPH, fontsize=10)
    doc.save(pdf)

    result = ingest_document(pdf, WriSite(web()), FakeClaude(reply()))
    write_catalog([result], tmp_path / "out")

    assert result.chunks
    assert {(c.label_source, c.topic, c.year, c.link) for c in result.chunks} == {
        ("model", "Freshwater", 2025, None)
    }
    (row,) = json.loads((tmp_path / "out" / "catalog.json").read_text())
    assert (row["label_source"], row["topic"], row["topic_source"]) == (
        "model",
        "Freshwater",
        "model",
    )
    assert (row["doc_type"], row["deadline"]) == ("RFP", "2025-04-30")
    assert "rfp_country" not in row
    assert (row["countries"], row["summary"]) == (["Kenya"], MODEL_REPLY["summary"])
