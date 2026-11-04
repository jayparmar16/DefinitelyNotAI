"""Tables on a page: which regions belong to one, its Markdown rows, and splitting it by rows."""

import math
import re
from dataclasses import dataclass, replace

# A caption or heading that labels a table: "Table 2 | ...", "Table A-1: ...", "Table ES-1 (cont.)".
# Body text such as "Table 2 shows ..." has no separator after the number and does not match.
TABLE_LABEL = re.compile(
    r"^(?i:table)\s+((?:[A-Z]{1,2}[-–]?)?\d+(?:\.\d+)?[a-z]?)\s*(?:[|:.–—-]|\(|$)"
)
OTHER_LABEL = re.compile(r"^(?:figure|fig\.|map|box|chart|graph)\b", re.IGNORECASE)
NOTE_LINE = re.compile(r"^(?:notes?|sources?|abbreviations?)\s*:", re.IGNORECASE)
NOTE_CONTINUATION = re.compile(r"^[a-z]\.\s")  # "b. We included ..." after a Notes line
LEADER_DOTS = re.compile(r"(?:\.\s?){4,}")  # ". . . . 5" between a contents entry and its page

CAPTION_CLASSES = {"caption", "section-header", "text"}
NOTE_CLASSES = {"caption", "text", "list-item", "footnote"}
MAX_CAPTION_GAP = 150  # points between a table and its caption
BELOW_PENALTY = 60  # WRI puts captions above tables: a caption below must be this much nearer
MAX_NOTE_GAP = 60  # points between a table (or its previous note) and a note line


@dataclass(frozen=True)
class Region:
    """One layout region of a page, in reading order."""

    layout_class: str  # "table", "text", "caption", "section-header", ...
    top: float
    bottom: float
    text: str  # plain text; empty for tables and pictures


@dataclass(frozen=True)
class TableClaim:
    """The regions that make up one table, as positions in the page's region list."""

    table: int
    caption: int | None
    notes: tuple[int, ...]  # Notes, Sources and footnote lines under the table


@dataclass(frozen=True)
class Table:
    """A table with the caption and notes that belong to it."""

    number: str | None  # "Table 2", "Table A-1"; None when the caption has no number
    caption: str  # empty when no caption was found
    rows: tuple[str, ...]  # Markdown lines: header, separator, data rows
    notes: tuple[str, ...]
    part: int = 1  # 2 and up for the later pieces of a table cut by rows

    @property
    def text(self) -> str:
        """Caption, rows and notes as paragraphs separated by blank lines."""
        return "\n\n".join(
            part for part in (self.caption, "\n".join(self.rows), *self.notes) if part
        )


def claim_tables(regions: list[Region]) -> list[TableClaim]:
    """Pair each table with its caption and the note lines under it.

    A caption is a region labelled "Table N" or a caption-class region that is not labelled
    as another kind of exhibit. It need not be next to the table, only the nearest one within
    MAX_CAPTION_GAP; a caption below the table counts BELOW_PENALTY further away. Each
    caption belongs to one table, and the closest pairs are settled first. Note lines follow
    the table, or follow its caption when the caption sits below it.
    """
    tables = [i for i, region in enumerate(regions) if region.layout_class == "table"]
    candidates = sorted(
        (score, table, caption)
        for table in tables
        for caption, region in enumerate(regions)
        if _is_caption(region) and (score := _caption_score(regions[table], region)) is not None
    )
    caption_of: dict[int, int] = {}
    for _, table, caption in candidates:
        if table not in caption_of and caption not in caption_of.values():
            caption_of[table] = caption
    return [
        TableClaim(table, caption_of.get(table), _note_lines(regions, table, caption_of.get(table)))
        for table in tables
    ]


def _is_caption(region: Region) -> bool:
    if region.layout_class not in CAPTION_CLASSES or not region.text:
        return False
    if TABLE_LABEL.match(region.text):
        return True
    return (
        region.layout_class == "caption"
        and not OTHER_LABEL.match(region.text)
        and not NOTE_LINE.match(region.text)
    )


def _caption_score(table: Region, caption: Region) -> float | None:
    """Distance from table to caption, or None if too far or beside it."""
    above = table.top - caption.bottom
    below = caption.top - table.bottom
    if above >= -2:
        gap, penalty = max(above, 0), 0
    elif below >= -2:
        gap, penalty = max(below, 0), BELOW_PENALTY
    else:
        return None
    return gap + penalty if gap <= MAX_CAPTION_GAP else None


def _note_lines(regions: list[Region], table: int, caption: int | None) -> tuple[int, ...]:
    """Positions of the Notes, Sources and footnote lines that directly follow the table."""
    notes: list[int] = []
    bottom = regions[table].bottom
    for position in range(table + 1, len(regions)):
        region = regions[position]
        if position == caption:
            bottom = region.bottom
            continue
        starts_note = NOTE_LINE.match(region.text) or (
            notes and NOTE_CONTINUATION.match(region.text)
        )
        close = -2 <= region.top - bottom <= MAX_NOTE_GAP
        if region.layout_class not in NOTE_CLASSES or not starts_note or not close:
            break
        notes.append(position)
        bottom = region.bottom
    return tuple(notes)


def table_number(caption: str) -> str | None:
    """The table number of a caption such as "Table 2 | Forest cover", or None without one."""
    match = TABLE_LABEL.match(caption)
    return f"Table {match.group(1).replace('–', '-')}" if match else None


def is_data_table(rows: tuple[str, ...], has_caption: bool) -> bool:
    """Whether the region is a data table rather than a layout grid.

    A table has a header and at least one data row, and either a caption or a number in some
    cell. A grid of names with no caption and no numbers is layout, not data, and so is a
    table of contents (entries joined to page numbers by dot leaders).
    """
    has_number = any(char.isdigit() for row in rows for char in row)
    has_leaders = any(LEADER_DOTS.search(row) for row in rows)
    return len(rows) > 2 and not has_leaders and (has_caption or has_number)


def cells_text(rows: tuple[str, ...]) -> str:
    """The cell words of Markdown rows in reading order, without the Markdown or dot leaders."""
    cells = (
        LEADER_DOTS.sub(" ", cell).strip() for row in rows for cell in row.strip("|").split("|")
    )
    return " ".join(cell for cell in cells if cell and not set(cell) <= {"-"})


def split_table(table: Table, limit: int) -> list[Table]:
    """Cut a table whose text exceeds `limit` into pieces by rows, each within `limit`.

    Every piece repeats the caption and the header row; the notes go on the last piece. A row
    is never cut, so a single row longer than the room left stays whole and over the limit.
    Pieces hold about the same number of characters rather than a full piece and a stub.
    """
    if len(table.text) <= limit:
        return [table]
    header, body = table.rows[:2], table.rows[2:]
    budget = max(limit - len(replace(table, rows=header).text), 1)  # room for rows per piece
    costs = [len(row) + 1 for row in body]
    pieces = math.ceil(sum(costs) / budget)
    target = sum(costs) / pieces
    groups: list[list[str]] = [[]]
    size = 0
    for row, cost in zip(body, costs, strict=True):
        too_big = size + cost > budget or size + cost - target > target - size
        if groups[-1] and too_big:
            groups.append([])
            size = 0
        groups[-1].append(row)
        size += cost
    last = len(groups) - 1
    return [
        replace(table, rows=(*header, *rows), notes=table.notes if n == last else (), part=n + 1)
        for n, rows in enumerate(groups)
    ]
