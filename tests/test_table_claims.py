"""Which regions of a page belong to a table: captions, notes and layout grids, on plain regions."""

from askwri.ingest.tables import Region, TableClaim, claim_tables, is_data_table, table_number


def region(layout_class: str, top: float, bottom: float, text: str = "") -> Region:
    return Region(layout_class, top, bottom, text)


def test_a_caption_two_regions_away_is_paired_with_the_table():
    regions = [
        region("section-header", 100, 110, "Table 4 | Funds"),
        region("text", 120, 160, "A paragraph that explains the funds in some detail."),
        region("table", 170, 300),
    ]

    assert claim_tables(regions) == [TableClaim(table=2, caption=0, notes=())]


def test_a_caption_far_from_the_table_is_not_paired():
    regions = [region("caption", 10, 20, "Table 4 | Funds"), region("table", 400, 500)]

    assert claim_tables(regions) == [TableClaim(table=1, caption=None, notes=())]


def test_a_caption_above_wins_over_a_nearer_one_below_that_belongs_to_the_next_table():
    regions = [
        region("caption", 100, 110, "Table 1 | Forest cover"),
        region("table", 150, 250),
        region("caption", 270, 280, "Table 2 | Forest loss"),
        region("table", 320, 420),
    ]

    claims = claim_tables(regions)

    assert [(c.table, c.caption) for c in claims] == [(1, 0), (3, 2)]


def test_notes_and_sources_after_the_table_belong_to_it_even_with_the_caption_below_them():
    regions = [
        region("table", 100, 200),
        region("text", 210, 230, "Notes: Rows are countries."),
        region("text", 232, 240, "b. Excludes islands."),
        region("text", 242, 250, "Sources: WRI analysis."),
        region("caption", 260, 270, "Table 2 | Forest cover"),
        region("text", 400, 460, "Notes: too far below to belong to the table."),
    ]

    assert claim_tables(regions) == [TableClaim(table=0, caption=4, notes=(1, 2, 3))]


def test_body_text_that_mentions_a_table_is_not_a_caption():
    regions = [region("text", 100, 120, "Table 2 shows forest cover."), region("table", 130, 230)]

    assert claim_tables(regions)[0].caption is None


def test_a_caption_for_a_figure_is_not_a_table_caption():
    regions = [region("caption", 100, 110, "Figure 3 | Forest cover"), region("table", 130, 230)]

    assert claim_tables(regions)[0].caption is None


def test_table_numbers():
    assert table_number("Table 2 | Forest cover") == "Table 2"
    assert table_number("TABLE 2: Forest cover") == "Table 2"
    assert table_number("Table A-1  | Assessment") == "Table A-1"
    assert table_number("Table ES-1 (cont.)") == "Table ES-1"
    assert table_number("Table 3.1. Costs") == "Table 3.1"
    assert table_number("Forest cover by country") is None
    assert table_number("Table 2 shows forest cover") is None


def test_a_grid_of_names_is_not_a_data_table_but_a_caption_or_a_number_makes_one():
    names = ("|Alice|Bob|", "|---|---|", "|Carol|Dan|")
    numbers = ("|Country|Forest|", "|---|---|", "|Peru|3.5|")
    contents = ("|Contents|Page|", "|---|---|", "|Introduction . . . . . . . . 5|6|")

    assert not is_data_table(names, has_caption=False)
    assert is_data_table(names, has_caption=True)
    assert is_data_table(numbers, has_caption=False)
    assert not is_data_table(contents, has_caption=False)
    assert not is_data_table(("|Country|Forest|", "|---|---|"), has_caption=True)
