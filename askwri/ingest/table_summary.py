"""Short model-written summaries of table chunks, used for search and never quoted."""

import dataclasses

from askwri.ingest.chunks import Chunk
from askwri.models import call_claude

PROMPT = """\
Below is a table from a World Resources Institute publication ("{title}", section: {section}).
Write a one- or two-sentence summary for a search index: say what the table shows (the measure,
its units, the places or groups and the period it covers) and any clear overall pattern. Use
only what the table says; do not add outside knowledge. Reply with the summary only.

{table}"""


def summarize_tables(client, chunks: list[Chunk]) -> list[Chunk]:
    """Return the chunks with `summary` set on every table chunk, one `labeler` call each.

    A model refusal or error raises `ModelError` naming the chunk, which fails the document.
    """
    return [
        dataclasses.replace(chunk, summary=_summary(client, chunk))
        if chunk.kind == "table"
        else chunk
        for chunk in chunks
    ]


def _summary(client, chunk: Chunk) -> str:
    prompt = PROMPT.format(title=chunk.doc_title, section=chunk.section or "none", table=chunk.text)
    return call_claude(client, "labeler", document=chunk.chunk_id, prompt=prompt).strip()
