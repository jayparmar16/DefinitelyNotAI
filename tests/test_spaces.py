from datetime import UTC, datetime

from askwri.ingest.model_labels import TOPICS
from askwri.spaces import spaces


def test_every_topic_is_a_space_in_order_with_zero_for_empty_ones():
    made = spaces({"Ocean": 52, "none": 20}, 579, datetime(2026, 11, 5, tzinfo=UTC))
    assert [s["name"] for s in made["spaces"]] == list(TOPICS)
    assert {s["name"]: s["documents"] for s in made["spaces"]}["Ocean"] == 52
    assert {s["name"]: s["documents"] for s in made["spaces"]}["Food"] == 0
    assert made["total"] == 579 and "none" not in [s["name"] for s in made["spaces"]]
