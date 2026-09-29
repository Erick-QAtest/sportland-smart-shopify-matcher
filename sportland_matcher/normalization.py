from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

LEGACY_SKU_SIZE_RE = re.compile(r"^(?P<base>.+?)(?P<sep>[-/])(?P<size>\d+(?:[.,]\d+)?)$")


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def normalize_sku(value: object) -> str:
    return re.sub(r"\s+", "", normalize_text(value)).upper()


def normalize_size(value: object) -> str:
    raw = normalize_text(value)
    if not raw:
        return ""
    cleaned = raw.replace(",", ".").strip()
    cleaned = re.sub(r"\s*(MX|CM|MEX|MEXICO|MÉXICO)$", "", cleaned, flags=re.IGNORECASE).strip()
    try:
        n = Decimal(cleaned)
    except InvalidOperation:
        return cleaned.casefold()
    normalized = format(n.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def parse_legacy_sku_size(sku: object) -> tuple[str, str]:
    # Conservative parser for historical forms such as 2033-27 / 1878L-23.5.
    value = normalize_sku(sku)
    if not value:
        return "", ""
    m = LEGACY_SKU_SIZE_RE.match(value)
    if not m:
        return value, ""
    size = normalize_size(m.group("size"))
    try:
        n = Decimal(size)
    except InvalidOperation:
        return value, ""
    # Avoid interpreting sequence suffixes such as 951-1 as shoe size 1.
    if n < 10 or n > 50:
        return value, ""
    return normalize_sku(m.group("base")), size


def strip_known_size_suffix(sku: object, size: object) -> str:
    sku_n = normalize_sku(sku)
    size_n = normalize_size(size)
    if not sku_n or not size_n:
        return sku_n
    candidates = {
        f"-{size_n}".upper(),
        f"/{size_n}".upper(),
        f"-{size_n.replace('.', ',')}".upper(),
        f"/{size_n.replace('.', ',')}".upper(),
    }
    for suffix in candidates:
        if sku_n.endswith(suffix):
            return sku_n[:-len(suffix)]
    return sku_n
