import tempfile
import unittest
from pathlib import Path

from macro_data_platform.config import Settings
from macro_data_platform.contracts import StageResult, StageStatus
from macro_data_platform.orchestration import (
    EngineRegistry,
    StageSpec,
    TaskPlan,
    build_engine_registry,
)
from macro_data_platform.storage.history import HistoryStore


class _FixedEngine:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def run(self, request):
        self.calls += 1
        return self.result


class EngineRegistryTests(unittest.TestCase):
    def test_resume_resolves_engine_from_immutable_saved_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=False)
            store = HistoryStore(settings)
            plan = TaskPlan((StageSpec("collect", "fixture", {}, max_attempts=2),))
            failing = _FixedEngine(StageResult(StageStatus.NEEDS_REVIEW))
            first = EngineRegistry(store)
            first.register("fixture", "1", lambda: failing)
            task = first.orchestrator_for(plan=plan).create("fixture resume")
            first.orchestrator_for(plan=plan).plan(task.task_id, plan)
            failed = first.orchestrator_for_task(task.task_id).run(task.task_id)
            self.assertEqual(failed["status"], "NEEDS_REVIEW")
            self.assertEqual(failing.calls, 1)

            recovered_engine = _FixedEngine(StageResult(StageStatus.SUCCEEDED, {"ok": True}))
            restarted = EngineRegistry(HistoryStore(settings))
            restarted.register("fixture", "1", lambda: recovered_engine)
            resumed = restarted.resume(task.task_id, approved=True)
            self.assertEqual(resumed["status"], "COMPLETED")
            self.assertEqual(resumed["task_id"], task.task_id)
            self.assertEqual(recovered_engine.calls, 1)
            self.assertEqual(len(resumed["attempts"]), 2)

    def test_registry_rejects_ambiguous_or_missing_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = EngineRegistry(HistoryStore(Settings(Path(directory))))
            engine = _FixedEngine(StageResult(StageStatus.SUCCEEDED))
            registry.register("fixture", "1", lambda: engine)
            with self.assertRaisesRegex(ValueError, "already registered"):
                registry.register("fixture", "1", lambda: engine)
            with self.assertRaisesRegex(ValueError, "unregistered engine versions"):
                registry.orchestrator_for(engine_keys={("fixture", "2")})

    def test_composition_root_registers_source_adapters_by_version(self):
        from macro_data_platform.ingestion.bls import BLSEngine
        from macro_data_platform.ingestion.boj import BOJMetadataEngine, BOJObservationEngine
        from macro_data_platform.ingestion.census import CensusEngine
        from macro_data_platform.ingestion.worldbank import WorldBankGDPEngine

        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=False)
            registry = build_engine_registry(settings, HistoryStore(settings), gate_a=True)
            self.assertTrue({
                ("worldbank_gdp", "2"),
                ("worldbank_collect_audit", "1"),
                ("worldbank_validate", "2"),
                ("boj_metadata", "1"),
                ("boj_observations", "2"),
                ("bls", "1"),
                ("census", "1"),
                ("gate_c_file_watch", "1"),
            }.issubset(registry.keys))
            expected = {
                ("worldbank_gdp", "2"): WorldBankGDPEngine,
                ("boj_metadata", "1"): BOJMetadataEngine,
                ("boj_observations", "2"): BOJObservationEngine,
                ("bls", "1"): BLSEngine,
                ("census", "1"): CensusEngine,
            }
            for key, engine_type in expected.items():
                with self.subTest(engine=key):
                    runner = registry.orchestrator_for(engine_keys={key})
                    self.assertIsInstance(runner.engines[key], engine_type)
