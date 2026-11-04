import pytest

from askwri.tools.authors import people
from askwri.tools.coverage import coverage_sql
from askwri.tools.passage import split_rows
from askwri.tools.search import matched_terms, rerank, search_parameters, to_result
from askwri.tools.translate import cache_key, numbers, numbers_preserved


def test_search_needs_a_query_and_defaults_to_including_undated():
    with pytest.raises(ValueError):
        search_parameters({"query": "  "})
    params = search_parameters({"query": " heat ", "year_from": 2010})
    assert params["query"] == "heat"
    assert params["include_undated"] is True
    assert params["year_from"] == 2010 and params["country"] is None


def test_matched_terms_reads_headline_marks_without_repeats():
    assert matched_terms("«Urban» heat in «cities» and «urban» areas") == ["Urban", "cities"]
    assert matched_terms("no marks here") == []


ROW = {
    "chunk_id": "heat#p4-1",
    "doc_id": "heat",
    "title": "Heat",
    "url": None,
    "doi": None,
    "year": 2026,
    "date_confidence": "high",
    "date_source": "wri.org",
    "pub_type": "Research",
    "office": None,
    "topic": "Cities",
    "language": "en",
    "page": 6,
    "printed_page": "4",
    "section": "Findings",
    "kind": "source_text",
    "quotable": True,
    "address": "Heat › Findings",
    "content": "Cities warm fast.",
    "by_meaning": True,
    "by_keyword": False,
    "matched": "«Cities» warm fast.",
    "label_source": "wri.org",
    "pdf_key": "raw/heat.pdf",
}


def test_result_explains_why_it_matched_and_keeps_citation_fields():
    result = to_result(ROW, 0.91234)
    assert result["relevance"] == 0.9123
    assert (result["page"], result["printed_page"], result["passage"]) == (
        6,
        "4",
        "Cities warm fast.",
    )
    # A passage found only by meaning shows no keyword terms, even if the headline marked some.
    assert result["why"] == {
        "by_meaning": True,
        "by_keyword": False,
        "matched_terms": [],
        "date_source": "wri.org",
        "label_source": "wri.org",
        "type_weight": 1.0,
    }


def test_publication_type_breaks_near_ties_but_never_beats_a_clearly_better_passage():
    from askwri.tools.search import by_evidence_weight

    paper, report, brief = ({"pub_type": t} for t in ("Working paper", "Report", "Issue brief"))
    near_tie = [(paper, 0.50), (report, 0.47), (brief, 0.46)]
    assert by_evidence_weight(near_tie, 2) == [(report, 0.47), (paper, 0.50)]  # raw scores kept
    clear = [(paper, 0.80), (report, 0.40)]
    assert by_evidence_weight(clear, 2) == clear


class FakeReranker:
    def __init__(self, order):
        self.order, self.request = order, None

    def rerank(self, **request):
        self.request = request
        return {"results": [{"index": i, "relevanceScore": s} for i, s in self.order]}


def test_rerank_returns_rows_in_the_model_order_with_scores(monkeypatch):
    monkeypatch.setenv("ASKWRI_RERANK_MODEL_ARN", "arn:rerank")
    rows = [{"address": "A", "content": "a"}, {"address": "B", "content": "b"}]
    client = FakeReranker([(1, 0.9), (0, 0.2)])
    assert rerank("q", rows, 2, client) == [(rows[1], 0.9), (rows[0], 0.2)]
    sources = client.request["sources"]
    assert sources[0]["inlineDocumentSource"]["textDocument"]["text"] == "A\n\na"


def test_passage_is_split_from_its_neighbours_in_order():
    def row(seq):
        return {
            "chunk_id": f"d#{seq}",
            "seq": seq,
            "content": f"text {seq}",
            "page": 1,
            "page_end": 1,
            "printed_page": "1",
            "printed_page_end": "1",
            "section": "",
            "kind": "source_text",
            "quotable": True,
            "doc_id": "d",
            "title": "T",
            "url": None,
            "doi": None,
            "year": None,
            "date_confidence": "undated",
            "pub_type": None,
            "office": None,
            "authors": [],
            "language": None,
        }

    shaped = split_rows([row(1), row(2), row(3)], "d#2")
    assert shaped["passage"]["content"] == "text 2"
    assert (shaped["before"], shaped["after"]) == (["text 1"], ["text 3"])
    with pytest.raises(ValueError):
        split_rows([row(1)], "d#9")


def test_coverage_refuses_unknown_dimensions():
    assert "unnest(d.countries)" in coverage_sql("country")
    with pytest.raises(ValueError):
        coverage_sql("d.topic; DROP TABLE documents")


def test_people_lists_each_author_once_most_prolific_first():
    documents = [
        {"doc_id": "a", "authors": ["Bo", "Ana"]},
        {"doc_id": "b", "authors": ["Ana"]},
    ]
    assert people(documents) == [
        {"name": "Ana", "doc_ids": ["a", "b"]},
        {"name": "Bo", "doc_ids": ["a"]},
    ]


def test_numbers_ignore_language_specific_separators():
    assert numbers("1,000.5 tonnes in 2019 (45%)") == sorted(["10005", "2019", "45"])
    assert numbers("1.000,5 toneladas en 2019 (45 %)") == sorted(["10005", "2019", "45"])


def test_number_check_catches_changed_and_dropped_numbers():
    source = "Emissions fell 12% between 2015 and 2019 [3]."
    assert numbers_preserved(source, "Las emisiones cayeron 12% entre 2015 y 2019 [3].") == []
    assert numbers_preserved(source, "Las emisiones cayeron 21% entre 2015 y 2019 [3].") == ["12"]
    assert numbers_preserved(source, "Las emisiones cayeron entre 2015 y 2019 [3].") == ["12"]
    # Two numbers separated by a space stay two numbers.
    assert numbers("in 2019 15 cities") == ["15", "2019"]


def test_cache_key_depends_on_language_and_text():
    assert cache_key("hello", "es") != cache_key("hello", "pt")
    assert cache_key("hello", "es") == cache_key("hello", "es")
