"""Offline defaults and repository-contained storage paths; no I/O on construction."""
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: str = "data"
    network_enabled: bool = False

    def __post_init__(self) -> None:
        root = self.project_root.resolve()
        object.__setattr__(self, "project_root", root)
        self._inside(self.data_dir)

    def _inside(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or path.drive or not relative.strip():
            raise ValueError("storage paths must be repository-relative")
        resolved = (self.project_root / path).resolve()
        if not resolved.is_relative_to(self.project_root) or resolved == self.project_root:
            raise ValueError("storage path must stay inside the repository")
        return resolved

    @classmethod
    def from_env(cls, project_root: Path, env: Mapping[str, str]) -> "Settings":
        enabled = env.get("MACROATLAS_NETWORK_ENABLED", "false").lower()
        if enabled not in {"true", "false"}:
            raise ValueError("MACROATLAS_NETWORK_ENABLED must be true or false")
        return cls(project_root, env.get("MACROATLAS_DATA_DIR", "data"), enabled == "true")

    @property
    def database_path(self) -> Path:
        return self._inside(f"{self.data_dir}/catalog.sqlite")

    @property
    def raw_dir(self) -> Path:
        return self._inside(f"{self.data_dir}/raw")

    @property
    def normalized_dir(self) -> Path:
        return self._inside(f"{self.data_dir}/processed")
