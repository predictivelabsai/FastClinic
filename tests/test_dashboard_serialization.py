"""Regression coverage for database-native values in dashboard charts."""

from datetime import date, datetime, timezone
from decimal import Decimal
import json

import pytest

from web.dashboards import _plot_spec


def test_plot_spec_serializes_postgresql_numeric_and_temporal_values():
    rendered = _plot_spec(
        [{
            "x": [date(2026, 8, 14), datetime(2026, 8, 14, 12, 30, tzinfo=timezone.utc)],
            "y": [Decimal("1234.56"), Decimal("0")],
        }],
        {"height": 280},
    )

    payload = json.loads(rendered)
    assert payload["data"][0]["x"] == ["2026-08-14", "2026-08-14T12:30:00+00:00"]
    assert payload["data"][0]["y"] == [1234.56, 0.0]


def test_plot_spec_still_rejects_unknown_python_objects():
    with pytest.raises(TypeError, match="object is not JSON serializable"):
        _plot_spec([{"y": [object()]}], {})
