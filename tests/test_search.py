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

    def go(candidates, near=(), **filters):
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
        return search.search_passages("how much water?", **filters), data_api, reranker

    return go


def test_filters_reach_the_sql_with_none_as_null(run):
    _, data_api, _ = run([row("a")], year_from=2024, topic="Water")
    hybrid = next(s for s in data_api.statements if "WITH meaning" in s["sql"])
    params = {p["name"]: p["value"] for p in hybrid["parameters"]}
    assert params["year_from"] == {"longValue": 2024}
    assert params["topic"] == {"stringValue": "Water"}
    for unset in ("year_to", "doc_type", "country"):
        assert params[unset] == {"isNull": True}


def test_rerank_order_is_applied_and_cut_to_six(run):
    candidates = [row(f"c{i}") for i in range(25)]
    results, _, _ = run(candidates)
    assert [r["chunk_id"] for r in results] == [f"c{i}" for i in range(24, 18, -1)]
    assert results[0]["score"] > results[-1]["score"]


def test_fewer_matches_are_not_padded_and_none_is_empty(run):
    results, _, _ = run([row("a"), row("b")])
    assert len(results) == 2
    assert run([])[0] == []


def test_rerank_uses_description_when_there_is_one(run):
    _, _, reranker = run([row("a", description="a summary"), row("b", content="b" * 500)])
    assert reranker.texts == ["a summary", "b" * 500]


def test_neighbours_only_for_short_hits_in_one_statement(run):
    short = row("short", content="tiny")
    near = [{"hit_id": "short"} | row("before"), {"hit_id": "short"} | row("after")]
    results, data_api, _ = run([short, row("long")], near)
    by_id = {r["chunk_id"]: r for r in results}
    assert [n["chunk_id"] for n in by_id["short"]["neighbours"]] == ["before", "after"]
    assert "neighbours" not in by_id["long"]
    neighbour_statements = [s for s in data_api.statements if "hit_id" in s["sql"]]
    assert len(neighbour_statements) == 1
    assert [p["value"] for p in neighbour_statements[0]["parameters"]] == [{"stringValue": "short"}]


def test_hits_below_min_relevance_are_dropped(run, monkeypatch):
    scores = {"answer": 0.9, "noise": 0.01}

    def rerank(self, **kwargs):
        texts = [s["inlineDocumentSource"]["textDocument"]["text"] for s in kwargs["sources"]]
        return {"results": [{"index": i, "relevanceScore": scores[t]} for i, t in enumerate(texts)]}

    monkeypatch.setattr(FakeRerank, "rerank", rerank)
    results, _, _ = run([row("a", content="answer"), row("b", content="noise")])
    assert [r["chunk_id"] for r in results] == ["a"]
