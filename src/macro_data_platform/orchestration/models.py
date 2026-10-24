"""Immutable plans and inputs for the synchronous iteration 02 runner."""
import json
from dataclasses import asdict, dataclass
from typing import Any

from macro_data_platform.contracts import required


def json_snapshot(value: Any) -> Any:
    """Detach mutable inputs and reject non-JSON/NaN payloads before persistence."""
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True))


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    engine: str
    input_data: Any = None
    engine_version: str = "1"
    max_attempts: int = 3
    reuse_ttl_seconds: int = 3600

    def __post_init__(self) -> None:
        for name in ("stage_id", "engine", "engine_version"):
            required(getattr(self, name), name)
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be an integer between 1 and 10")
        if type(self.reuse_ttl_seconds) is not int or self.reuse_ttl_seconds < 0:
            raise ValueError("reuse_ttl_seconds must be a nonnegative integer")
        json_snapshot(self.input_data)


@dataclass(frozen=True)
class TaskPlan:
    stages: tuple[StageSpec, ...]

    def __post_init__(self) -> None:
        if not self.stages or not all(isinstance(stage, StageSpec) for stage in self.stages):
            raise ValueError("plan requires stage specifications")
        ids = [stage.stage_id for stage in self.stages]
        if len(ids) != len(set(ids)):
            raise ValueError("stage identifiers must be unique")

    def snapshot(self) -> list[dict]:
        return json_snapshot([asdict(stage) for stage in self.stages])


@dataclass(frozen=True)
class StageInput:
    task_id: str
    request: str
    stage_id: str
    input_data: Any
    upstream: Any
    input_refs: tuple[str, ...]
