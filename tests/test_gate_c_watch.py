"""Persisted Gate C source-watch tests; transport failures are controlled fixtures."""
import io
import os
import tempfile
import unittest
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from macro_data_platform.config import Settings
from macro_data_platform.connectors.official_files import (
    PROFILES,
    OfficialFileDownload,
    OfficialFileTransport,
)
from macro_data_platform.connectors.statistical_http import SourceFailure
from macro_data_platform.contracts import ErrorCode, StageStatus
from macro_data_platform.ingestion.gate_c_watch import (
    build_gate_c_watch_plan,
    make_gate_c_watch_orchestrator,
)
from macro_data_platform.storage.history import HistoryStore

NOW = datetime(2026, 10, 26, tzinfo=UTC)


def zip_csv(value):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("WS_GLI_csv_col.csv", f"period,value\n2026Q1,{value}\n")
    return output.getvalue()


def download(source_id, body, retrieved_at=NOW):
    profile = PROFILES[source_id]
    return OfficialFileDownload(source_id, profile["url"], body, 200, retrieved_at,
                                 "application/zip", "Wed, 21 Oct 2026 07:59:26 GMT")


class FixtureTransport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def fetch(self, source_id):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class GateCWatchTests(unittest.TestCase):
    def test_live_transport_uses_configured_proxy_ca_and_fixed_url(self):
        class Response:
            def __init__(self):
                self.status_code = 200
                self.headers = {"Content-Length": "3", "Content-Type": "text/plain"}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def iter_content(self, chunk_size):
                yield b"abc"

        class Session:
            def __init__(self):
                self.trust_env = True
                self.call = None

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return None

            def get(self, url, **kwargs):
                self.call = (url, kwargs)
                return Response()

        session = Session()
        with (patch("macro_data_platform.connectors.official_files.requests.Session",
                    return_value=session),
              patch.dict(os.environ, {"HTTP_PROXY": "http://proxy:8080",
                                      "HTTPS_PROXY": "http://proxy:8080",
                                      "REQUESTS_CA_BUNDLE": "/configured/ca.pem"})):
            result = OfficialFileTransport().fetch("tic")
        url, kwargs = session.call
        self.assertFalse(session.trust_env)
        self.assertEqual(url, PROFILES["tic"]["url"])
        self.assertEqual(kwargs["proxies"], {
            "http": "http://proxy:8080", "https": "http://proxy:8080",
        })
        self.assertEqual(kwargs["verify"], "/configured/ca.pem")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (5, 30))
        self.assertEqual(result.body, b"abc")

    def test_source_scope_change_preserves_raw_and_withholds_normalized_output(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            store = HistoryStore(settings)
            first_transport = FixtureTransport([download("bis", zip_csv("1"))])
            first_runner = make_gate_c_watch_orchestrator(store, settings, first_transport)
            first_task = first_runner.create("BIS baseline")
            first_runner.plan(first_task.task_id, build_gate_c_watch_plan("bis"))
            first = first_runner.run(first_task.task_id)
            self.assertEqual(first["status"], "COMPLETED")

            second_transport = FixtureTransport([
                download("bis", zip_csv("2"), NOW + timedelta(seconds=1)),
            ])
            second_runner = make_gate_c_watch_orchestrator(store, settings, second_transport)
            second_task = second_runner.create("BIS changed copy")
            second_runner.plan(second_task.task_id, build_gate_c_watch_plan("bis"))
            second = second_runner.run(second_task.task_id)
            self.assertEqual(second["status"], "NEEDS_REVIEW")
            payload = second["stages"][-1]["result"]["payload"]
            self.assertEqual(payload["source_change_status"], "changed")
            self.assertNotIn("normalized_path", payload)
            self.assertTrue(Path(directory, payload["raw_path"]).is_file())
            self.assertTrue(Path(directory, payload["request_manifest_path"]).is_file())

    def test_same_task_resumes_after_controlled_transient_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=True)
            store = HistoryStore(settings)
            transport = FixtureTransport([
                SourceFailure(StageStatus.FAILED_RETRYABLE, ErrorCode.TRANSIENT,
                              "fixture 503", 503),
                download("bis", zip_csv("3"), NOW + timedelta(seconds=1)),
            ])
            runner = make_gate_c_watch_orchestrator(store, settings, transport)
            task = runner.create("BIS source watch")
            runner.plan(task.task_id, build_gate_c_watch_plan("bis"))
            failed = runner.run(task.task_id)
            self.assertEqual(failed["status"], "FAILED")
            resumed = runner.resume(task.task_id)
            self.assertEqual(resumed["status"], "COMPLETED")
            self.assertEqual(resumed["task_id"], failed["task_id"])
            self.assertEqual(transport.calls, 2)
            self.assertEqual(len(resumed["attempts"]), 2)
            self.assertIn("TASK_RESUMED", [e["kind"] for e in store.events(task.task_id)])

    def test_task_is_planned_and_persisted_before_live_stage_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), network_enabled=False)
            store = HistoryStore(settings)
            runner = make_gate_c_watch_orchestrator(store, settings,
                                                   FixtureTransport([download("tic", b"x")]))
            task = runner.create("TIC source watch")
            runner.plan(task.task_id, build_gate_c_watch_plan("tic"))
            self.assertEqual(store.get(task.task_id)["status"], "PLANNED")
            result = runner.run(task.task_id)
            self.assertEqual(result["status"], "NEEDS_REVIEW")
            self.assertEqual(runner.engines[("gate_c_file_watch", "1")].transport.calls, 0)


if __name__ == "__main__":
    unittest.main()
