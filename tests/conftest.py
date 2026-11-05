"""Shared test setup: tests never send real metrics to CloudWatch."""

import pytest

from askwri.agent import usage


@pytest.fixture(autouse=True)
def no_live_metrics(monkeypatch):
    monkeypatch.setattr(usage, "publish", lambda points: None)
