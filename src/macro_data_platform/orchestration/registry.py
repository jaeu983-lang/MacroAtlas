"""Versioned engine registration and composition for persisted task plans."""
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from macro_data_platform.contracts import Engine
from macro_data_platform.orchestration.models import StageSpec, TaskPlan
from macro_data_platform.orchestration.runner import Orchestrator
from macro_data_platform.storage.history import HistoryStore

EngineKey = tuple[str, str]
EngineFactory = Callable[[], Engine[Any, Any]]
ReuseValidator = Callable[[StageSpec, dict], bool]


@dataclass(frozen=True)
class EngineRegistration:
    factory: EngineFactory
    reuse_validator: ReuseValidator | None = None


class EngineRegistry:
    """Resolve a persisted (engine, version) plan into the shared Orchestrator."""

    def __init__(self, store: HistoryStore, *, clock: Callable[[], datetime] =
                 lambda: datetime.now(UTC)):
        self.store = store
        self.clock = clock
        self._registrations: dict[EngineKey, EngineRegistration] = {}

    def register(self, engine: str, version: str, factory: EngineFactory, *,
                 reuse_validator: ReuseValidator | None = None) -> None:
        if not isinstance(engine, str) or not engine or not isinstance(version, str) or not version:
            raise ValueError("engine and version must be non-empty strings")
        if not callable(factory):
            raise TypeError("engine factory must be callable")
        if reuse_validator is not None and not callable(reuse_validator):
            raise TypeError("reuse validator must be callable")
        key = (engine, version)
        if key in self._registrations:
            raise ValueError(f"engine version is already registered: {engine}/{version}")
        self._registrations[key] = EngineRegistration(factory, reuse_validator)

    @property
    def keys(self) -> frozenset[EngineKey]:
        return frozenset(self._registrations)

    def orchestrator_for(self, *, plan: TaskPlan | None = None,
                         engine_keys: Iterable[EngineKey] | None = None) -> Orchestrator:
        if (plan is None) == (engine_keys is None):
            raise ValueError("provide exactly one of plan or engine_keys")
        required = ({(stage.engine, stage.engine_version) for stage in plan.stages}
                    if plan is not None else set(engine_keys or ()))
        if not required:
            raise ValueError("at least one engine version is required")
        missing = required - self._registrations.keys()
        if missing:
            names = ", ".join(f"{name}/{version}" for name, version in sorted(missing))
            raise ValueError(f"task plan requires unregistered engine versions: {names}")
        registrations = {key: self._registrations[key] for key in required}
        engines = {key: registration.factory() for key, registration in registrations.items()}
        if any(not callable(getattr(engine, "run", None)) for engine in engines.values()):
            raise TypeError("registered engine factory must return an engine with run()")
        validators = {key: registration.reuse_validator for key, registration in registrations.items()
                      if registration.reuse_validator is not None}

        def validate_reuse(spec: StageSpec, stage: dict) -> bool:
            validator = validators.get((spec.engine, spec.engine_version))
            return bool(validator(spec, stage)) if validator is not None else False

        return Orchestrator(
            self.store, engines, clock=self.clock,
            reuse_validator=validate_reuse if validators else None,
        )

    def orchestrator_for_task(self, task_id: str) -> Orchestrator:
        doc = self.store.get(task_id)
        saved_plan = doc.get("plan")
        if not isinstance(saved_plan, list) or not saved_plan:
            raise ValueError("task has no persisted engine plan")
        keys = set()
        for row in saved_plan:
            if not isinstance(row, Mapping):
                raise TypeError("task plan contains an invalid engine registration")
            engine, version = row.get("engine"), row.get("engine_version", "1")
            if not isinstance(engine, str) or not isinstance(version, str):
                raise TypeError("task plan contains an invalid engine registration")
            keys.add((engine, version))
        return self.orchestrator_for(engine_keys=keys)

    def resume(self, task_id: str, *, approved: bool = False) -> dict:
        return self.orchestrator_for_task(task_id).resume(task_id, approved=approved)
