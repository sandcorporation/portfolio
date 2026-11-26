"""A cold home request asks the three external services side by side (issue 54)."""

import time
from dataclasses import dataclass

import pytest
from django.core.cache import cache

from adapters import foresight as foresight_adapter
from adapters import metrics as metrics_adapter
from adapters.fake_foresight import FakeForesight
from adapters.fake_metrics import FakeMetrics
from services.home import home_page

pytestmark = pytest.mark.django_db

DELAY = 0.3


@dataclass
class SlowMetrics(FakeMetrics):
    def stats(self):  # type: ignore[no-untyped-def]
        time.sleep(DELAY)
        return super().stats()


@dataclass
class SlowForesight(FakeForesight):
    def recent(self, limit: int):  # type: ignore[no-untyped-def]
        time.sleep(DELAY)
        return super().recent(limit)

    def stats(self):  # type: ignore[no-untyped-def]
        time.sleep(DELAY)
        return super().stats()


def slow() -> tuple[SlowMetrics, SlowForesight]:
    m, f = SlowMetrics(), SlowForesight()
    metrics_adapter.set_gateway(m)
    foresight_adapter.set_gateway(f)
    cache.clear()
    return m, f


def test_cold_request_waits_for_one_delay_not_three() -> None:
    m, f = slow()
    start = time.monotonic()
    data = home_page().data
    elapsed = time.monotonic() - start
    assert elapsed < DELAY * 2  # sequential would be 3 × DELAY
    assert (m.calls, len(f.calls), f.stats_calls) == (1, 1, 1)
    assert data["visits"] is not None and data["news"]


def test_warm_request_calls_nothing() -> None:
    m, f = slow()
    home_page()
    start = time.monotonic()
    home_page()
    assert time.monotonic() - start < DELAY
    assert (m.calls, len(f.calls), f.stats_calls) == (1, 1, 1)


def test_failures_fall_back_as_before() -> None:
    m, f = slow()
    m.failing = True
    f.failing = True
    data = home_page().data
    assert data["visits"] is None
    assert data["news"] == []
