"""Vision-model descriptions of picture chunks, used for search and never quoted."""

import dataclasses

from askwri.ingest.chunks import Chunk
from askwri.ingest.figures import PictureReport
from askwri.models import Image, call_claude_json

JUDGE_PROMPT = """\
This picture comes from a World Resources Institute publication ("{title}"). Is it informative:
a chart, graph, map, diagram, infographic or other picture that carries data or an explanation
a reader could ask about? Pictures that are only decoration (a photograph, a banner, a cover
image, a logo, a portrait, a background) are not informative."""
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"informative": {"type": "boolean"}},
    "required": ["informative"],
    "additionalProperties": False,
}

DESCRIBE_PROMPT = """\
This picture comes from a World Resources Institute publication ("{title}", section: {section}).
Caption: {caption}
Text printed inside the picture (axis labels, legend, labels): {inside}

Describe the picture for a search index, using only what the picture and its text show.
For a chart or graph, give the chart type, the axes and units, the main takeaway and the key
values; mark any value you read off the chart as approximate (about, roughly). For a map,
diagram or infographic, give the region or subject, what is shown and the legend. Say "chart" in
"kind" for a chart or graph and "image" for anything else."""
DESCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["chart", "image"]},
        "description": {"type": "string"},
    },
    "required": ["kind", "description"],
    "additionalProperties": False,
}


def describe_figures(
    client, chunks: list[Chunk], report: PictureReport
) -> tuple[list[Chunk], PictureReport]:
    """Describe every picture chunk with the `vision` role; return the chunks and the updated report.

    A picture with a caption is informative. One without gets a `labeler` call first, and is
    dropped if judged decorative; the chunks are then renumbered so `seq` stays contiguous.
    Each informative picture gets one `vision` call that sets its `description` and `kind`
    ("chart" or "image"). A model refusal or error raises `ModelError` naming the chunk,
    which fails the document.
    """
    kept, decorative, described = [], 0, 0
    for chunk in chunks:
        if chunk.figure is None:
            kept.append(chunk)
        elif not chunk.text and not _is_informative(client, chunk):
            decorative += 1
        else:
            kept.append(_described(client, chunk))
            described += 1
    kept = [dataclasses.replace(chunk, seq=seq) for seq, chunk in enumerate(kept, start=1)]
    report = dataclasses.replace(report, decorative=decorative, described=described)
    return kept, report


def _is_informative(client, chunk: Chunk) -> bool:
    answer = call_claude_json(
        client,
        "labeler",
        document=chunk.chunk_id,
        prompt=JUDGE_PROMPT.format(title=chunk.doc_title),
        images=[Image(chunk.figure.png, "image/png")],
        schema=JUDGE_SCHEMA,
    )
    return answer["informative"]


def _described(client, chunk: Chunk) -> Chunk:
    prompt = DESCRIBE_PROMPT.format(
        title=chunk.doc_title,
        section=chunk.section or "none",
        caption=chunk.text or "none",
        inside=chunk.figure.text or "none",
    )
    answer = call_claude_json(
        client,
        "vision",
        document=chunk.chunk_id,
        prompt=prompt,
        images=[Image(chunk.figure.png, "image/png")],
        schema=DESCRIBE_SCHEMA,
    )
    return dataclasses.replace(
        chunk, kind=answer["kind"], description=answer["description"].strip()
    )
