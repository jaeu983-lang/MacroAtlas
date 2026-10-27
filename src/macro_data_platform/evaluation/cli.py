"""Validate curated evaluation case sets without running or changing any engine."""

import argparse
import json
from pathlib import Path

from macro_data_platform.evaluation.cases import validate_case_sets


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate development/validation/holdout cases")
    validate.add_argument("--sets-dir", type=Path, default=Path.cwd() / "evaluation" / "sets")
    args = parser.parse_args(argv)
    report = validate_case_sets(args.sets_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"READY", "VALID_BUT_EMPTY"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
