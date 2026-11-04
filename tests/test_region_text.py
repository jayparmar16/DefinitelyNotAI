"""Choosing a region's text: the layout model's Markdown, or the PDF's own text layer."""

import pymupdf
import pytest

from askwri.ingest.pdf import region_text

SENTENCE = "Catch up on the first and second installments of the article on tariffs."


@pytest.fixture
def page():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 120), SENTENCE, fontsize=11)
    yield page
    doc.close()


def test_keeps_layout_text_that_matches_the_page(page):
    assert region_text(page, page.get_text(), (50, 50, 550, 120), SENTENCE) == SENTENCE


def test_replaces_scrambled_ligatures_with_the_text_layer(page):
    scrambled = "Catch up on the frst i and second installments of the artcle i on tarifs."

    assert region_text(page, page.get_text(), (50, 50, 550, 120), scrambled) == SENTENCE


def test_never_swaps_in_text_layer_that_lost_words_at_the_region_edge(page):
    scrambled = "Catch up on the frst i and second installments of the artcle i on tarifs."

    # The clipped region holds only part of the sentence: keep the layout text and let the
    # audit report the scrambled words, rather than silently dropping the rest.
    assert region_text(page, page.get_text(), (50, 50, 200, 70), scrambled) == scrambled


def test_keeps_reordered_layout_text_when_the_text_layer_is_no_better(page):
    reordered = "on tariffs. Catch up on the first and second installments of the article"

    # A region that cuts off most of the text can't replace the layout text.
    assert region_text(page, page.get_text(), (50, 50, 60, 60), reordered) == reordered


def test_plain_text_drops_pymupdf_picture_markers():
    from askwri.ingest.pdf import plain_text

    marked = "<!-- Start of picture text -->Solar pumps<!-- End of picture text --> save water."
    assert plain_text(marked) == "Solar pumps save water."
