"""Read-only CLI for bounded recurring-pattern analysis."""
import argparse
import json
from pathlib import Path

from macro_data_platform.analysis.patterns import PatternAnalyzer
from macro_data_platform.config import Settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    report = PatternAnalyzer(Settings(args.project_root.resolve())).analyze()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
