"""Bounded backoff for explicit, durable transient-failure resumption."""
from __future__ import annotations

import math

RETRY_BASE_SECONDS = 1.0
RETRY_EXPONENTIAL_CAP_SECONDS = 60.0
RETRY_ABSOLUTE_CAP_SECONDS = 86_400.0


def retry_delay(attempt_no: int, source_delay: float | None = None) -> float:
    """Compute a bounded delay; retries remain explicit and are never slept inline."""
    if type(attempt_no) is not int or not 1 <= attempt_no <= 10:
        raise ValueError("retry attempt must be within the workflow attempt limit")
    if source_delay is not None and (
        type(source_delay) not in {int, float}
        or not math.isfinite(source_delay)
        or not 0 <= source_delay <= RETRY_ABSOLUTE_CAP_SECONDS
    ):
        raise ValueError("source retry delay is invalid or exceeds the supported cap")
    exponential = min(RETRY_EXPONENTIAL_CAP_SECONDS,
                      RETRY_BASE_SECONDS * (2 ** (attempt_no - 1)))
    return max(exponential, float(source_delay or 0))
