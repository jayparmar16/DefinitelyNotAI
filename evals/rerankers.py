"""Is the reranker losing good passages? Judge every candidate, then compare orderings of them.

Usage: `uv run python -m evals.rerankers`. For each question it takes the 25 candidates search
passes to the reranker, has the judge rate all of them, and counts how many passages that help
each ordering puts in its top RESULTS: Amazon Rerank (today), Cohere Rerank 3.5, and the fused
order with no reranker. It also counts the helping passages MIN_RELEVANCE drops from Amazon's.
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor

from askwri import search
from askwri.models import cached_client, claude_client
from evals.run import CACHE, JUDGE_THREADS, QUESTIONS, judge

RERANKERS = {"amazon": "amazon.rerank-v1:0", "cohere": "cohere.rerank-v3-5:0"}


def candidates(question: str) -> list[dict]:
    """The candidates search_passages() would rerank for this question, in fused order."""
    year_from, year_to, keywords = search.publication_years(question)
    aws = search._aws()
    params = {
        "q": keywords,
        "vec": json.dumps(search._embed_query(aws["bedrock"], question)),
        "year_from": year_from,
        "year_to": year_to,
        "topic": None,
        "doc_type": None,
        "country": None,
    }
    return search._query_hybrid(aws["data_api"], aws["target"], params)


def rerank_scores(model: str, question: str, rows: list[dict]) -> list[float]:
    """Each candidate's relevance from `model`, in the candidates' order."""
    client = search._aws()["rerank"]
    arn = f"arn:aws:bedrock:{client.meta.region_name}::foundation-model/{model}"
    response = client.rerank(
        queries=[{"type": "TEXT", "textQuery": {"text": question}}],
        sources=[
            {"type": "INLINE", "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": search._rerank_text(row)}}}
            for row in rows
        ],
        rerankingConfiguration={
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "modelConfiguration": {"modelArn": arn},
                "numberOfResults": len(rows),
            },
        },
    )  # fmt: skip
    scores = [0.0] * len(rows)
    for hit in response["results"]:
        scores[hit["index"]] = hit["relevanceScore"]
    return scores


def helping_in_top(order: list[int], helps: list[bool], k: int = search.RESULTS) -> int:
    """How many of the first k candidates in `order` help."""
    return sum(helps[i] for i in order[:k])


def main() -> int:
    """Print, per answerable question and in total, helping passages each ordering keeps."""
    questions = [q for q in json.loads(QUESTIONS.read_text()) if not q.get("unanswerable")]
    client = cached_client(claude_client(), CACHE / "judge")
    totals = {"candidates help": 0, "fused": 0, "amazon": 0, "cohere": 0, "amazon kept": 0}
    aws = search._aws()
    years = search._rows(aws["data_api"], aws["target"], "SELECT doc_id, year FROM documents", {})
    year_of = {row["doc_id"]: row["year"] for row in years}
    print(f"{'question':28} cands helps | top {search.RESULTS}: fused amazon cohere | amazon kept")
    for question in questions:
        rows = candidates(question["question"])
        if not rows:
            print(f"{question['id'][:28]:28} no candidates")
            continue
        with ThreadPoolExecutor(JUDGE_THREADS) as pool:
            scores = list(
                pool.map(
                    lambda r, q=question["question"]: judge(client, q, r, year_of[r["doc_id"]]),
                    rows,
                )
            )
        helps = [score == 2 for score in scores]
        orders = {"fused": list(range(len(rows)))}
        amazon = rerank_scores(RERANKERS["amazon"], question["question"], rows)
        for name, model in RERANKERS.items():
            got = amazon if name == "amazon" else rerank_scores(model, question["question"], rows)
            orders[name] = sorted(range(len(rows)), key=lambda i, got=got: -got[i])
        kept = [i for i in orders["amazon"][: search.RESULTS] if amazon[i] >= search.MIN_RELEVANCE]
        line = {name: helping_in_top(order, helps) for name, order in orders.items()}
        line["amazon kept"] = sum(helps[i] for i in kept)
        totals["candidates help"] += sum(helps)
        for name in ("fused", "amazon", "cohere", "amazon kept"):
            totals[name] += line[name]
        print(
            f"{question['id'][:28]:28} {len(rows):5} {sum(helps):5} |        {line['fused']:5} "
            f"{line['amazon']:6} {line['cohere']:6} | {line['amazon kept']:11}"
        )
    print(
        f"\ntotal: {totals['candidates help']} candidates help; in the top {search.RESULTS}: "
        f"fused {totals['fused']}, amazon {totals['amazon']}, cohere {totals['cohere']}; "
        f"amazon after MIN_RELEVANCE {totals['amazon kept']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
