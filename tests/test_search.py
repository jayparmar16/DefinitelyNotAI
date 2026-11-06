"""Hybrid search: filter parameters, rerank order and cut, no padding, neighbours; fakes only."""

import io
import json

import pytest

from askwri import search

TARGET = {"resourceArn": "cluster", "secretArn": "secret", "database": "askwri"}


def row(chunk_id: str, content: str = "x" * 500, description: str | None = None) -> dict:
    return {
        "chunk_id": chunk_id, "doc_id": "doc", "title": "A report", "link": "https://wri.org/a",
        "pdf_page": 3, "pdf_page_end": 3, "printed_page": "3", "printed_page_end": "3",
        "section": "Results", "kind": "source_text", "quotable": True, "content": content,
        "description": description, "number": None, "figure_key": None,
    }  # fmt: skip


class FakeDataApi:
    """Answers the hybrid statement with `candidates` and the neighbour statement with `near`."""

    def __init__(self, candidates: list[dict], near: list[dict] = ()):
        self.candidates, self.near = candidates, list(near)
        self.statements = []

    def begin_transaction(self, **kwargs):
        return {"transactionId": "tx"}

    def commit_transaction(self, **kwargs):
        pass

    def execute_statement(self, **kwargs):
        sql = kwargs["sql"]
        self.statements.append(kwargs)
        if sql.startswith("SET LOCAL"):
            return {}
        rows = self.near if "hit_id" in sql else self.candidates
        return {"formattedRecords": json.dumps(rows)}


class FakeBedrock:
    def invoke_model(self, **kwargs):
        body = json.loads(kwargs["body"])
        assert body["input_type"] == "search_query"
        return {"body": io.BytesIO(json.dumps({"embeddings": {"float": [[0.1, 0.2]]}}).encode())}


class FakeRerank:
    """Ranks candidates in reverse order and records the texts it was given."""

    class meta:
        region_name = "us-west-2"

    def __init__(self):
        self.texts = []

    def rerank(self, **kwargs):
        self.texts = [s["inlineDocumentSource"]["textDocument"]["text"] for s in kwargs["sources"]]
        n = kwargs["rerankingConfiguration"]["bedrockRerankingConfiguration"]["numberOfResults"]
        order = range(len(self.texts) - 1, -1, -1)
        return {
            "results": [
                {"index": i, "relevanceScore": 1 - 0.01 * rank} for rank, i in enumerate(order)
            ][:n]
        }


@pytest.fixture
def run(monkeypatch):
    """Run search_passages against a fake database that returns `candidates`."""
    reranker = FakeRerank()

    def go(candidates, near=(), question="how much water?", **filters):
        data_api = FakeDataApi(candidates, near)
        monkeypatch.setattr(
            search,
            "_aws",
            lambda: {
                "data_api": data_api,
                "bedrock": FakeBedrock(),
                "rerank": reranker,
                "target": TARGET,
            },
        )
        return search.search_passages(question, **filters), data_api, reranker

    return go


def test_filters_reach_the_sql_with_none_as_null(run):
    _, data_api, _ = run([row("a")], year_from=2024, topic="Water")
    hybrid = next(s for s in data_api.statements if "WITH meaning" in s["sql"])
    params = {p["name"]: p["value"] for p in hybrid["parameters"]}
    assert params["year_from"] == {"longValue": 2024}
    assert params["topic"] == {"stringValue": "Water"}
    for unset in ("year_to", "doc_type", "country"):
        assert params[unset] == {"isNull": True}


def test_rerank_order_is_applied_and_cut_to_ten(run):
    candidates = [row(f"c{i}") for i in range(25)]
    results, _, _ = run(candidates)
    assert [r["chunk_id"] for r in results] == [f"c{i}" for i in range(24, 14, -1)]
    assert results[0]["score"] > results[-1]["score"]


def test_fewer_matches_are_not_padded_and_none_is_empty(run):
    results, _, _ = run([row("a"), row("b")])
    assert len(results) == 2
    assert run([])[0] == []


def test_rerank_reads_title_and_section_then_description_else_content(run):
    _, _, reranker = run([row("a", description="a summary"), row("b", content="b" * 500)])
    assert reranker.texts == [
        "A report › Results\n\na summary",
        "A report › Results\n\n" + "b" * 500,
    ]


def test_every_hit_gets_its_neighbours_in_one_statement(run):
    near = [{"hit_id": "a"} | row("before"), {"hit_id": "a"} | row("after")]
    results, data_api, _ = run([row("a"), row("b")], near)
    by_id = {r["chunk_id"]: r for r in results}
    assert [n["chunk_id"] for n in by_id["a"]["neighbours"]] == ["before", "after"]
    assert by_id["b"]["neighbours"] == []
    neighbour_statements = [s for s in data_api.statements if "hit_id" in s["sql"]]
    assert len(neighbour_statements) == 1
    hit_ids = {p["value"]["stringValue"] for p in neighbour_statements[0]["parameters"]}
    assert hit_ids == {"a", "b"}


def test_hits_below_min_relevance_are_dropped(run, monkeypatch):
    scores = {"answer": 0.9, "noise": 0.01}

    def rerank(self, **kwargs):
        texts = [s["inlineDocumentSource"]["textDocument"]["text"] for s in kwargs["sources"]]
        found = [scores[t.rsplit("\n\n", 1)[1]] for t in texts]
        return {"results": [{"index": i, "relevanceScore": f} for i, f in enumerate(found)]}

    monkeypatch.setattr(FakeRerank, "rerank", rerank)
    results, _, _ = run([row("a", content="answer"), row("b", content="noise")])
    assert [r["chunk_id"] for r in results] == ["a"]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "What are the trends for ocean renewable energies published in 2025?",
            (2025, 2025, "What are the trends for ocean renewable energies ?"),
        ),
        ("What did WRI publish in 2024 about heat?", (2024, 2024, "What did WRI about heat?")),
        (
            "Reports published between 2024 and 2026 on mangroves",
            (2024, 2026, "Reports on mangroves"),
        ),
        ("Anything released since 2025 on lithium?", (2025, None, "Anything on lithium?")),
        (
            "How did clean energy investment change in 2025?",
            (None, None, "How did clean energy investment change in 2025?"),
        ),
    ],
)
def test_publication_years_come_only_from_a_publication_phrase(question, expected):
    assert search.publication_years(question) == expected


def test_a_publication_phrase_becomes_the_filter_unless_one_is_given(run):
    question = "Ocean energy published in 2025?"
    _, inferred, _ = run([row("a")], question=question)
    _, given, _ = run([row("a")], question=question, year_from=2023)

    def hybrid_params(api):
        hybrid = next(s for s in api.statements if "WITH meaning" in s["sql"])
        return {p["name"]: p["value"] for p in hybrid["parameters"]}

    assert hybrid_params(inferred)["year_from"] == {"longValue": 2025}
    assert hybrid_params(inferred)["year_to"] == {"longValue": 2025}
    assert hybrid_params(inferred)["q"] == {"stringValue": "Ocean energy ?"}
    assert hybrid_params(given)["year_from"] == {"longValue": 2023}
    assert hybrid_params(given)["year_to"] == {"isNull": True}
    assert hybrid_params(given)["q"] == {"stringValue": question}
