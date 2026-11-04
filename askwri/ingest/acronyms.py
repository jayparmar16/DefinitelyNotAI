"""Acronyms a document defines, such as "Offshore wind (OSW)", found by rule in its text."""

import re

# "(OSW)", "(NDCs)": a capital, then up to 9 letters or digits; two capitals at least.
SHORT_FORM = re.compile(r"\(([A-Z][A-Za-z0-9]{1,9})\)")
MIN_LONG_WORDS = 2  # a one-word "long form" is usually a name in brackets, not a definition


def find_acronyms(text: str) -> tuple[str, ...]:
    """Every acronym the text defines, as "SHORT = long form", once each, in order of first use.

    A definition is "long form (SHORT)" where the short form's letters appear in order in the
    words just before the bracket and its first letter starts a word (the Schwartz-Hearst
    rule), so "Offshore wind (OSW)" counts and "see the annex (PDF)" does not.
    """
    found: dict[str, str] = {}
    for match in SHORT_FORM.finditer(text):
        short = match.group(1)
        if short in found or sum(char.isupper() for char in short) < 2:
            continue
        words = text[: match.start()].split()
        window = " ".join(words[-min(len(short) + 5, 2 * len(short)) :])
        if long := _long_form(short, window):
            found[short] = long
    return tuple(f"{short} = {long}" for short, long in found.items())


def _long_form(short: str, window: str) -> str | None:
    """The shortest end of `window` that `short` abbreviates, or None."""
    s, w = len(short) - 1, len(window) - 1
    while s >= 0:
        char = short[s].lower()
        # The short form's first letter must start a word; later letters may sit anywhere.
        while w >= 0 and (
            window[w].lower() != char or (s == 0 and w > 0 and window[w - 1].isalnum())
        ):
            w -= 1
        if w < 0:
            return None
        w -= 1
        s -= 1
    long = window[window.rfind(" ", 0, w + 1) + 1 :].strip(" ,;:\"'(")
    return long if len(long.split()) >= MIN_LONG_WORDS else None
