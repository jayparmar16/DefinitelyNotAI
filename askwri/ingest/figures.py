"""Pictures on a page: which are worth describing, their captions, and their figure numbers."""

import re
from dataclasses import dataclass

from askwri.ingest.tables import (
    CAPTION_CLASSES,
    NOTE_LINE,
    TABLE_LABEL,
    Region,
    caption_score,
)

# A caption or heading that labels a figure: "Figure 2 | ...", "Map 3: ...", "Box A-1 (cont.)".
FIGURE_LABEL = re.compile(
    r"^(figure|fig\.|map|box|chart|graph)\s+((?:[A-Z]{1,2}[-–]?)?\d+(?:\.\d+)?[a-z]?)"
    r"\s*(?:[|:.–—-]|\(|$)",
    re.IGNORECASE,
)

MIN_PAGE_SHARE = 0.02  # pictures smaller than this share of the page are logos and icons
SCAN_PAGE_SHARE = 0.6  # a picture this large on a page with no text layer is a scan
CAPTION_OVERLAP = 12  # picture boxes often start a line into their caption
MAX_CONTEXT_CHARS = 2000  # picture text sent to the vision model as context


@dataclass(frozen=True)
class Figure:
    """A picture to describe: its rendered PNG and the text printed inside it."""

    png: bytes
    text: str  # axis labels, legends, diagram labels: context for the vision model, never quoted
    number: str | None  # "Figure 3", "Map 2"; None when the caption has no number


@dataclass(frozen=True)
class PictureReport:
    """How many pictures a document had and what happened to them, to track vision cost."""

    found: int = 0
    small: int = 0  # skipped by size
    scanned: int = 0  # a scanned page, not a figure
    decorative: int = 0  # judged decorative by the labeler
    described: int = 0  # described by the vision model

    @property
    def summary(self) -> str:
        """One line for the run report."""
        return (
            f"pictures {self.found}: {self.small} small, {self.scanned} scanned, "
            f"{self.decorative} decorative, {self.described} described"
        )

    def __add__(self, other: "PictureReport") -> "PictureReport":
        return PictureReport(
            self.found + other.found,
            self.small + other.small,
            self.scanned + other.scanned,
            self.decorative + other.decorative,
            self.described + other.described,
        )


def figure_number(caption: str) -> str | None:
    """The number of a caption such as "figure 3 | Forest cover", as "Figure 3", or None."""
    match = FIGURE_LABEL.match(caption)
    if not match:
        return None
    label = match.group(1)
    label = "Fig." if label.lower() == "fig." else label.capitalize()
    return f"{label} {match.group(2).replace('–', '-')}"


def is_small(picture_area: float, page_area: float) -> bool:
    """Whether the picture is too small to be a figure."""
    return picture_area < MIN_PAGE_SHARE * page_area


def is_scan(picture_area: float, page_area: float, page_text: str) -> bool:
    """Whether the picture is a scanned page: it covers most of a page that has no text layer."""
    return picture_area >= SCAN_PAGE_SHARE * page_area and not page_text.strip()


def claim_captions(regions: list[Region], pictures: list[int], taken: set[int]) -> dict[int, int]:
    """Pair each picture with its caption: the nearest figure caption on the page.

    The caption is a region labelled "Figure N" (or Map, Box, ...) or a caption-class region
    that is not labelled as a table or a note, and not already `taken` by a table. It need
    not be next to the picture. A caption below the picture counts further away, as in
    `claim_tables`. Each caption belongs to one picture, and the closest pairs are settled
    first. Returns picture position -> caption position.
    """
    candidates = sorted(
        (score, picture, caption)
        for picture in pictures
        for caption, region in enumerate(regions)
        if caption not in taken
        and _is_caption(region)
        and (score := caption_score(regions[picture], region, CAPTION_OVERLAP)) is not None
    )
    caption_of: dict[int, int] = {}
    for _, picture, caption in candidates:
        if picture not in caption_of and caption not in caption_of.values():
            caption_of[picture] = caption
    return caption_of


def _is_caption(region: Region) -> bool:
    if region.layout_class not in CAPTION_CLASSES or not region.text:
        return False
    if FIGURE_LABEL.match(region.text):
        return True
    return (
        region.layout_class == "caption"
        and not TABLE_LABEL.match(region.text)
        and not NOTE_LINE.match(region.text)
    )
