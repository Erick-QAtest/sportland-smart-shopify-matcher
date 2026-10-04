from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class MemoryConfig:
    database_url: str
    source_name: str = "sportland_smart_v5"
    store_phone: bool = False

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "MemoryConfig":
        load_dotenv(env_path, override=False)
        store_phone = os.getenv("MEMORY_STORE_PHONE", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        return cls(
            database_url=os.getenv("DATABASE_URL", "").strip(),
            source_name=os.getenv("MEMORY_SOURCE_NAME", "sportland_smart_v5").strip()
            or "sportland_smart_v5",
            store_phone=store_phone,
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.database_url:
            errors.append("DATABASE_URL requerido")
        elif not self.database_url.startswith(("postgresql://", "postgres://")):
            errors.append("DATABASE_URL debe ser PostgreSQL")
        return errors
