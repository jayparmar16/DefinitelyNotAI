"""The evaluation's scoring arithmetic: per-question metrics, pooling and coverage."""

from evals.run import coverage, pooled_useful_docs, question_metrics


def hit(doc_id: str, score: int, year: int = 2025) -> dict:
    return {"doc_id": doc_id, "score": score, "year": year}


def test_question_metrics_count_documents_helpful_passages_and_the_year_share():
    hits = [hit("a", 2), hit("a", 1), hit("b", 2, year=2023), hit("c", 0)]

    m = question_metrics({"years": [2025]}, hits)

    assert (m["results"], m["documents"], m["helps"], m["gain"]) == (4, 3, 2, 5)
    assert m["useful_docs"] == ["a", "b"]
    assert m["in_years"] == 0.75
    assert "declined" not in m


def test_an_unanswerable_question_is_declined_only_when_nothing_comes_back():
    assert question_metrics({"unanswerable": True}, [])["declined"] is True
    related_only = question_metrics({"unanswerable": True}, [hit("a", 1)])
    assert (related_only["declined"], related_only["safe"]) == (False, True)
    assert question_metrics({"unanswerable": True}, [hit("a", 2)])["safe"] is False


def test_coverage_is_the_share_of_every_run_s_useful_documents_this_run_found():
    runs = [
        {"q": {"metrics": {"useful_docs": ["a", "b"]}}},
        {"q": {"metrics": {"useful_docs": ["b", "c", "d"]}}},
    ]

    pool = pooled_useful_docs(runs)

    assert pool == {"q": {"a", "b", "c", "d"}}
    assert coverage(["a", "b"], pool["q"]) == 0.5
    assert coverage([], set()) is None
