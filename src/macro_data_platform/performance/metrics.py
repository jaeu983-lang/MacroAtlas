"""In-memory phase timers; only validated labels and numeric sizes are persisted."""
import os
import platform
import re
import subprocess
import sys
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from functools import lru_cache, wraps
from time import perf_counter_ns

PHASES = frozenset({"network", "raw_write", "parse", "quality", "sqlite", "export", "worker"})
SAMPLE_CLASSES = frozenset({
    "fixture", "synthetic", "live_api", "live_file", "stored", "unspecified",
})
CACHE_STATES = frozenset({"hit", "miss", "not_applicable"})
_ACTIVE_METRICS: ContextVar["PerformanceMetrics | None"] = ContextVar(
    "macroatlas_performance_metrics", default=None,
)


class PerformanceMetrics:
    """Per-operation timing accumulator with no request, payload, or URL fields."""

    def __init__(self):
        self._phase_timings_ns = {}
        self.input_bytes = None
        self.input_rows = None
        self.input_columns = None
        self.output_bytes = None
        self.output_rows = None
        self.output_columns = None
        self.sample_class = "unspecified"
        self.cache_status = "not_applicable"

    @contextmanager
    def measure(self, phase):
        if phase not in PHASES:
            raise ValueError("unsupported performance phase")
        started = perf_counter_ns()
        try:
            yield
        finally:
            elapsed = max(0, perf_counter_ns() - started)
            self._phase_timings_ns[phase] = self._phase_timings_ns.get(phase, 0) + elapsed

    @contextmanager
    def activate(self):
        token = _ACTIVE_METRICS.set(self)
        try:
            yield self
        finally:
            _ACTIVE_METRICS.reset(token)

    def observe_input(self, *, byte_count=None, rows=None, columns=None):
        self.input_bytes = _valid_count(byte_count, self.input_bytes)
        self.input_rows = _valid_count(rows, self.input_rows)
        self.input_columns = _valid_count(columns, self.input_columns)

    def observe_output(self, *, byte_count=None, rows=None, columns=None):
        self.output_bytes = _valid_count(byte_count, self.output_bytes)
        self.output_rows = _valid_count(rows, self.output_rows)
        self.output_columns = _valid_count(columns, self.output_columns)

    def observe_sample_class(self, value):
        value = getattr(value, "value", value)
        mapping = {"live_api": "live_api", "live_ingestion": "live_api",
                   "live_file": "live_file", "fixture": "fixture",
                   "synthetic": "synthetic", "stored": "stored"}
        self.sample_class = mapping.get(value, "unspecified") if isinstance(value, str) else "unspecified"

    def observe_cache(self, value):
        self.cache_status = value if value in {"hit", "miss"} else "not_applicable"

    def snapshot(self):
        return {
            "phase_timings_ns": {
                phase: duration for phase, duration in self._phase_timings_ns.items()
                if phase in PHASES and type(duration) is int and duration >= 0
            },
            "input_bytes": self.input_bytes,
            "input_rows": self.input_rows,
            "input_columns": self.input_columns,
            "output_bytes": self.output_bytes,
            "output_rows": self.output_rows,
            "output_columns": self.output_columns,
            "sample_class": self.sample_class,
            "cache_status": self.cache_status,
        }


def _valid_count(value, previous):
    if value is None:
        return previous
    if type(value) is int and 0 <= value <= 10**15:
        return value
    return previous


def measure_current(phase):
    metrics = _ACTIVE_METRICS.get()
    return metrics.measure(phase) if metrics is not None else nullcontext()


def current_metrics():
    return _ACTIVE_METRICS.get()


def measured_phase(phase):
    """Time a pure/leaf operation only when it runs inside an instrumented call."""
    if phase not in PHASES:
        raise ValueError("unsupported performance phase")

    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with measure_current(phase):
                result = function(*args, **kwargs)
            if phase == "parse":
                if args:
                    observe_download(args[0])
                observe_result_shape(result)
            return result
        return wrapped

    return decorate


def observe_download(download):
    metrics = current_metrics()
    body = getattr(download, "body", None)
    if metrics is None or not isinstance(body, bytes):
        return
    metrics.observe_input(byte_count=len(body))
    metrics.observe_sample_class(getattr(download, "kind", None))


def observe_result_shape(result):
    """Extract counts only; never serialize or retain result values."""
    metrics = current_metrics()
    if metrics is None:
        return
    rows = None
    columns = None
    if isinstance(result, dict):
        candidates = result.get("observations")
        if not isinstance(candidates, list):
            candidates = result.get("rows")
        if isinstance(candidates, list):
            rows = len(candidates)
            first = next((item for item in candidates if isinstance(item, dict)), None)
            columns = len(first) if first is not None else 0
    else:
        candidates = result if isinstance(result, (list, tuple)) else getattr(result, "rows", None)
        headers = getattr(result, "headers", None)
        if isinstance(candidates, (list, tuple)):
            rows = len(candidates)
            first = next((item for item in candidates if isinstance(item, dict)), None)
            columns = len(first) if first is not None else 0
        if isinstance(headers, (list, tuple)):
            columns = len(headers)
    metrics.observe_output(rows=rows, columns=columns)


@lru_cache(maxsize=16)
def _resolve_code_sha(project_root: str) -> str:
    supplied = os.environ.get("MACROATLAS_CODE_SHA") or os.environ.get("GITHUB_SHA")
    if supplied and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", supplied):
        return supplied
    root = os.path.abspath(project_root)
    try:
        state = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root,
            check=False, capture_output=True, text=True, timeout=1,
        )
        if state.returncode != 0 or state.stdout.strip():
            return "unknown"
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=root,
            check=False, capture_output=True, text=True, timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    value = completed.stdout.strip().lower()
    return value if completed.returncode == 0 and re.fullmatch(
        r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value,
    ) else "unknown"


def runtime_metadata(project_root):
    """Return environment fields that cannot contain paths, hostnames, or credentials."""
    return {
        "code_sha": _resolve_code_sha(str(project_root)),
        "python_version": platform.python_version(),
        "platform": sys.platform[:32],
        "architecture": (platform.machine() or "unknown")[:64],
    }


def workload_tier(input_bytes, input_rows):
    if input_bytes is not None:
        for ceiling, label in ((64 * 1024, "bytes_le_64k"), (1024**2, "bytes_le_1m"),
                               (16 * 1024**2, "bytes_le_16m"),
                               (128 * 1024**2, "bytes_le_128m")):
            if input_bytes <= ceiling:
                return label
        return "bytes_gt_128m"
    if input_rows is not None:
        for ceiling, label in ((100, "rows_le_100"), (10_000, "rows_le_10k"),
                               (1_000_000, "rows_le_1m")):
            if input_rows <= ceiling:
                return label
        return "rows_gt_1m"
    return "unknown"
