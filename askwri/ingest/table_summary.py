"""Short model-written summaries of table chunks, used for search and never quoted."""

import dataclasses
from concurrent.futures import ThreadPoolExecutor

from askwri.ingest.chunks import Chunk
from askwri.models import call_claude

PROMPT = """\
Below is a table from a World Resources Institute publication ("{title}", section: {section}).
Write a one- or two-sentence summary for a search index: say what the table shows (the measure,
its units, the places or groups and the period it covers) and any clear overall pattern. Use
only what the table says; do not add outside knowledge. Reply with the summary only.

{table}"""
# Calls in flight per document. Loading runs 8 documents at once, so up to 32 in all; one
# report has 113 tables, which one at a time set the length of the whole load.
THREADS = 4


def summarize_tables(client, chunks: list[Chunk]) -> list[Chunk]:
    """Return the chunks with `description` set on every table chunk, one `labeler` call each.

    Tables with a role (contents, abbreviations...) are skipped: search never returns them.
    The calls run THREADS at a time. A model refusal or error raises `ModelError` naming the
    chunk, which fails the document.
    """
    tables = [chunk for chunk in chunks if chunk.kind == "table" and chunk.role is None]
    with ThreadPoolExecutor(THREADS) as pool:
        summaries = pool.map(lambda chunk: _summary(client, chunk), tables)
        by_id = dict(zip((chunk.chunk_id for chunk in tables), summaries, strict=True))
    return [
        dataclasses.replace(chunk, description=by_id[chunk.chunk_id])
        if chunk.chunk_id in by_id
        else chunk
        for chunk in chunks
    ]


def _summary(client, chunk: Chunk) -> str:
    prompt = PROMPT.format(title=chunk.doc_title, section=chunk.section or "none", table=chunk.text)
    return call_claude(client, "labeler", document=chunk.chunk_id, prompt=prompt).strip()
