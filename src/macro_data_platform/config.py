"""Offline defaults, safe local settings loading and repository-contained storage paths."""
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

MAX_ENV_FILE_BYTES = 16 * 1024
_SUPPORTED_ENV_KEYS = frozenset({
    "MACROATLAS_DATA_DIR", "MACROATLAS_NETWORK_ENABLED", "BEA_API_KEY", "ESTAT_APP_ID",
    "FRED_API_KEY", "CENSUS_API_KEY", "BLS_API_KEY",
})


def _parse_env_file(path: Path) -> dict[str, str]:
    """Read a small, non-executable .env file without interpolation or value-bearing errors."""
    if path.is_symlink():
        raise ValueError("The project .env file must not be a symbolic link")
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {}
    if not path.is_file() or stat.st_size > MAX_ENV_FILE_BYTES:
        raise ValueError("The project .env file is not a regular file within the size limit")
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_ENV_FILE_BYTES:
            raise ValueError("The project .env file exceeds the size limit")
        content = raw.decode("utf-8-sig")
    except (OSError, UnicodeError):
        raise ValueError("The project .env file could not be read as UTF-8") from None

    values: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, separator, raw_value = stripped.partition("=")
        name = name.strip()
        if not separator or name not in _SUPPORTED_ENV_KEYS:
            raise ValueError("The project .env file contains an unsupported or malformed setting")
        if name in values:
            raise ValueError("The project .env file contains a duplicate setting")
        value = raw_value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            if len(value) < 2 or value[-1] != quote:
                raise ValueError("The project .env file contains an unterminated quoted setting")
            value = value[1:-1]
        if len(value) > 512 or "\x00" in value or "\r" in value or "\n" in value:
            raise ValueError("The project .env file contains an invalid setting value")
        values[name] = value
    return values


def _credential(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    normalized = value.strip()
    if len(normalized) > 512 or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{name} contains an invalid value")
    return normalized or None


@dataclass(frozen=True)
class Settings:
    project_root: Path
    data_dir: str = "data"
    network_enabled: bool = False
    bea_api_key: str | None = field(default=None, repr=False)
    estat_app_id: str | None = field(default=None, repr=False)
    fred_api_key: str | None = field(default=None, repr=False)
    census_api_key: str | None = field(default=None, repr=False)
    bls_api_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        root = self.project_root.resolve()
        object.__setattr__(self, "project_root", root)
        self._inside(self.data_dir)
        for name in ("bea_api_key", "estat_app_id", "fred_api_key", "census_api_key", "bls_api_key"):
            value = getattr(self, name)
            if value is not None:
                normalized = _credential({name: value}, name)
                object.__setattr__(self, name, normalized)

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
        return cls(
            project_root,
            env.get("MACROATLAS_DATA_DIR", "data"),
            enabled == "true",
            _credential(env, "BEA_API_KEY"),
            _credential(env, "ESTAT_APP_ID"),
            _credential(env, "FRED_API_KEY"),
            _credential(env, "CENSUS_API_KEY"),
            _credential(env, "BLS_API_KEY"),
        )

    @classmethod
    def from_project_env(
        cls,
        project_root: Path,
        process_env: Mapping[str, str] | None = None,
    ) -> "Settings":
        """Load the repository-root .env, then let process environment override it."""
        root = project_root.resolve()
        merged = _parse_env_file(root / ".env")
        merged.update(os.environ if process_env is None else process_env)
        return cls.from_env(root, merged)

    @property
    def database_path(self) -> Path:
        return self._inside(f"{self.data_dir}/catalog.sqlite")

    @property
    def raw_dir(self) -> Path:
        return self._inside(f"{self.data_dir}/raw")

    @property
    def normalized_dir(self) -> Path:
        return self._inside(f"{self.data_dir}/processed")
