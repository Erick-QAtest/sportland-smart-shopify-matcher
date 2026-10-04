from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Iterable

MONTHS_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def norm(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s)
    return s


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    s = str(value).strip().replace("$", "").replace(" ", "")
    if not s:
        return None
    # Spanish decimal comma or US thousands separators.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        right = s.split(",")[-1]
        if len(right) <= 2:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def month_year_from_text(value: Any) -> tuple[int, int] | None:
    s = norm(value)
    if not s:
        return None
    year_match = re.search(r"\b(20\d{2})\b", s)
    if not year_match:
        return None
    year = int(year_match.group(1))
    for name, month in MONTHS_ES.items():
        if re.search(rf"\b{name}\b", s):
            return year, month
    return None


def rows_pad(rows: list[list[Any]], width: int | None = None) -> list[list[Any]]:
    width = width or max((len(r) for r in rows), default=0)
    return [list(r) + [""] * (width - len(r)) for r in rows]


def last_numeric(values: Iterable[Any]) -> float | None:
    out = None
    for v in values:
        n = to_float(v)
        if n is not None:
            out = n
    return out


def today_iso() -> str:
    return date.today().isoformat()
