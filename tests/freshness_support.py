"""Explicit tolerance for old synthetic fixtures used by non-freshness tests."""
from macro_data_platform.ingestion.freshness import FreshnessPolicy

HISTORICAL_FIXTURE_POLICY = FreshnessPolicy(
    policy_id="test_historical_fixture_v1",
    frequency_max_age_days={
        "daily": 36500, "weekly": 36500, "monthly": 36500,
        "quarterly": 36500, "semiannual": 36500, "annual": 36500,
    },
)
