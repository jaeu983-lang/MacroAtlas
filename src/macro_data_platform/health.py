from __future__ import annotations

import sys
from pathlib import Path


def check_project_layout(project_root: Path) -> list[str]:
    required = ["AGENTS.md", "GUIDELINES.md", "pyproject.toml", "src", "tests"]
    return [item for item in required if not (project_root / item).exists()]


def main() -> int:
    # Keep the consumer's encoding, but escape unsupported path characters instead
    # of crashing on redirected legacy Windows streams (for example cp949).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    root = Path(__file__).resolve().parents[2]
    missing = check_project_layout(root)
    if missing:
        print("FAIL: required project items missing: " + ", ".join(missing))
        return 1
    print(f"OK: project layout verified ({root})")
    print(f"Python: {sys.version.split()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
