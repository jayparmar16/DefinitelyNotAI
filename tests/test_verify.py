"""Claim verification: each rule drops the right sentence, with a fake grounding check."""

from decimal import Decimal

import pytest

from askwri.answer.verify import (
    NO_SOURCE,
    NOT_GROUNDED,
    NUMBER_NOT_IN_SOURCE,
    QUOTE_NOT_FOUND,
    QUOTE_NOT_QUOTABLE,
    grounding_score_from,
    numbers,
    passage_numbers,
    verify,
)
from tests.answer_fakes import FakeGrounding, passage

PASSAGES = [
    passage(1, text="Solar capacity reached 2000 GW in 2025, up 3.5% on the year before."),
    passage(2, text="Battery storage is the fastest-growing part of the grid in most markets."),
    passage(3, text="Grid operators “must plan for storage at every substation”.", quotable=False),
]


def draft(paragraphs, key_points=None):
    report = None if key_points is None else {"key_points": key_points}
    return {"passages": PASSAGES, "paragraphs": paragraphs, "report": report}


def sentence(text, *cites):
    return {"text": text, "cites": list(cites)}


def reason_for(text, *cites, grounding=None):
    result = verify("What about solar?", draft([[sentence(text, *cites)]]), grounding=grounding)
    return result["dropped"][0]["reason"] if result["dropped"] else None


def test_sentence_with_no_cites_or_a_cite_out_of_range_has_no_source():
    assert reason_for("Solar is growing.") == NO_SOURCE
    assert reason_for("Solar is growing.", 0) == NO_SOURCE
    assert reason_for("Solar is growing.", 1, 4) == NO_SOURCE
    assert reason_for("Solar is growing.", 1) is None


def test_quote_must_appear_word_for_word_in_a_cited_passage():
    kept = "Storage is “the fastest-growing part of the grid” today."
    assert reason_for(kept, 2) is None
    assert reason_for(kept, 1) == QUOTE_NOT_FOUND
    assert reason_for("It is “the fastest growing piece of the grid” now.", 2) == QUOTE_NOT_FOUND


def test_straight_quotes_are_checked_too():
    assert reason_for('Storage is "the fastest-growing part of the grid".', 2) is None
    assert reason_for('Storage is "the slowest-growing part of the grid".', 2) == QUOTE_NOT_FOUND


def test_quote_from_a_passage_that_may_not_be_quoted_is_dropped():
    text = "Operators “must plan for storage at every substation”."
    assert reason_for(text, 3) == QUOTE_NOT_QUOTABLE
    # The words are the passage's, so the citation itself is fine without quotation marks.
    assert reason_for("Operators must plan for storage at every substation.", 3) is None


def test_quotes_under_four_words_are_not_checked():
    assert reason_for("Storage is “very fast growing” in places.", 2) is None


def test_every_number_must_appear_in_a_cited_passage():
    assert reason_for("Solar reached 2000 GW in 2025.", 1) is None
    assert reason_for("Solar reached 2100 GW in 2025.", 1) == NUMBER_NOT_IN_SOURCE
    assert reason_for("Solar reached 2000 GW in 2025.", 2) == NUMBER_NOT_IN_SOURCE
    assert reason_for("Solar reached 2000 GW in 2025.", 2, 1) is None


def test_thousands_separators_match_the_number_as_written_in_the_passage():
    assert reason_for("Solar reached 2,000 GW in 2025.", 1) is None


def test_a_decimal_never_matches_the_same_digits_without_the_point():
    passages = [passage(1, text="Growth was 35% in 2025.")]
    result = verify(
        "q", {"passages": passages, "paragraphs": [[sentence("Up 3.5%.", 1)]]}, grounding=None
    )
    assert result["dropped"] == [{"text": "Up 3.5%.", "reason": NUMBER_NOT_IN_SOURCE}]


def test_footnote_marker_glued_to_a_number_does_not_drop_a_correct_sentence():
    # Ingest keeps superscript footnote 12 after "2030." as "2030.12".
    passages = [passage(1, text="Coal must be phased out globally by 2030.12 Gas follows.")]
    d = {"passages": passages, "paragraphs": [[sentence("Coal must go by 2030.", 1)]]}
    assert verify("q", d, grounding=None)["dropped"] == []


def test_footnote_reading_applies_only_at_a_sentence_end():
    assert passage_numbers("by 2030.12") == {Decimal("2030.12"), Decimal(2030)}
    assert passage_numbers("by 2030.12 Gas") == {Decimal("2030.12"), Decimal(2030)}
    assert passage_numbers("up 3.5 percent") == {Decimal("3.5")}
    assert passage_numbers("from 4,000,000.5 people") == {Decimal("4000000.5")}


def test_percentages_and_numbers_written_as_words_are_handled():
    assert reason_for("Capacity grew 3.5 percent.", 1) is None
    assert reason_for("Capacity grew by about three percent.", 1) is None


def test_number_values():
    assert numbers("2,000 and 2.000 and 2000") == {Decimal(2000)}
    assert numbers("3.5% or 3,5") == {Decimal("3.5")}
    assert numbers("0.125 and 1,234.5") == {Decimal("0.125"), Decimal("1234.5")}
    assert numbers("from 2024-2026, 10,000,000 people") == {
        Decimal(2024),
        Decimal(2026),
        Decimal(10_000_000),
    }


def test_grounding_score_below_the_threshold_drops_the_sentence():
    low, edge = "Solar is growing fast.", "Storage is growing fast."
    grounding = FakeGrounding({low: 0.69, edge: 0.7})
    result = verify("q", draft([[sentence(low, 1), sentence(edge, 2)]]), grounding=grounding)
    assert result["dropped"] == [{"text": low, "reason": NOT_GROUNDED}]
    assert result["grounding_check"] == "guardrails"


def test_grounding_threshold_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("ASKWRI_GROUNDING_THRESHOLD", "0.5")
    assert (
        reason_for("Solar is growing.", 1, grounding=FakeGrounding({"Solar is growing.": 0.6}))
        is None
    )


def test_grounding_sees_only_the_cited_passages_and_only_sentences_that_passed():
    grounding = FakeGrounding()
    paragraphs = [[sentence("Solar is growing.", 1, 2, 1), sentence("Solar grew 9%.", 1)]]
    verify("What about solar?", draft(paragraphs), grounding=grounding)
    assert grounding.calls == [
        ("What about solar?", "Solar is growing.", f"{PASSAGES[0].text}\n\n{PASSAGES[1].text}")
    ]


def test_without_a_grounding_check_rule_four_is_skipped():
    result = verify("q", draft([[sentence("Solar is growing.", 1)]]), grounding=None)
    assert result["grounding_check"] == "skipped"
    assert result["claims_verified"] == 1


def test_result_keeps_survivors_removes_empty_paragraphs_and_counts_claims():
    paragraphs = [
        [sentence("Solar is growing.", 1), sentence("Unsourced.")],
        [sentence("Also unsourced.")],
    ]
    key_points = [sentence("Storage leads.", 2), sentence("Solar hit 9 GW.", 1)]
    result = verify("q", draft(paragraphs, key_points), grounding=FakeGrounding())
    assert result["paragraphs"] == [[sentence("Solar is growing.", 1)]]
    assert result["key_points"] == [sentence("Storage leads.", 2)]
    assert (result["claims_total"], result["claims_verified"]) == (5, 2)
    assert [d["reason"] for d in result["dropped"]] == [NO_SOURCE, NO_SOURCE, NUMBER_NOT_IN_SOURCE]


def test_grounding_score_is_read_from_the_apply_guardrail_response():
    response = {
        "assessments": [
            {
                "contextualGroundingPolicy": {
                    "filters": [
                        {"type": "GROUNDING", "threshold": 0.7, "score": 0.42, "action": "NONE"},
                    ]
                },
                "invocationMetrics": {"guardrailProcessingLatency": 310},
            }
        ]
    }
    assert grounding_score_from(response) == 0.42
    with pytest.raises(RuntimeError, match="no GROUNDING score"):
        grounding_score_from({"assessments": [{"invocationMetrics": {}}]})
