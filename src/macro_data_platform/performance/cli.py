"""Read-only CLI for privacy-safe performance summaries."""
import argparse
import json
import os
from pathlib import Path

from macro_data_platform.config import Settings
from macro_data_platform.performance.report import build_performance_report


def main(argv=None):
    parser = argparse.ArgumentParser(prog="macro-perf", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="read the local performance sample table")
    report.add_argument("--project-root", type=Path, default=Path.cwd())
    report.add_argument("--limit", type=int, default=10_000)
    args = parser.parse_args(argv)
    data_dir = os.environ.get("MACROATLAS_DATA_DIR", "data")
    settings = Settings(args.project_root, data_dir=data_dir)
    result = build_performance_report(settings.performance_database_path, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] in {"READY", "NO_DATA"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
