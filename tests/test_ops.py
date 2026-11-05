from datetime import UTC, datetime

from askwri.api import ops

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def answer_events(cost=0.01, removed=0, translated=False, rounds=1):
    steps = [
        {"type": "step", "id": f"search-0-{r}", "status": "done"} for r in range(1, rounds + 1)
    ]
    answer = {
        "paragraphs": ["Cities cool down [1]."],
        "sources": [
            {"marker": 1, "title": "Heat", "page": 6, "url": None, "passage": "Roofs cool."}
        ],
        "claimsTotal": 2,
        "claimsVerified": 2 - removed,
        "removedClaims": ["x"] * removed,
        "machineTranslated": translated,
        "language": "es" if translated else "en",
        "audience": "researcher",
    }
    usage = {
        "tokensIn": 1000,
        "tokensOut": 200,
        "byStep": {"draft": {"in": 800, "out": 150}, "verify": {"in": 200, "out": 50}},
        "estimatedCostUsd": cost,
    }
    return steps + [{"type": "answer", "answer": answer, "usage": usage}]


def record(events, mode="quick", source="user", seconds=10.0, ts=NOW, rid="2026-11-05.120000-a"):
    return ops.query_record(
        {"question": "How do cities cool?", "mode": mode, "source": source},
        events,
        seconds,
        ts,
        rid,
    )


def test_a_record_keeps_kind_usage_claims_and_sources():
    r = record(answer_events(rounds=2, removed=1))
    assert (r["kind"], r["status"], r["rounds"], r["claims_verified"]) == (
        "Quick answer with a retry",
        "answered",
        2,
        1,
    )
    assert r["sources"][0]["page"] == 6 and r["usage"]["estimatedCostUsd"] == 0.01
    assert record(answer_events(translated=True))["kind"] == "Translated answer"
    assert record(answer_events(), mode="deep")["kind"] == "Deep research"
    assert (
        record([{"type": "decline", "decline": {"message": "no"}, "usage": None}])["status"]
        == "declined"
    )
    assert record([])["status"] == "error"


def test_live_numbers_come_only_from_records_and_say_none_without_data():
    records = [
        record(answer_events(cost=0.01)),
        record(answer_events(cost=0.03, removed=2), mode="deep", seconds=40.0),
    ]
    view = ops.live(records, records, NOW)
    assert view["cost_per_answer_usd"] == 0.02
    assert view["projected_per_1000_usd"] == 20.0
    assert view["most_expensive"][0]["cost_usd"] == 0.03
    assert view["claims_removed_per_answer"] == 1.0
    assert view["median_seconds"] == {"quick": 10.0, "deep": 40.0}
    assert {k["kind"]: k["share"] for k in view["by_kind"]} == {
        "Deep research": 0.75,
        "Quick answer": 0.25,
    }
    assert view["tokens_by_step"][0] == {"step": "draft", "in": 1600, "out": 300}
    empty = ops.live([], [], NOW)
    assert (
        empty["cost_per_answer_usd"] is None
        and empty["declined_share"] is None
        and empty["spend_30d_usd"] is None
    )


def test_items_are_partitioned_by_day_and_found_again_from_the_id():
    rid = ops.new_id(NOW, "abc")
    item = ops.item(record(answer_events(), rid=rid))
    assert item["day"] == "2026-11-05" and rid == f"{item['day']}.{item['sk']}"
    assert ops.days(ops.window_start("7d", NOW), NOW)[0] == "2026-10-29"
