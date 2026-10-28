"""Shared success boundary for persisting common typed-series artifacts."""
from collections.abc import Sequence

from macro_data_platform.config import Settings
from macro_data_platform.contracts import ErrorCode, StageResult, StageStatus, TimeSeries
from macro_data_platform.storage.typed_series import save_typed_series_artifact


def persist_typed_series_result(
    settings: Settings,
    *,
    payload: dict,
    series: Sequence[TimeSeries],
    engine_id: str,
    refs: Sequence[str],
    warnings: Sequence[str] = (),
) -> StageResult[dict]:
    """Persist a passing typed result or stop without exposing unpersisted values."""
    quality = payload.get("quality")
    try:
        artifact = save_typed_series_artifact(
            settings, series=series, engine_id=engine_id, quality=quality,
        )
    except (OSError, TypeError, ValueError):
        return StageResult(
            StageStatus.FAILED_TERMINAL, None, tuple(refs),
            ("Typed-series artifact persistence failed; original source files remain available.",),
            ErrorCode.INTERNAL_BUG,
        )
    result_payload = {**payload, "typed_series_artifact": artifact}
    artifact_refs = (artifact["typed_series_path"], artifact["typed_series_manifest_path"])
    combined_refs = tuple(dict.fromkeys((*refs, *artifact_refs)))
    return StageResult(StageStatus.SUCCEEDED, result_payload, combined_refs, tuple(warnings))
