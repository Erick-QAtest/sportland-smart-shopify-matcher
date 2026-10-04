from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .data_safe import INBOX_HEADERS, LOG_HEADERS, build_log_row, phone_hash, semantic_hash, validate_for_log
from .models import CapturedEvent, iso_utc


def _load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


@dataclass
class SheetConfig:
    spreadsheet_id: str
    log_sheet: str = "eventos_log_v5"
    inbox_sheet: str = "eventos_inbox_v1"
    catalog_sheet: str = "catalogo_eventos_db"
    service_account_file: str = ""

    @classmethod
    def from_env(cls) -> "SheetConfig":
        _load_dotenv()
        return cls(
            spreadsheet_id=os.getenv("SMART_SPREADSHEET_ID", "").strip(),
            log_sheet=os.getenv("SMART_SHEET_NAME", "eventos_log_v5").strip() or "eventos_log_v5",
            inbox_sheet=os.getenv("SMART_EVENT_INBOX_SHEET", "eventos_inbox_v1").strip() or "eventos_inbox_v1",
            catalog_sheet=os.getenv("SMART_EVENT_CATALOG_SHEET", "catalogo_eventos_db").strip() or "catalogo_eventos_db",
            service_account_file=(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") or os.getenv("FINANCE_GOOGLE_SERVICE_ACCOUNT_FILE") or "").strip(),
        )

    def validate(self) -> list[str]:
        out = []
        if not self.spreadsheet_id:
            out.append("SMART_SPREADSHEET_ID requerido")
        if not self.service_account_file:
            out.append("GOOGLE_SERVICE_ACCOUNT_FILE requerido")
        elif not Path(self.service_account_file).expanduser().exists():
            out.append("GOOGLE_SERVICE_ACCOUNT_FILE no existe")
        return out


class GoogleSheetEventStore:
    """Append-only writer for Smart. Never updates or deletes historical log rows."""

    def __init__(self, cfg: SheetConfig, service: Any | None = None):
        self.cfg = cfg
        self._service = service

    def _svc(self):
        if self._service is not None:
            return self._service
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(str(Path(self.cfg.service_account_file).expanduser()), scopes=scopes)
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    def _values_get(self, range_: str) -> list[list[Any]]:
        r = self._svc().spreadsheets().values().get(spreadsheetId=self.cfg.spreadsheet_id, range=range_).execute()
        return r.get("values") or []

    def _append(self, range_: str, row: list[Any]) -> None:
        self._svc().spreadsheets().values().append(
            spreadsheetId=self.cfg.spreadsheet_id,
            range=range_,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()

    def _ensure_inbox(self) -> None:
        # If sheet is absent, create it. We never auto-create/alter eventos_log_v5.
        meta = self._svc().spreadsheets().get(spreadsheetId=self.cfg.spreadsheet_id, fields="sheets.properties.title").execute()
        titles = {x["properties"]["title"] for x in meta.get("sheets") or []}
        if self.cfg.inbox_sheet not in titles:
            self._svc().spreadsheets().batchUpdate(
                spreadsheetId=self.cfg.spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": self.cfg.inbox_sheet}}}]},
            ).execute()
            self._append(f"'{self.cfg.inbox_sheet}'!A1:Q1", INBOX_HEADERS)
        else:
            current = self._values_get(f"'{self.cfg.inbox_sheet}'!A1:Q1")
            if not current:
                self._append(f"'{self.cfg.inbox_sheet}'!A1:Q1", INBOX_HEADERS)

    def verify_log_contract(self) -> None:
        rows = self._values_get(f"'{self.cfg.log_sheet}'!A1:U1")
        if not rows:
            raise RuntimeError(f"{self.cfg.log_sheet} no existe o no tiene headers")
        got = [str(x).strip() for x in rows[0]]
        if got[: len(LOG_HEADERS)] != LOG_HEADERS:
            raise RuntimeError("Contrato eventos_log_v5 no coincide; se aborta sin escribir")

    def event_catalog(self) -> dict[str, int]:
        rows = self._values_get(f"'{self.cfg.catalog_sheet}'!A2:B")
        out: dict[str, int] = {}
        for r in rows:
            if len(r) < 2:
                continue
            try:
                ident = int(float(r[0]))
            except Exception:
                continue
            name = str(r[1] or "").strip().upper()
            if ident > 0 and name:
                out[name] = ident
        if not out:
            raise RuntimeError("catalogo_eventos_db vacío/no accesible")
        return out

    def _existing_hashes(self) -> set[str]:
        rows = self._values_get(f"'{self.cfg.log_sheet}'!C2:C")
        return {str(r[0]).strip() for r in rows if r and str(r[0]).strip()}

    def _existing_source_ids(self) -> set[str]:
        self._ensure_inbox()
        rows = self._values_get(f"'{self.cfg.inbox_sheet}'!B2:B")
        return {str(r[0]).strip() for r in rows if r and str(r[0]).strip()}

    def _client_uuid(self, phone: str) -> str:
        if not phone:
            return ""
        # Existing log: E=phone, F=client_uuid.
        rows = self._values_get(f"'{self.cfg.log_sheet}'!E2:F")
        for r in reversed(rows):
            if len(r) >= 2 and str(r[0]).strip() == phone and str(r[1]).strip():
                return str(r[1]).strip()
        return str(uuid.uuid4())

    def append_inbox(self, event: CapturedEvent, *, sanitized_text: str, demand_relevant: bool, promotion_status: str, error_msg: str = "") -> bool:
        self._ensure_inbox()
        sid = event.source_event_id or ""
        if sid and sid in self._existing_source_ids():
            return False
        ev_uuid = str(uuid.uuid4())
        meta = dict(event.metadata)
        meta.update({"resolver_reason": event.resolver_reason, "resolver_confidence": event.resolver_confidence})
        row = [
            iso_utc(__import__("datetime").datetime.now(__import__("datetime").timezone.utc)),
            sid,
            ev_uuid,
            iso_utc(event.occurred_at),
            event.channel,
            event.normalized_type(),
            event.detail,
            event.sku,
            event.size,
            round(float(event.resolver_confidence or 0), 4),
            event.resolver_reason,
            "TRUE" if demand_relevant else "FALSE",
            phone_hash(event.phone_e164),
            sanitized_text,
            json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
            promotion_status,
            error_msg,
        ]
        self._append(f"'{self.cfg.inbox_sheet}'!A:Q", row)
        return True

    def promote_to_log(self, event: CapturedEvent) -> tuple[str, str]:
        self.verify_log_contract()
        catalog = self.event_catalog()
        errors = validate_for_log(event, catalog)
        if errors:
            return "NEEDS_REVIEW", " | ".join(errors)
        eid = catalog[event.normalized_type()]
        h = semantic_hash(event, eid)
        if h in self._existing_hashes():
            return "SKIPPED_DUPLICATE", "semantic event_hash already logged"
        phone = event.phone_e164
        client_uuid = self._client_uuid(phone)
        row = build_log_row(event, eid, client_uuid=client_uuid)
        self._append(f"'{self.cfg.log_sheet}'!A:U", row)
        return "LOGGED", ""

    def read_logged_events(self) -> list[dict[str, Any]]:
        self.verify_log_contract()
        values = self._values_get(f"'{self.cfg.log_sheet}'!A:U")
        if len(values) <= 1:
            return []
        headers = values[0]
        out = []
        for row in values[1:]:
            row = row + [""] * (len(headers) - len(row))
            out.append(dict(zip(headers, row)))
        return out
