"""Read a PDF with PyMuPDF's layout model into ordered text, heading and table blocks."""

import html
import re
from dataclasses import dataclass, replace
from pathlib import Path

import pymupdf

from askwri.ingest.figures import (
    MAX_CONTEXT_CHARS,
    Figure,
    PictureReport,
    claim_captions,
    figure_number,
    is_scan,
    is_small,
)
from askwri.ingest.pages import PrintedPage, printed_pages
from askwri.ingest.tables import (
    Region,
    Table,
    TableClaim,
    cells_text,
    claim_tables,
    is_data_table,
    table_number,
)
from askwri.ingest.text import comparable, missing_words, words

# Layout classes that carry body text. Pictures become figure blocks (see `figure_blocks`).
TEXT_CLASSES = {"text", "list-item", "footnote", "formula", "caption"}
HEADING_CLASSES = {"title", "section-header"}
RUNNING_CLASSES = {"page-header", "page-footer"}  # kept out of chunks, read for page numbers
FIGURE_DPI = 110  # enough to read chart labels, small enough to send to the vision model
INSIDE_SHARE = 0.8  # a text region this much inside a picture belongs to the picture


@dataclass(frozen=True)
class Block:
    """One layout region of a page, in reading order, as plain text."""

    page: int  # 1-based position in the PDF file
    heading_level: int  # 0 for body text, 1 for "#", 2 for "##", ...
    text: str
    table: Table | None = None  # set for a table region; `text` is then the table's full text
    figure: Figure | None = None  # set for a picture; `text` is then its caption, maybe empty


@dataclass(frozen=True)
class ParsedPdf:
    """What the chunker needs from a PDF: its title, its blocks in reading order, its page numbers."""

    title: str
    blocks: list[Block]
    printed_pages: list[PrintedPage]  # one per PDF page, in order
    pictures: PictureReport  # picture counts so far: found, small, scanned


def parse_pdf(path: Path) -> ParsedPdf:
    """Parse a PDF into text, heading and table blocks.

    The layout model decides the regions, their classes and their reading order. Page headers
    and footers are kept out of the blocks and read for printed page numbers instead. The layout
    model sometimes calls a running header "text" on one page while calling it a header on the
    others, so body text equal to a header or footer seen anywhere in the document is dropped
    too (digits ignored, so a lone page number counts). A table region becomes one table block
    together with its caption and note lines (see `claim_tables`), so those never become text
    or headings. A layout grid that is not a data table stays a text block. Pictures become
    figure blocks, with their caption and the text inside them (see `figure_blocks`). OCR is
    off: a page without a text layer yields no blocks, so every passage stays checkable
    against the PDF's own text.
    """
    with pymupdf.open(path) as doc:
        pages = doc.to_markdown(
            page_chunks=True, header=False, footer=False, use_ocr=False, show_progress=False
        )
        title = (doc.metadata or {}).get("title", "").strip()
        blocks, region_texts, pictures = [], [], PictureReport()
        for chunk in pages:
            page = doc[chunk["metadata"]["page_number"] - 1]
            page_text = page.get_text()
            region_texts.append(
                [
                    layer_text(page, box["bbox"])
                    for box in chunk["page_boxes"]
                    if box["class"] in RUNNING_CLASSES
                ]
            )
            boxes = sorted(chunk["page_boxes"], key=lambda box: box["index"])
            markdowns = [chunk["text"][box["pos"][0] : box["pos"][1]].strip() for box in boxes]
            regions = _regions(boxes, markdowns)
            claims = claim_tables(regions)
            tables = {claim.table: claim for claim in claims}
            claimed = {i for c in claims for i in (c.caption, *c.notes) if i is not None}
            figures, in_figures, found = figure_blocks(
                page, page_text, boxes, markdowns, regions, claimed
            )
            pictures += found
            claimed |= in_figures
            for position, (box, markdown) in enumerate(zip(boxes, markdowns, strict=True)):
                if position in claimed:
                    continue
                if position in figures:
                    blocks.append(figures[position])
                    continue
                if position in tables:
                    block = table_block(page, page_text, boxes, markdowns, tables[position])
                    blocks.extend([block] if block else [])
                    continue
                if box["class"] not in TEXT_CLASSES | HEADING_CLASSES:
                    continue
                text = region_text(page, page_text, box["bbox"], plain_text(markdown))
                if not text:
                    continue
                level = 0
                if box["class"] in HEADING_CLASSES:
                    level = len(markdown) - len(markdown.lstrip("#")) or 1
                blocks.append(Block(page=page.number + 1, heading_level=level, text=text))
        printed = printed_pages([page.get_label() for page in doc], region_texts)
    running = {running_key(text) for texts in region_texts for text in texts}
    blocks = [b for b in blocks if b.heading_level or running_key(b.text) not in running]
    return ParsedPdf(title=title, blocks=blocks, printed_pages=printed, pictures=pictures)


def _regions(boxes: list[dict], markdowns: list[str]) -> list[Region]:
    """The page's layout boxes as `Region`s; only classes that can caption or annotate a table need text."""
    needs_text = TEXT_CLASSES | HEADING_CLASSES
    return [
        Region(
            layout_class=box["class"],
            top=box["bbox"][1],
            bottom=box["bbox"][3],
            text=plain_text(markdown) if box["class"] in needs_text else "",
        )
        for box, markdown in zip(boxes, markdowns, strict=True)
    ]


def table_block(
    page: pymupdf.Page, page_text: str, boxes: list[dict], markdowns: list[str], claim: TableClaim
) -> Block | None:
    """The block for one table region with its claimed caption and notes, or None if it is empty.

    A data table becomes a table block. A region that is not a data table (a layout grid with
    no caption and no numbers, or a contents list) becomes a plain text block of its cell
    words, and its caption and notes, if any, stay with it as text. So does a table whose cell
    words are not all on the page (the layout model dropped letters), because the audit would
    block the document; the PDF's text layer then supplies the words.
    """

    def claimed_text(position: int) -> str:
        return region_text(
            page, page_text, boxes[position]["bbox"], plain_text(markdowns[position])
        )

    rows = table_rows(markdowns[claim.table])
    caption = claimed_text(claim.caption) if claim.caption is not None else ""
    notes = tuple(claimed_text(position) for position in claim.notes)
    if is_data_table(rows, bool(caption)) and not has_garbled_word(cells_text(rows), page_text):
        table = Table(number=table_number(caption), caption=caption, rows=rows, notes=notes)
        return Block(page=page.number + 1, heading_level=0, text=table.text, table=table)
    bbox = boxes[claim.table]["bbox"]
    grid = region_text(page, page_text, bbox, cells_text(rows))
    if has_garbled_word(
        grid, page_text
    ):  # region_text keeps garbled layout words it cannot replace
        grid = layer_text(page, bbox)
    text = "\n\n".join(part for part in (caption, grid, *notes) if part)
    return Block(page=page.number + 1, heading_level=0, text=text) if text else None


def figure_blocks(
    page: pymupdf.Page,
    page_text: str,
    boxes: list[dict],
    markdowns: list[str],
    regions: list[Region],
    taken: set[int],
) -> tuple[dict[int, Block], set[int], PictureReport]:
    """The figure blocks of a page, by picture position, the regions they absorb, and the counts.

    Pictures under 2% of the page (logos, icons) and scanned pages are skipped. Each other
    picture is rendered to a PNG from its bounding box and paired with its caption (see
    `claim_captions`; `taken` are the regions tables have claimed). The caption and the
    text regions inside the picture (axis labels, legends) are absorbed: they never become
    text blocks. The text inside goes to the vision model as context. If the picture is later
    judged decorative, that text goes with it.
    """
    page_area = page.rect.width * page.rect.height
    pictures = [i for i, box in enumerate(boxes) if box["class"] == "picture"]
    report = PictureReport(found=len(pictures))
    big = []
    for i in pictures:
        area = _area(boxes[i]["bbox"])
        if is_small(area, page_area):
            report = replace(report, small=report.small + 1)
        elif is_scan(area, page_area, page_text):
            report = replace(report, scanned=report.scanned + 1)
        else:
            big.append(i)
    captions = claim_captions(regions, big, taken)
    figures: dict[int, Block] = {}
    absorbed = set(captions.values())
    for i in big:
        bbox = boxes[i]["bbox"]
        caption = ""
        if i in captions:
            position = captions[i]
            caption = region_text(
                page, page_text, boxes[position]["bbox"], plain_text(markdowns[position])
            )
        pixmap = page.get_pixmap(clip=pymupdf.Rect(bbox), dpi=FIGURE_DPI)
        inside = layer_text(page, bbox)[:MAX_CONTEXT_CHARS]
        figure = Figure(png=pixmap.tobytes("png"), text=inside, number=figure_number(caption))
        figures[i] = Block(page=page.number + 1, heading_level=0, text=caption, figure=figure)
        absorbed |= {
            j
            for j, box in enumerate(boxes)
            if box["class"] in TEXT_CLASSES | HEADING_CLASSES and _inside(box["bbox"], bbox)
        }
    return figures, absorbed, report


def _area(bbox: tuple[float, float, float, float]) -> float:
    return max(bbox[2] - bbox[0], 0) * max(bbox[3] - bbox[1], 0)


def _inside(
    inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]
) -> bool:
    """Whether at least INSIDE_SHARE of the inner box lies within the outer box."""
    overlap = _area((max(inner[0], outer[0]), max(inner[1], outer[1]),
                     min(inner[2], outer[2]), min(inner[3], outer[3])))  # fmt: skip
    return _area(inner) > 0 and overlap >= INSIDE_SHARE * _area(inner)


def has_garbled_word(text: str, page_text: str) -> bool:
    """Whether some word of the text is not on the page, such as "suort" for "support".

    Stricter than the audit, which lets a word match as two words glued together. For a table
    it is worth being strict: a garbled word in an indexed row is wrong even if the audit passes.
    """
    page = comparable(page_text)
    return any(word not in page for word in words(text))


def table_rows(markdown: str) -> tuple[str, ...]:
    """Clean a Markdown table's lines: cell text as plain text, rows with no words dropped."""
    rows = []
    for line in re.sub(r"<!--.*?-->", " ", markdown, flags=re.DOTALL).splitlines():
        cells = [plain_text(cell) for cell in line.strip().strip("|").split("|")]
        if any(cells):
            rows.append("|" + "|".join(cells) + "|")
    return tuple(rows)


def region_text(
    page: pymupdf.Page, page_text: str, bbox: tuple[float, float, float, float], layout_text: str
) -> str:
    """Pick the region's text: the layout model's, unless the PDF's own text layer is better.

    The layout Markdown sometimes misplaces ligatures ("frst", "tarifs") or interleaves a pull
    quote into a paragraph. The text layer read from the same region has the words verbatim.
    It wins only if it is complete (at least 95% of the layout text's length, so a region
    that clips words at its edge can't drop them) and either it is a verbatim run of the page
    or the layout text has words that are not on the page at all. Otherwise the layout text
    stays, and the audit decides.
    """
    page_run = comparable(page_text)
    if comparable(layout_text) in page_run:
        return layout_text
    from_layer = layer_text(page, bbox)
    complete = len(comparable(from_layer)) >= 0.95 * len(comparable(layout_text))
    if complete and (comparable(from_layer) in page_run or missing_words(layout_text, page_text)):
        return from_layer
    return layout_text


def running_key(text: str) -> str:
    """The text without digits, so a footer reading "Report | 5" matches "Report | 7" on another page."""
    return comparable(re.sub(r"\d+", "", text))


def layer_text(page: pymupdf.Page, bbox: tuple[float, float, float, float]) -> str:
    """The PDF text layer's text inside a layout box, as plain text."""
    region = pymupdf.Rect(bbox) + (-2, -2, 2, 2)  # layout boxes can clip edge characters
    return plain_text(page.get_text("text", clip=region, flags=pymupdf.TEXT_DEHYPHENATE))


def plain_text(markdown: str) -> str:
    """Strip the Markdown and HTML that PyMuPDF adds, so the text reads as it does in the PDF."""
    text = re.sub(r"<br\s*/?>", " ", markdown)
    text = re.sub(r"<!--.*?-->", " ", text)  # PyMuPDF's "Start of picture text" markers
    text = re.sub(r"_{3,}|(?:\. ?){4,}|…{2,}", " ", text)  # blank form lines and dot leaders
    text = re.sub(r"</?[a-z]+>", "", text)
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"(?<!\w)_|_(?!\w)", "", text)
    return " ".join(html.unescape(text).split())
