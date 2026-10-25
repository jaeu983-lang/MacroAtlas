"""Deterministic offline microbenchmark for selected MacroAtlas components."""
from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import sys
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def product_code_fingerprint() -> str:
    digest = hashlib.sha256()
    paths = [*ROOT.joinpath("src").rglob("*.py"),
             *ROOT.joinpath("tests").rglob("*.py"),
             *ROOT.joinpath("tests", "fixtures").rglob("*")]
    paths.append(ROOT / "pyproject.toml")
    for path in sorted((item for item in paths if item.is_file()),
                       key=lambda item: item.relative_to(ROOT).as_posix()):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def percentile_measurement(name: str, function, repetitions: int) -> dict:
    print(f"Starting component measurement: {name}", file=sys.stderr, flush=True)
    samples_ms: list[float] = []
    max_peak_bytes = 0
    tracemalloc.start()
    cpu_start = time.process_time()
    for _ in range(repetitions):
        tracemalloc.reset_peak()
        started = time.perf_counter()
        function()
        samples_ms.append((time.perf_counter() - started) * 1000)
        _, peak = tracemalloc.get_traced_memory()
        max_peak_bytes = max(max_peak_bytes, peak)
    cpu_seconds = time.process_time() - cpu_start
    tracemalloc.stop()
    print(f"Finished component measurement: {name}", file=sys.stderr, flush=True)
    return {
        "name": name,
        "repetitions": repetitions,
        "wall_ms": {
            "p50": round(percentile(samples_ms, 0.50), 4),
            "p95": round(percentile(samples_ms, 0.95), 4),
            "max": round(max(samples_ms), 4),
        },
        "cpu_seconds_total": round(cpu_seconds, 6),
        "python_tracemalloc_peak_bytes": max_peak_bytes,
    }


class _FakeResponse:
    def __init__(self, body: bytes):
        self.status_code = 200
        self.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset:offset + chunk_size]


class _MockSessionFactory:
    def __init__(self, response_body: bytes):
        self.response_body = response_body
        self.calls = 0
        self.query_bytes = 0
        self.response_bytes = 0
        self.fingerprints: set[str] = set()
        self.duplicate_calls = 0

    def __call__(self):
        return _MockSession(self)


class _MockSession:
    def __init__(self, owner: _MockSessionFactory):
        self.owner = owner
        self.trust_env = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, _url, *, params, **_kwargs):
        self.owner.calls += 1
        encoded = urlencode(params).encode("ascii")
        self.owner.query_bytes += len(encoded)
        request_fingerprint = hashlib.sha256(encoded).hexdigest()
        if request_fingerprint in self.owner.fingerprints:
            self.owner.duplicate_calls += 1
        self.owner.fingerprints.add(request_fingerprint)
        self.owner.response_bytes += len(self.owner.response_body)
        return _FakeResponse(self.owner.response_body)


def run_component_benchmarks() -> dict:
    from test_metadata_discovery import document, institution
    from test_worldbank import fixture_download

    from macro_data_platform.config import Settings
    from macro_data_platform.connectors.bea import BEAClient
    from macro_data_platform.connectors.estat import EStatClient
    from macro_data_platform.connectors.official_api import JsonApiTransport
    from macro_data_platform.connectors.worldbank import GDPQuery, parse_gdp
    from macro_data_platform.discovery.series import SeriesDiscoveryService, parse_request
    from macro_data_platform.ingestion.formats import parse_table
    from macro_data_platform.metadata.adapters import read_metadata

    results: list[dict] = []
    phrase = "미국 명목 GDP 2020 2022"

    def natural_language_parse():
        request, _ = parse_request(phrase, request_id="perf-baseline")
        assert request.concept == "gdp_nominal" and request.countries == ("USA",)

    results.append(percentile_measurement("natural_language_rule_parse", natural_language_parse, 200))

    catalogue = document()
    institution_candidate = institution()

    def metadata_normalization():
        result = read_metadata(catalogue, institution_candidate)
        assert len(result.records) == 1

    results.append(percentile_measurement("metadata_normalization_worldbank_shaped_fixture",
                                          metadata_normalization, 100))

    records = read_metadata(catalogue, institution_candidate).records
    settings = Settings(ROOT)

    class _MetadataRecords:
        def __init__(self):
            self.settings = settings

        def current_records(self, **_kwargs):
            return records

        @staticmethod
        def validate_structure(_record):
            return None

    metadata = _MetadataRecords()
    history = SimpleNamespace(settings=settings)
    service = SeriesDiscoveryService(metadata, history)
    request, _ = parse_request(phrase, request_id="perf-baseline-search")

    def metadata_search():
        result = service.search(request)
        assert len(result.records) == 1

    results.append(percentile_measurement("series_discovery_in_memory_fixture_search",
                                          metadata_search, 50))

    csv_body = b"period,country,value\n2020,USA,123.5\n2021,USA,\n2022,USA,0\n"

    def csv_parse():
        result = parse_table(csv_body, "csv")
        assert len(result.rows) == 4 and result.rows[-1][-1] == "0"

    results.append(percentile_measurement("csv_parse_preserve_blank_and_zero", csv_parse, 100))

    download = fixture_download()

    def worldbank_parse():
        result = parse_gdp(download, GDPQuery())
        assert [row["value"] for row in result["observations"]] == [123.5, None, 0]

    results.append(percentile_measurement("worldbank_json_parse_fixture", worldbank_parse, 100))

    # This intentionally repeats identical requests to measure client overhead and lack of
    # request-level de-duplication. These are mocked calls; no real credential or network is used.
    repetitions = 40
    api_settings = Settings(ROOT, network_enabled=True,
                            bea_api_key="benchmark-placeholder-not-a-valid-key",
                            estat_app_id="benchmark-placeholder-not-a-valid-id")
    bea_body = b'{"BEAAPI":{"Results":{"DataSet":[{"DatasetName":"NIPA"}]}}}'
    bea_factory = _MockSessionFactory(bea_body)
    bea_transport = JsonApiTransport(api_settings, session_factory=bea_factory)
    bea = BEAClient(api_settings, bea_transport)

    def bea_metadata_call():
        response = bea.get_dataset_list()
        assert response.payload["BEAAPI"]["Results"]["DataSet"][0]["DatasetName"] == "NIPA"

    results.append(percentile_measurement("bea_dataset_list_mock_api", bea_metadata_call, repetitions))

    estat_body = b'{"GET_STATS_LIST":{"DATALIST_INF":{"TABLE_INF":[]}}}'
    estat_factory = _MockSessionFactory(estat_body)
    estat_transport = JsonApiTransport(api_settings, session_factory=estat_factory)
    estat = EStatClient(api_settings, estat_transport)

    def estat_table_list_call():
        response = estat.get_stats_list({"lang": "E"})
        assert response.payload["GET_STATS_LIST"]["DATALIST_INF"]["TABLE_INF"] == []

    results.append(percentile_measurement("estat_table_list_mock_api", estat_table_list_call,
                                          repetitions))

    mock_api = {}
    for name, factory in (("BEA", bea_factory), ("e-Stat", estat_factory)):
        mock_api[name] = {
            "requests": factory.calls,
            "unique_request_fingerprints": len(factory.fingerprints),
            "repeated_identical_requests": factory.duplicate_calls,
            "mock_query_bytes_total": factory.query_bytes,
            "mock_response_body_bytes_total": factory.response_bytes,
            "live_requests": 0,
        }

    return {"cases": results, "mock_api": mock_api,
            "external_http_requests": 0, "live_data_transferred_bytes": None}


def git_snapshot() -> dict:
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                            cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    return {"head_revision": revision, "worktree_dirty": bool(status),
            "visible_status_entries": len(status),
            "source_tests_and_fixtures_sha256": product_code_fingerprint()}


def main() -> int:
    baseline = {
        "schema_version": 1,
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "mode": "offline_fixture_and_mock_microbenchmark",
        "network_used": False,
        "git": git_snapshot(),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor() or None,
        },
        "measurement_limits": {
            "memory": "Python tracemalloc per microbenchmark; native SQLite memory and process RSS are not measured here.",
            "network": "BEA/e-Stat request and response byte counts come from injected mock transport; no wire bytes or live latency.",
            "agent": "No in-repository LLM client or token instrumentation was found; agent tokens/human review time are unavailable.",
        },
    }
    baseline["engine_microbenchmarks"] = run_component_benchmarks()
    baseline["microbenchmark_assertions"] = "passed"
    print(json.dumps(baseline, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
