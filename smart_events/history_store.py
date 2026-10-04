from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOG_HEADERS = [
    "ts_log", "event_uuid", "event_hash", "fecha_evento", "telefono_e164",
    "client_uuid", "tipo_evento_id", "tipo_evento_nombre", "detalle_evento",
    "sku", "talla", "monto", "canal", "pct", "moneda", "actor", "device",
    "origen", "silencio_flag_system", "meta_json", "status",
]


def _load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class HistorySheetConfig:
    spreadsheet_id: str
    log_sheet: str = "eventos_log_v5"
    service_account_file: str = ""

    @classmethod
    def from_env(cls) -> "HistorySheetConfig":
        _load_dotenv()
        return cls(
            spreadsheet_id=os.getenv("SMART_SPREADSHEET_ID", "").strip(),
            log_sheet=os.getenv("SMART_SHEET_NAME", "eventos_log_v5").strip() or "eventos_log_v5",
            service_account_file=(
                os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
                or os.getenv("FINANCE_GOOGLE_SERVICE_ACCOUNT_FILE")
                or ""
            ).strip(),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.spreadsheet_id:
            errors.append("SMART_SPREADSHEET_ID requerido")
        if not self.service_account_file:
            errors.append("GOOGLE_SERVICE_ACCOUNT_FILE requerido")
        elif not Path(self.service_account_file).expanduser().exists():
            errors.append("GOOGLE_SERVICE_ACCOUNT_FILE no existe")
        return errors


class GoogleSheetHistoryStore:
    """Read-only reader for the canonical eventos_log_v5 history."""

    def __init__(self, cfg: HistorySheetConfig, service: Any | None = None):
        self.cfg = cfg
        self._service = service

    def _svc(self):
        if self._service is not None:
            return self._service
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = Credentials.from_service_account_file(
            str(Path(self.cfg.service_account_file).expanduser()), scopes=scopes
        )
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    def _get(self, range_: str) -> list[list[Any]]:
        result = (
            self._svc()
            .spreadsheets()
            .values()
            .get(spreadsheetId=self.cfg.spreadsheet_id, range=range_)
            .execute()
        )
        return result.get("values") or []

    def read_logged_events(self) -> list[dict[str, Any]]:
        values = self._get(f"'{self.cfg.log_sheet}'!A:U")
        if not values:
            raise RuntimeError(f"{self.cfg.log_sheet} no existe o está vacía")
        headers = [str(x).strip() for x in values[0]]
        if headers[: len(LOG_HEADERS)] != LOG_HEADERS:
            raise RuntimeError(
                "Contrato eventos_log_v5 no coincide; se aborta para evitar interpretar columnas equivocadas"
            )
        rows: list[dict[str, Any]] = []
        for raw in values[1:]:
            raw = list(raw) + [""] * (len(headers) - len(raw))
            row = dict(zip(headers, raw))
            if str(row.get("status") or "").strip().upper() == "LOGGED":
                rows.append(row)
        return rows
