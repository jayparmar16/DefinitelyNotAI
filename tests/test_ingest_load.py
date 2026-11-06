"""Loading into Aurora: chunk-to-row mapping and the per-document replace, with a fake Data API."""

import dataclasses
import json

import pytest

from askwri.ingest.chunks import Chunk
from askwri.ingest.load import ROW_BATCH, chunk_row, replace_document

TARGET = {"resourceArn": "cluster", "secretArn": "secret", "database": "askwri"}


class FakeDataApi:
    """Records Data API calls; optionally fails the batch insert."""

    def __init__(self, fail_batch: bool = False):
        self.calls = []
        self.fail_batch = fail_batch

    def begin_transaction(self, **kwargs):
        self.calls.append(("begin", None))
        return {"transactionId": "tx1"}

    def execute_statement(self, **kwargs):
        self.calls.append(("execute", kwargs["sql"].split()[0], kwargs["transactionId"]))

    def batch_execute_statement(self, **kwargs):
        if self.fail_batch:
            raise RuntimeError("Data API refused the batch")
        self.calls.append(("batch", len(kwargs["parameterSets"]), kwargs["transactionId"]))

    def commit_transaction(self, **kwargs):
        self.calls.append(("commit", kwargs["transactionId"]))

    def rollback_transaction(self, **kwargs):
        self.calls.append(("rollback", kwargs["transactionId"]))


def chunk(**overrides) -> Chunk:
    base = Chunk(
        chunk_id="doc#p3-1", seq=1, doc_id="doc", doc_title="Doc", pdf_page=3, pdf_page_end=4,
        printed_page="iii", printed_page_end="iv", printed_page_fallback=False,
        section="Intro", kind="source_text", text="Forests store carbon.",
    )  # fmt: skip
    return dataclasses.replace(base, **overrides)


def test_chunk_row_maps_every_chunks_column():
    row = chunk_row(chunk(kind="table", number="Table 2", description="Shows X."), [0.5, -1.0])

    assert row["content"] == "Forests store carbon."
    assert (row["pdf_page"], row["pdf_page_end"], row["printed_page"]) == (3, 4, "iii")
    assert (row["kind"], row["number"], row["description"]) == ("table", "Table 2", "Shows X.")
    assert json.loads(row["embedding"]) == [0.5, -1.0]


def test_an_empty_description_is_stored_as_null():
    assert chunk_row(chunk(), [0.0])["description"] is None


def test_replace_deletes_then_inserts_in_one_transaction():
    api = FakeDataApi()
    rows = [chunk_row(chunk(chunk_id=f"doc#p3-{n}", seq=n), [0.0]) for n in range(ROW_BATCH + 1)]

    replace_document(api, TARGET, {"doc_id": "doc"}, rows)

    assert api.calls == [
        ("begin", None),
        ("execute", "DELETE", "tx1"),
        ("execute", "INSERT", "tx1"),
        ("batch", ROW_BATCH, "tx1"),
        ("batch", 1, "tx1"),
        ("commit", "tx1"),
    ]


def test_a_failed_insert_rolls_back_and_raises():
    api = FakeDataApi(fail_batch=True)

    with pytest.raises(RuntimeError):
        replace_document(api, TARGET, {"doc_id": "doc"}, [chunk_row(chunk(), [0.0])])

    assert api.calls[-1] == ("rollback", "tx1")
    assert ("commit", "tx1") not in api.calls
