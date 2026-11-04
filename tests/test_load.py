import json

import pytest

from askwri.load import ChunkRecord, chunk_row, data_api_parameters, document_row, read_chunks

CATALOG_ROW = {
    "doc_id": "urban-water",
    "pdf_file": "urban-water.pdf",
    "label_source": "wri.org",
    "title": "Urban Water Resilience",
    "doi": "10.46830/wrirpt.25.00050",
    "link": "https://www.wri.org/research/urban-water",
    "topic": "Cities",
    "topic_source": "wri.org",
    "wri_type": "Research",
    "authors": ["Ana Silva", "Bo Chen"],
    "published": "2026-10-13",
    "tags": ["Freshwater", "Cities"],
    "doc_type": None,
    "countries": [],
    "summary": None,
}


def test_wri_org_date_is_high_confidence():
    row = document_row(CATALOG_ROW, "abc")
    assert (row["year"], row["pub_date"]) == (2026, "2026-10-13")
    assert (row["date_source"], row["date_confidence"]) == ("wri.org", "high")
    assert row["url"] == "https://www.wri.org/research/urban-water"
    assert row["pdf_key"] == "raw/urban-water.pdf"
    assert json.loads(row["authors"]) == ["Ana Silva", "Bo Chen"]


def test_without_a_date_the_document_is_undated_not_guessed():
    row = document_row({**CATALOG_ROW, "published": None}, "abc")
    assert (row["year"], row["pub_date"]) == (None, None)
    assert (row["date_source"], row["date_confidence"]) == ("none", "undated")


def test_publication_type_comes_from_the_doi_then_the_sorter_then_the_site():
    def pub_type(**fields):
        return document_row({**CATALOG_ROW, **fields}, "abc")["pub_type"]

    assert pub_type(doi="10.46830/wriwp.25.00035", doc_type="research report") == "Working paper"
    assert pub_type(doi="10.46830/writn.24.00028") == "Technical note"
    assert pub_type(doi="10.46830/wrirpt.25.00050") == "Report"
    assert pub_type(doi=None, doc_type="issue brief") == "Issue brief"
    assert pub_type(doi=None, doc_type="research report") == "Report"
    assert pub_type(doi="10.1000/other", doc_type="other") == "Research"  # the site's type


ATTRIBUTES = {
    "chunk_id": "urban-water#p4-2",
    "seq": 7,
    "doc_id": "urban-water",
    "pdf_page": 4,
    "pdf_page_end": 5,
    "printed_page": "2",
    "printed_page_end": "3",
    "printed_page_fallback": False,
    "section": "Findings › Kampala",
    "kind": "source_text",
    "quotable": True,
}


def test_chunk_row_splits_address_from_the_quotable_passage():
    text = "Urban Water Resilience › Findings › Kampala\n\nFloods rose.\n\nCosts fell."
    row = chunk_row(ChunkRecord(ATTRIBUTES, text), [0.5, -0.25])
    assert row["address"] == "Urban Water Resilience › Findings › Kampala"
    assert row["content"] == "Floods rose.\n\nCosts fell."
    assert (row["page"], row["page_end"], row["printed_page"]) == (4, 5, "2")
    assert json.loads(row["embedding"]) == [0.5, -0.25]


def test_chunk_without_an_address_line_fails_loudly():
    with pytest.raises(ValueError, match="urban-water#p4-2"):
        chunk_row(ChunkRecord(ATTRIBUTES, "no address here"), [0.0])


def test_data_api_parameters_keep_types_and_nulls():
    params = data_api_parameters({"a": None, "b": True, "c": 3, "d": "x"})
    assert params == [
        {"name": "a", "value": {"isNull": True}},
        {"name": "b", "value": {"booleanValue": True}},
        {"name": "c", "value": {"longValue": 3}},
        {"name": "d", "value": {"stringValue": "x"}},
    ]


def test_read_chunks_pairs_files_with_sidecars_in_seq_order(tmp_path):
    for seq, name in [(2, "p1-2"), (1, "p1-1")]:
        (tmp_path / f"{name}.txt").write_text(f"Title\n\nPassage {seq}", encoding="utf-8")
        sidecar = {"metadataAttributes": {**ATTRIBUTES, "seq": seq}}
        (tmp_path / f"{name}.txt.metadata.json").write_text(json.dumps(sidecar), encoding="utf-8")
    records = read_chunks(tmp_path)
    assert [r.attributes["seq"] for r in records] == [1, 2]
    assert records[0].indexed_text == "Title\n\nPassage 1"
