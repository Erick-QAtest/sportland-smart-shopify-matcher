from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


def _csv_list(value: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in value.split(",") if x.strip())


def _looks_like_placeholder(value: str) -> bool:
    cleaned = value.strip().casefold()
    if not cleaned:
        return False
    markers = (
        "tu_tienda",
        "your_shop",
        "example.myshopify.com",
        "tu_client_id",
        "your_client_id",
        "tu_client_secret",
        "your_client_secret",
        "changeme",
        "replace_me",
    )
    return any(marker in cleaned for marker in markers)


@dataclass(frozen=True)
class Config:
    smart_source: str
    smart_spreadsheet_id: str
    smart_sheet_name: str
    smart_range: str
    google_service_account_file: str
    smart_csv_path: str
    demand_events: tuple[str, ...]
    accepted_statuses: tuple[str, ...]
    include_phone: bool
    shopify_shop: str
    shopify_token: str
    shopify_client_id: str
    shopify_client_secret: str
    shopify_api_version: str
    shopify_variant_page_size: int
    shopify_location_page_size: int
    shopify_max_retries: int
    shopify_timeout_seconds: int
    shopify_size_option_names: tuple[str, ...]
    output_dir: Path

    @property
    def shopify_auth_mode(self) -> str:
        if self.shopify_token:
            return "admin_access_token"
        if self.shopify_client_id and self.shopify_client_secret:
            return "client_credentials"
        return "missing"


def load_config(env_file: str | None = ".env") -> Config:
    if env_file:
        # Process environment wins over .env so temporary overrides remain possible.
        load_dotenv(env_file, override=False)
    return Config(
        smart_source=os.getenv("SMART_SOURCE", "sheets").strip().lower(),
        smart_spreadsheet_id=os.getenv("SMART_SPREADSHEET_ID", "").strip(),
        smart_sheet_name=os.getenv("SMART_SHEET_NAME", "eventos_log").strip(),
        smart_range=os.getenv("SMART_RANGE", "A:V").strip(),
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip(),
        smart_csv_path=os.getenv("SMART_CSV_PATH", "").strip(),
        demand_events=tuple(x.upper() for x in _csv_list(os.getenv(
            "SMART_DEMAND_EVENTS",
            "PREGUNTA_TALLA_PRECIO,PREGUNTA_MODELO_ESPECIFICO,PRUEBA_MULTIPLES_MODELOS",
        ))),
        accepted_statuses=tuple(x.upper() for x in _csv_list(os.getenv("SMART_ACCEPTED_STATUSES", "LOGGED"))),
        include_phone=os.getenv("INCLUDE_PHONE", "false").lower() in {"1", "true", "yes", "y"},
        shopify_shop=os.getenv("SHOPIFY_SHOP", "").strip().replace("https://", "").replace("http://", "").rstrip("/"),
        shopify_token=os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN", "").strip(),
        shopify_client_id=os.getenv("SHOPIFY_CLIENT_ID", "").strip(),
        shopify_client_secret=os.getenv("SHOPIFY_CLIENT_SECRET", "").strip(),
        shopify_api_version=os.getenv("SHOPIFY_API_VERSION", "2026-07").strip(),
        shopify_variant_page_size=min(50, max(1, int(os.getenv("SHOPIFY_VARIANT_PAGE_SIZE", "50")))),
        shopify_location_page_size=min(10, max(1, int(os.getenv("SHOPIFY_LOCATION_PAGE_SIZE", "10")))),
        shopify_max_retries=max(1, int(os.getenv("SHOPIFY_MAX_RETRIES", "6"))),
        shopify_timeout_seconds=max(5, int(os.getenv("SHOPIFY_TIMEOUT_SECONDS", "30"))),
        shopify_size_option_names=tuple(x.casefold() for x in _csv_list(os.getenv(
            "SHOPIFY_SIZE_OPTION_NAMES", "Talla,Size,Tamaño,Tamano,Shoe Size"
        ))),
        output_dir=Path(os.getenv("OUTPUT_DIR", "artifacts")),
    )


def validate_config(cfg: Config, *, require_shopify: bool = True) -> list[str]:
    errors: list[str] = []
    if cfg.smart_source not in {"sheets", "csv"}:
        errors.append("SMART_SOURCE debe ser 'sheets' o 'csv'.")
    if cfg.smart_source == "sheets":
        if not cfg.smart_spreadsheet_id:
            errors.append("Falta SMART_SPREADSHEET_ID.")
        if not cfg.google_service_account_file:
            errors.append("Falta GOOGLE_SERVICE_ACCOUNT_FILE.")
        elif not Path(cfg.google_service_account_file).expanduser().exists():
            errors.append("GOOGLE_SERVICE_ACCOUNT_FILE no existe en la ruta indicada.")
    if cfg.smart_source == "csv":
        if not cfg.smart_csv_path:
            errors.append("Falta SMART_CSV_PATH.")
        elif not Path(cfg.smart_csv_path).expanduser().exists():
            errors.append("SMART_CSV_PATH no existe.")

    if require_shopify:
        if not cfg.shopify_shop:
            errors.append("Falta SHOPIFY_SHOP.")
        elif _looks_like_placeholder(cfg.shopify_shop):
            errors.append("SHOPIFY_SHOP todavía contiene un valor placeholder.")
        elif not cfg.shopify_shop.casefold().endswith(".myshopify.com"):
            errors.append("SHOPIFY_SHOP debe usar el dominio *.myshopify.com de la tienda.")

        if cfg.shopify_token and _looks_like_placeholder(cfg.shopify_token):
            errors.append("SHOPIFY_ADMIN_ACCESS_TOKEN todavía contiene un valor placeholder.")

        if not cfg.shopify_token:
            if not cfg.shopify_client_id:
                errors.append("Falta SHOPIFY_CLIENT_ID (o alternativamente SHOPIFY_ADMIN_ACCESS_TOKEN).")
            elif _looks_like_placeholder(cfg.shopify_client_id):
                errors.append("SHOPIFY_CLIENT_ID todavía contiene un valor placeholder.")
            if not cfg.shopify_client_secret:
                errors.append("Falta SHOPIFY_CLIENT_SECRET (o alternativamente SHOPIFY_ADMIN_ACCESS_TOKEN).")
            elif _looks_like_placeholder(cfg.shopify_client_secret):
                errors.append("SHOPIFY_CLIENT_SECRET todavía contiene un valor placeholder.")

    return errors
