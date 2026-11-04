"""Fakes for the answering side: C1 passages, a scripted search and a scripted grounding check."""

from types import SimpleNamespace


def passage(n: int = 1, **fields) -> SimpleNamespace:
    """A C1 search result with every attribute set; `fields` override the defaults."""
    doc_id = fields.pop("doc_id", f"doc-{n}")
    defaults = {
        "chunk_id": f"{doc_id}#p{n}-1",
        "seq": n,
        "doc_id": doc_id,
        "doc_title": f"Report {n}",
        "link": f"https://www.wri.org/research/report-{n}",
        "pdf_key": f"corpus/{doc_id}.pdf",
        "pdf_page": n,
        "pdf_page_end": n,
        "printed_page": str(n),
        "printed_page_end": str(n),
        "printed_page_fallback": False,
        "section": "Findings",
        "kind": "source_text",
        "quotable": True,
        "text": f"Passage {n} text.",
        "year": 2025,
        "topic": "Energy",
        "doc_type": "research report",
        "wri_type": "Report",
        "authors": (),
        "figure_image": None,
        "score": 0.8,
    }
    return SimpleNamespace(**(defaults | fields))


class FakeGrounding:
    """A grounding check that returns a set score per sentence (default 1.0) and records calls."""

    def __init__(self, scores: dict[str, float] | None = None):
        self.scores = scores or {}
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, question: str, sentence: str, source: str) -> float:
        self.calls.append((question, sentence, source))
        return self.scores.get(sentence, 1.0)
