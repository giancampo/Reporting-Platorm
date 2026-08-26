import pytest

from reporting_etl.transform.canonical import (
    to_canonical_dimension,
    to_canonical_metric,
    to_ga4_dimension,
    to_ga4_metric,
)


def test_ga4_to_canonical_roundtrip():
    assert to_canonical_dimension("sessionSourceMedium") == "source_medium"
    assert to_ga4_dimension("source_medium") == "sessionSourceMedium"
    assert to_canonical_metric("screenPageViews") == "pageviews"
    assert to_ga4_metric("pageviews") == "screenPageViews"


def test_unmapped_native_name_raises():
    with pytest.raises(ValueError):
        to_canonical_dimension("someBrandNewGa4Dimension")


def test_unmapped_canonical_name_raises():
    with pytest.raises(ValueError):
        to_ga4_metric("some_metric_with_no_ga4_mapping")
