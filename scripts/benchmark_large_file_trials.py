"""Reproducible bounded qualification experiments; fixtures and trial chunks are disposable."""

import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path

from macro_data_platform.config import Settings
from macro_data_platform.ingestion.large_file_trial import (
    DEFAULT_BUDGET,
    create_trial,
    make_trial_orchestrator,
)
from macro_data_platform.ingestion.non_api_capacity import DeferredNonAPIStore, decision
from macro_data_platform.storage.history import HistoryStore


def generate(path, target, columns=10):
    header = ",".join(f"c{i}" for i in range(columns)) + "\n"
    values = ["0", "", "12345678901234567890123456789012"] + ["data_12345678"] * (columns - 3)
    row = ",".join(values) + "\n"
    count = max(1, (target - len(header)) // len(row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(header)
        for _ in range(count // 1024):
            stream.write(row * 1024)
        stream.write(row * (count % 1024))
    return count


def main():
    root = Path(__file__).resolve().parents[1]
    settings = Settings(root, data_dir="data/qualification_benchmark")
    inbox = settings._inside(f"{settings.data_dir}/inbox")
    inbox.mkdir(parents=True, exist_ok=True)
    store = HistoryStore(settings)
    catalog = DeferredNonAPIStore(settings)
    runner = make_trial_orchestrator(store, settings)
    results = []
    with tempfile.TemporaryDirectory(prefix="qualification-fixtures-", dir=inbox) as directory:
        base = Path(directory)
        for mib, columns in [(1, 10), (16, 10), (64, 10), (16, 512), (96, 10), (127, 10)]:
            source = base / f"csv-{mib}-{columns}.csv"
            count = generate(source, mib * 1024 * 1024, columns)
            for repeat in range(2):
                results.append(
                    trial(
                        root,
                        source,
                        store,
                        catalog,
                        runner,
                        f"csv_{mib}MiB_{columns}cols_r{repeat + 1}",
                        expected_rows=count,
                    )
                )
        zipped = base / "stored.zip"
        with zipfile.ZipFile(zipped, "w", zipfile.ZIP_STORED) as archive:
            archive.write(base / "csv-16-10.csv", "data.csv")
            archive.writestr("README.md", "Synthetic qualification fixture")
        results.append(trial(root, zipped, store, catalog, runner, "zip_single_table"))
        ambiguous = base / "ambiguous.txt"
        ambiguous.write_text("date|value\n20260101|0\n20260102|\n", encoding="utf-8")
        results.append(trial(root, ambiguous, store, catalog, runner, "ambiguous_delimiter"))
        malformed = base / "ragged.csv"
        malformed.write_text("a,b\n1\n")
        results.append(trial(root, malformed, store, catalog, runner, "ragged_rows"))
        large = base / "above-budget.csv"
        with large.open("wb") as stream:
            stream.truncate(DEFAULT_BUDGET.input_bytes)
        results.append(trial(root, large, store, catalog, runner, "input_ceiling_no_read"))
        for label, budget in [
            ("output_budget", replace(DEFAULT_BUDGET, output_bytes=4096)),
            ("low_memory", replace(DEFAULT_BUDGET, memory_bytes=8 * 1024 * 1024)),
            ("wall_timeout", replace(DEFAULT_BUDGET, wall_seconds=1)),
        ]:
            results.append(
                trial(root, base / "csv-64-10.csv", store, catalog, runner, label, budget=budget)
            )
    report = {
        "environment": {
            "platform": os.sys.platform,
            "cpu_count": os.cpu_count(),
            "free_disk_bytes": shutil.disk_usage(root).free,
        },
        "budget": DEFAULT_BUDGET.__dict__,
        "cases": results,
        "note": "Synthetic/replay qualification only. No production approval or natural Gate C evidence.",
    }
    output = root / "reports/large_file_qualification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(output.relative_to(root)), "cases": len(results)}))


def trial(
    root, source, store, catalog, runner, label, *, expected_rows=None, budget=DEFAULT_BUDGET
):
    parent = runner.create("Explicit synthetic capacity qualification candidate")
    scope = {"relative_path": source.relative_to(root).as_posix(), "format": source.suffix[1:]}
    record = catalog.register(
        scope,
        parent.task_id,
        "candidate",
        decision("qualification_candidate", status="inspection_required"),
    )
    task_id = create_trial(store, store.settings, record["id"], budget=budget)
    doc = runner.run(task_id)
    payload = doc["stages"][-1]["result"]["payload"]
    if expected_rows is not None and payload.get("execution_state") == "TRIAL_PASSED":
        assert payload["rows"] == expected_rows
    result = {
        "case": label,
        "input_bytes": source.stat().st_size,
        "task_id": task_id,
        "task_status": doc["status"],
        "result": payload,
    }
    print(
        json.dumps(
            {
                "case": label,
                "state": payload.get("execution_state"),
                "reason": payload.get("reason"),
                "seconds": payload.get("elapsed_seconds"),
                "peak_rss_bytes": payload.get("peak_rss_bytes"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return result


if __name__ == "__main__":
    main()
