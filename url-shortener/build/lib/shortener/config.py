import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import HttpUrl, TypeAdapter

SERVICE_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_path: Path = SERVICE_ROOT / "data" / "shortener.db"
    public_base_url: str = "http://127.0.0.1:8000"
    lock_timeout: float = 5.0

    def __post_init__(self):
        path = Path(self.database_path).expanduser()
        if not path.is_absolute():
            path = SERVICE_ROOT / path
        object.__setattr__(self, "database_path", path.resolve())
        url = TypeAdapter(HttpUrl).validate_python(self.public_base_url)
        if url.query or url.fragment or url.username or url.password or url.path not in (None, "/"):
            raise ValueError("Public base URL must be an HTTP(S) origin without credentials or a path")
        object.__setattr__(self, "public_base_url", str(url).rstrip("/"))
        if not 0 < self.lock_timeout <= 30:
            raise ValueError("Lock timeout must be greater than 0 and at most 30 seconds")

    @classmethod
    def from_env(cls):
        return cls(
            database_path=Path(os.environ.get("SHORTENER_DB_PATH", str(cls.database_path))),
            public_base_url=os.environ.get("SHORTENER_BASE_URL", cls.public_base_url),
            lock_timeout=float(os.environ.get("SHORTENER_LOCK_TIMEOUT", "5")),
        )
