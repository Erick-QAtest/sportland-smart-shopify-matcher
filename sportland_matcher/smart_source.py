from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
import csv
import json

from .config import Config
from .normalization import normalize_sku, normalize_size, normalize_text, parse_legacy_sku_size

GOOGLE_EPOCH = datetime(1899, 12, 30)


@dataclass
class DemandEvent:
    event_uuid: str
    event_hash: str
    fecha_evento: str
    client_uuid: str
    phone: str
    event_type: str
    detail: str
    smart_sku: str
    explicit_size: str
    requested_size: str
    size_source: str
    channel: str
    source_status: str
    pg_evento_id: str
    raw_row_number: int

    def to_dict(self) -> dict:
        return asdict(self)


def _google_serial_to_iso(value: object) -> str:
    if value in ("", None):
        return ""
    if isinstance(value, (int, float)):
        try:
            return (GOOGLE_EPOCH + timedelta(days=float(value))).isoformat()
        except Exception:
            return str(value)
    return str(value)


def _rows_to_dicts(values: list[list[object]]) -> list[dict[str, object]]:
    if not values:
        return []
    headers = [normalize_text(x) for x in values[0]]
    rows: list[dict[str, object]] = []
    for idx, row in enumerate(values[1:], start=2):
        padded = list(row) + [""] * max(0, len(headers) - len(row))
        item = {headers[i]: padded[i] for i in range(len(headers)) if headers[i]}
        item["_row_number"] = idx
        rows.append(item)
    return rows


def load_google_sheet_rows(cfg: Config) -> list[dict[str, object]]:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_service_account_file(
        str(Path(cfg.google_service_account_file).expanduser()),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    result = service.spreadsheets().values().get(
        spreadsheetId=cfg.smart_spreadsheet_id,
        range=f"{cfg.smart_sheet_name}!{cfg.smart_range}",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()
    return _rows_to_dicts(result.get("values", []))


def load_csv_rows(cfg: Config) -> list[dict[str, object]]:
    path = Path(cfg.smart_csv_path).expanduser()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, object]] = []
        for idx, row in enumerate(reader, start=2):
            item = dict(row)
            item["_row_number"] = idx
            rows.append(item)
        return rows


def load_rows(cfg: Config) -> list[dict[str, object]]:
    return load_google_sheet_rows(cfg) if cfg.smart_source == "sheets" else load_csv_rows(cfg)


def _meta(row: dict[str, object]) -> dict:
    raw = row.get("meta_json") or row.get("meta") or ""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(str(raw))
    except (ValueError, TypeError):
        return {}


def _latest_deduped_rows(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    # During v5.x the same event could be reprocessed while JDBC was being fixed.
    # event_uuid is a safer cross-attempt identity than event_hash.
    latest: dict[str, dict[str, object]] = {}
    no_identity: list[dict[str, object]] = []
    for row in rows:
        event_uuid = normalize_text(row.get("event_uuid"))
        event_hash = normalize_text(row.get("event_hash"))
        key = event_uuid or event_hash
        if not key:
            no_identity.append(row)
            continue
        latest[key] = row
    return list(latest.values()) + no_identity


def demand_events_from_rows(rows: Iterable[dict[str, object]], cfg: Config) -> list[DemandEvent]:
    accepted_types = set(cfg.demand_events)
    accepted_statuses = set(cfg.accepted_statuses)
    results: list[DemandEvent] = []
    for row in _latest_deduped_rows(rows):
        event_type = normalize_text(row.get("tipo_evento_nombre") or row.get("tipo_evento")).upper()
        status = normalize_text(row.get("status")).upper()
        if event_type not in accepted_types:
            continue
        if accepted_statuses and status not in accepted_statuses:
            continue
        meta = _meta(row)
        sku = normalize_sku(
            row.get("sku_producto") or row.get("sku") or meta.get("sku_producto") or meta.get("sku")
        )
        explicit_size = normalize_size(
            row.get("talla") or row.get("size_norm") or row.get("size")
            or meta.get("talla") or meta.get("size_norm") or meta.get("size")
        )
        _, inferred_size = parse_legacy_sku_size(sku)
        requested_size = explicit_size or inferred_size
        size_source = "EXPLICIT" if explicit_size else ("LEGACY_SKU_SUFFIX" if inferred_size else "MISSING")
        phone = normalize_text(row.get("telefono_e164") or row.get("telefono") or meta.get("telefono"))
        results.append(DemandEvent(
            event_uuid=normalize_text(row.get("event_uuid")),
            event_hash=normalize_text(row.get("event_hash")),
            fecha_evento=_google_serial_to_iso(row.get("fecha_evento")),
            client_uuid=normalize_text(row.get("client_uuid")),
            phone=phone if cfg.include_phone else "",
            event_type=event_type,
            detail=normalize_text(row.get("detalle_evento")),
            smart_sku=sku,
            explicit_size=explicit_size,
            requested_size=requested_size,
            size_source=size_source,
            channel=normalize_text(row.get("canal") or meta.get("canal")),
            source_status=status,
            pg_evento_id=normalize_text(row.get("pg_evento_id")),
            raw_row_number=int(row.get("_row_number") or 0),
        ))
    return results
