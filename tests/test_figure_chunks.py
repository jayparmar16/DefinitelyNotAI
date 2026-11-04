"""Picture chunks, driven through a synthetic PDF with a captioned chart and the fake model client."""

import json
from pathlib import Path

import pymupdf
import pytest

from askwri.ingest.document import ingest_document
from askwri.models import MODELS, ModelError
from tests.fake_claude import FakeClaude

PARAGRAPH = (
    "Forests store large amounts of carbon and support the livelihoods of many communities. "
    "Protecting them requires secure land rights, transparent monitoring and finance that "
    "reaches local groups. "
)
LABELS = json.dumps(
    {
        "title": "Forest Cover",
        "date": "2025-01-01",
        "doc_type": "other",
        "topic": "Forests",
        "countries": [],
        "summary": "Forest cover charts.",
    }
)
DESCRIPTION = "A bar chart of forest cover in million hectares; Brazil is highest, about 150."


def draw_bar_chart(page, top: float) -> None:
    """Bars with country labels under them and a unit label beside the axis."""
    page.draw_line((90, top + 200), (500, top + 200))
    page.draw_line((90, top), (90, top + 200))
    for n, height in enumerate((120, 80, 150, 60)):
        left = 110 + n * 90
        page.draw_rect(
            pymupdf.Rect(left, top + 200 - height, left + 50, top + 200), fill=(0.2, 0.5, 0.3)
        )
        page.insert_text((left, top + 215), f"Brazil{n}", fontsize=8)
    page.insert_text((60, top + 100), "Mha", fontsize=8)


def chart_report(path: Path) -> Path:
    """Page 1: a logo, text, "Figure 1" above a bar chart, then text. Page 2: a large picture with no caption."""
    doc = pymupdf.open()
    page = doc.new_page()
    logo = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    logo.set_rect(logo.irect, (200, 0, 0))
    page.insert_image(pymupdf.Rect(500, 20, 530, 50), pixmap=logo)
    page.insert_text((50, 60), "Findings", fontsize=15, fontname="hebo")
    page.insert_textbox(pymupdf.Rect(50, 70, 550, 170), PARAGRAPH * 3, fontsize=10)
    page.insert_text((50, 190), "Figure 1 | Forest cover by country, 2020", fontsize=10)
    draw_bar_chart(page, 200)
    page.insert_textbox(
        pymupdf.Rect(50, 440, 550, 540), PARAGRAPH.replace("Forests", "Peatlands") * 3, fontsize=10
    )
    banner = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 150), False)
    banner.set_rect(banner.irect, (30, 90, 160))
    doc.new_page().insert_image(pymupdf.Rect(100, 100, 500, 400), pixmap=banner)
    doc.set_metadata({"title": "Forest Cover"})
    doc.save(path)
    return path


class ScriptedClaude(FakeClaude):
    """Answers each kind of request: the vision description, the decorative check, the labels."""

    def __init__(self, informative: bool = True):
        super().__init__()
        self.informative = informative

    def _create(self, **request):
        schema = request.get("output_config", {}).get("format", {}).get("schema", {})
        if "informative" in schema.get("properties", {}):
            reply = json.dumps({"informative": self.informative})
        elif "description" in schema.get("properties", {}):
            reply = json.dumps({"kind": "chart", "description": DESCRIPTION})
        else:
            reply = LABELS
        self.replies = [reply]
        return super()._create(**request)

    def calls(self, model: str) -> list[dict]:
        return [r for r in self.requests if r["model"] == model]


@pytest.fixture(scope="module")
def chart_pdf(tmp_path_factory) -> Path:
    return chart_report(tmp_path_factory.mktemp("pdf") / "forest-cover.pdf")


def test_a_captioned_chart_is_a_chunk_with_its_description_and_is_not_quotable(chart_pdf):
    result = ingest_document(chart_pdf, client=ScriptedClaude())

    assert result.audit.passed, result.audit.failures
    (chart, *_) = [c for c in result.chunks if c.kind == "chart"]
    assert chart.text == "Figure 1 | Forest cover by country, 2020"
    assert (chart.number, chart.pdf_page, chart.section) == ("Figure 1", 1, "Findings")
    assert chart.description == DESCRIPTION
    assert DESCRIPTION in chart.indexed_text
    assert not chart.quotable
    assert chart.figure.png.startswith(b"\x89PNG")


def test_a_logo_gets_no_model_call_and_no_chunk(chart_pdf):
    client = ScriptedClaude()
    result = ingest_document(chart_pdf, client=client)

    assert result.pictures.small == 1
    assert len(client.calls(MODELS["vision"])) == result.pictures.described == 2


def test_text_inside_a_picture_goes_to_the_model_and_leaves_the_text_chunks(chart_pdf):
    client = ScriptedClaude()
    result = ingest_document(chart_pdf, client=client)

    text = "\n".join(c.text for c in result.chunks if c.kind == "source_text")
    assert "Brazil" not in text and "Mha" not in text
    assert "Peatlands store" in text
    prompt = client.calls(MODELS["vision"])[0]["messages"][0]["content"][-1]["text"]
    assert "Brazil0" in prompt and "Mha" in prompt


def test_an_uncaptioned_picture_judged_decorative_is_dropped_and_chunks_stay_contiguous(chart_pdf):
    client = ScriptedClaude(informative=False)
    result = ingest_document(chart_pdf, client=client)

    assert result.pictures.decorative == 1  # the picture on page 2
    assert [c.kind for c in result.chunks if c.pdf_page == 2] == []
    assert [c.seq for c in result.chunks] == list(range(1, len(result.chunks) + 1))


def test_a_model_refusal_fails_the_document(chart_pdf):
    with pytest.raises(ModelError, match="forest-cover.*vision call did not finish"):
        ingest_document(chart_pdf, client=FakeClaude({"stop_reason": "refusal"}))
