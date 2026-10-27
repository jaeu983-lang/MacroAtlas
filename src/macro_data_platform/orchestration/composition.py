"""Composition root for the supported statistical source adapters."""
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from macro_data_platform.config import Settings
from macro_data_platform.orchestration.registry import EngineKey, EngineRegistry, ReuseValidator
from macro_data_platform.storage.history import HistoryStore


def build_engine_registry(
    settings: Settings,
    store: HistoryStore,
    *,
    worldbank_transport=None,
    boj_transport=None,
    bls_transport=None,
    census_transport=None,
    file_transport=None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    freshness_policy=None,
    gate_a: bool = False,
    audit_store=None,
    additional_engines: Mapping[EngineKey, Any] | None = None,
    additional_reuse_validators: Mapping[EngineKey, ReuseValidator] | None = None,
) -> EngineRegistry:
    """Register source adapters once; provider protocols remain in their adapters."""
    if settings.database_path != store.settings.database_path:
        raise ValueError("engine registry and history must use the same configured storage")

    # Local imports keep storage contracts independent from connector implementations and
    # avoid a provider module importing itself while exposing its compatibility factory.
    from macro_data_platform.ingestion.bls import BLSEngine
    from macro_data_platform.ingestion.boj import (
        BOJMetadataEngine,
        BOJObservationEngine,
        metadata_reusable,
    )
    from macro_data_platform.ingestion.census import CensusEngine
    from macro_data_platform.ingestion.freshness import (
        DEFAULT_FRESHNESS_POLICY,
    )
    from macro_data_platform.ingestion.gate_c_watch import GateCFileEngine
    from macro_data_platform.ingestion.worldbank import WorldBankGDPEngine
    from macro_data_platform.ingestion.worldbank_quality import (
        WorldBankAuditedCollection,
        WorldBankValidation,
    )
    from macro_data_platform.ingestion.worldbank_quality import (
        reusable as worldbank_reusable,
    )
    from macro_data_platform.storage.audit import AuditStore

    policy = freshness_policy or DEFAULT_FRESHNESS_POLICY
    registry = EngineRegistry(store, clock=clock)
    audit = (audit_store or AuditStore(store, clock=clock)) if gate_a else None

    registry.register("worldbank_gdp", "2", lambda: WorldBankGDPEngine(
        settings, worldbank_transport, clock=clock, freshness_policy=policy))
    registry.register("boj_metadata", "1", lambda: BOJMetadataEngine(settings, boj_transport),
                      reuse_validator=lambda spec, stage: metadata_reusable(spec, stage, settings))
    registry.register("boj_observations", "2", lambda: BOJObservationEngine(
        settings, boj_transport, clock=clock, freshness_policy=policy))
    registry.register("bls", "1", lambda: BLSEngine(
        settings, bls_transport, clock=clock, freshness_policy=policy))
    registry.register("census", "1", lambda: CensusEngine(
        settings, census_transport, clock=clock, freshness_policy=policy))
    registry.register("gate_c_file_watch", "1", lambda: GateCFileEngine(settings, file_transport))

    if gate_a:
        validator = lambda spec, stage: worldbank_reusable(
            audit, spec, stage, freshness_policy=policy)
        registry.register("worldbank_collect_audit", "1", lambda: WorldBankAuditedCollection(
            audit, worldbank_transport, settings=settings), reuse_validator=validator)
        registry.register("worldbank_validate", "2", lambda: WorldBankValidation(
            audit, freshness_policy=policy), reuse_validator=validator)

    validators = additional_reuse_validators or {}
    for (engine, version), implementation in (additional_engines or {}).items():
        registry.register(engine, version, lambda implementation=implementation: implementation,
                          reuse_validator=validators.get((engine, version)))
    unknown_validators = validators.keys() - (additional_engines or {}).keys()
    if unknown_validators:
        raise ValueError("reuse validators require a matching additional engine")
    return registry
