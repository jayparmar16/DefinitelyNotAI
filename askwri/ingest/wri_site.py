"""Find a document's page on wri.org by its DOI or its title, and check that the link resolves."""

import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit, urlunsplit

from askwri.ingest.text import comparable, words

USER_AGENT = "AskWRI-ingest/0.1"
SITEMAP_URL = "https://www.wri.org/sitemap.xml"
SITE_HOST = "www.wri.org"
PAGE_PREFIXES = ("https://www.wri.org/research/", "https://www.wri.org/data/")
# Shorter titles must match whole: a short phrase would otherwise sit inside many other titles.
MIN_PARTIAL_MATCH_CHARS = 15
# Words the site drops from a page's URL slug when it builds one from the title.
SLUG_STOP_WORDS = {
    *("a", "an", "as", "at", "before", "but", "by", "for", "from", "is", "in", "into"),
    *("like", "of", "off", "on", "onto", "per", "since", "than", "the", "this", "that"),
    *("to", "up", "via", "with"),
}
MAX_SITEMAP_CANDIDATES = 3
# A research page's taxonomy line: "This Working Paper is part of <a>Ocean Climate
# Diplomacy</a> within <a>Energy</a> and <a>Clean Energy</a>. Reach out to <a>...</a>"
TAXONOMY_LINE = re.compile(r'<div class="narrative-taxonomy">\s*<p>(.*?)</p>', re.DOTALL)
LINK_TEXT = re.compile(r"<a\b[^>]*>(.*?)</a>", re.DOTALL)


@dataclass(frozen=True)
class Response:
    """What a fetch returns: the final URL after redirects, the HTTP status and the body."""

    url: str
    status: int
    body: str


Fetch = Callable[[str], Response]


def fetch_url(url: str) -> Response:
    """GET a URL, following redirects. An HTTP error status is returned; network errors raise."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as reply:
            return Response(reply.url, reply.status, reply.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        return Response(url, error.code, "")


@dataclass(frozen=True)
class Page:
    """A wri.org page that resolved and whose title matches the PDF's."""

    url: str  # without the tracking query the site adds on redirect
    title: str
    meta: dict[str, list[str]]  # meta tag name or property -> every content value, in order
    match: str  # "doi" or "title": how it was found
    initiatives: tuple[str, ...] = ()  # named in the page's "part of ... within ..." line
    programs: tuple[str, ...] = ()


class WriSite:
    """Looks up documents on wri.org. The sitemap is fetched once, the first time it's needed."""

    def __init__(self, fetch: Fetch = fetch_url):
        self.fetch = fetch

    def find_page(self, title: str, doi: str | None) -> Page | None:
        """The wri.org page for a document, or None.

        Tries the DOI first, then a title match against the sitemap's research and data pages.
        A page is accepted only if it answers 200 on www.wri.org and its own title matches
        the PDF's title, so a DOI that resolves to a translation or a different edition is
        rejected. This fetch is the link check: a Page's URL has been seen to resolve.
        """
        if doi and (page := self._page(f"https://doi.org/{doi}", title, "doi")):
            return page
        for url in self._sitemap_candidates(title):
            if page := self._page(url, title, "title"):
                return page
        return None

    def _page(self, url: str, pdf_title: str, match: str) -> Page | None:
        response = self.fetch(url)
        parts = urlsplit(response.url)
        if response.status != 200 or parts.netloc != SITE_HOST:
            return None
        meta = parse_meta(response.body)
        title = _page_title(meta)
        if not titles_match(pdf_title, title):
            return None
        initiatives, programs = part_of(response.body)
        url = urlunsplit(parts._replace(query="", fragment=""))
        return Page(url, title, meta, match, initiatives, programs)

    def _sitemap_candidates(self, title: str) -> list[str]:
        """Sitemap URLs whose slug reads like the title, closest first, at most a few."""
        wanted = _slug_key(title)
        if len(wanted) < MIN_PARTIAL_MATCH_CHARS:
            return []
        close = [
            (abs(len(key) - len(wanted)), url)
            for url, key in self._slug_keys
            if len(key) >= MIN_PARTIAL_MATCH_CHARS and (wanted in key or key in wanted)
        ]
        return [url for _, url in sorted(close)[:MAX_SITEMAP_CANDIDATES]]

    @cached_property
    def _slug_keys(self) -> list[tuple[str, str]]:
        urls = []
        index = self._get(SITEMAP_URL)
        for child in re.findall(r"<loc>([^<]+)</loc>", index):
            urls += re.findall(r"<loc>([^<]+)</loc>", self._get(child))
        return [
            (url, _slug_key(url.rsplit("/", 1)[1])) for url in urls if url.startswith(PAGE_PREFIXES)
        ]

    def _get(self, url: str) -> str:
        response = self.fetch(url)
        if response.status != 200:
            raise RuntimeError(f"{url} answered HTTP {response.status}")
        return response.body


def titles_match(pdf_title: str, page_title: str) -> bool:
    """Whether two titles name the same document, ignoring case, spacing and punctuation.

    A PDF often drops the subtitle or a "Technical Note:" prefix, so one title may sit inside
    the other, as long as the shorter is long enough not to match by accident.
    """
    short, long = sorted((comparable(pdf_title), comparable(page_title)), key=len)
    if not short:
        return False
    return short == long or (len(short) >= MIN_PARTIAL_MATCH_CHARS and short in long)


def part_of(page_html: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The initiatives and programs a page's "This ... is part of X within Y" line links to.

    Link texts before "within" are initiatives, those after it are programs; the "Reach out
    to ..." sentence is left out. A page without the line gives two empty tuples.
    """
    line = TAXONOMY_LINE.search(page_html)
    if line is None:
        return (), ()
    head, _, tail = line.group(1).split("Reach out")[0].partition(" within ")
    return _link_texts(head), _link_texts(tail)


def _link_texts(fragment: str) -> tuple[str, ...]:
    texts = (unescape(re.sub(r"<[^>]+>", "", text)).strip() for text in LINK_TEXT.findall(fragment))
    return tuple(text for text in texts if text)


def _slug_key(text: str) -> str:
    """Words of a title or URL slug without the words a slug drops, run together."""
    return "".join(word for word in words(text) if word not in SLUG_STOP_WORDS)


def _page_title(meta: dict[str, list[str]]) -> str:
    for key in ("citation_title", "wri_full_title", "og:title"):
        if meta.get(key):
            return meta[key][0]
    return ""


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        key = attributes.get("name") or attributes.get("property")
        if tag == "meta" and key and attributes.get("content"):
            self.meta.setdefault(key, []).append(attributes["content"].strip())


def parse_meta(html: str) -> dict[str, list[str]]:
    """Every <meta> tag's content by its name or property, in page order (values unescaped)."""
    parser = _MetaParser()
    parser.feed(html)
    return parser.meta
