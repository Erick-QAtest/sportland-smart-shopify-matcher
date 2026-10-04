from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


STOP = {
    "tenis", "para", "de", "la", "el", "los", "las", "un", "una", "y", "en",
    "talla", "precio", "cuanto", "cuesta", "tienes", "hay", "disponible", "stock",
    "quiero", "busco", "necesito", "me", "lo", "por", "favor", "modelo"
}


def _norm(v: Any) -> str:
    s = unicodedata.normalize("NFKD", str(v or "")).encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+", s))


def _tokens(v: str) -> set[str]:
    return {x for x in _norm(v).split() if len(x) >= 2 and x not in STOP}


@dataclass
class Resolution:
    sku: str = ""
    product_title: str = ""
    confidence: float = 0.0
    reason: str = "unresolved"


class CatalogResolver:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.by_sku: dict[str, dict[str, Any]] = {}
        self.by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            sku = str(row.get("sku") or "").strip()
            title = str(row.get("product_title") or row.get("title") or "").strip()
            if sku:
                self.by_sku[sku.lower()] = row
            if title:
                self.by_product[title].append(row)

    @classmethod
    def from_csv(cls, path: str | Path) -> "CatalogResolver":
        p = Path(path)
        if not p.exists():
            return cls([])
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            return cls(list(csv.DictReader(f)))

    def resolve(self, text: str, *, explicit_sku: str = "", product_title: str = "") -> Resolution:
        if explicit_sku:
            row = self.by_sku.get(explicit_sku.strip().lower())
            if row:
                return Resolution(str(row.get("sku") or explicit_sku), str(row.get("product_title") or ""), 1.0, "exact_sku")
            # Preserve an explicitly observed SKU even if the local artifact is stale.
            return Resolution(explicit_sku.strip(), product_title.strip(), 0.95, "explicit_sku_not_in_local_catalog")

        target = product_title.strip() or text.strip()
        if not target or not self.by_product:
            return Resolution()

        tt = _tokens(target)
        nt = _norm(target)
        best: tuple[float, str] = (0.0, "")
        second = 0.0
        for title in self.by_product:
            pt = _tokens(title)
            j = len(tt & pt) / max(1, len(tt | pt))
            seq = SequenceMatcher(None, nt, _norm(title)).ratio()
            containment = 1.0 if _norm(title) in nt or nt in _norm(title) else 0.0
            score = 0.62 * j + 0.28 * seq + 0.10 * containment
            if score > best[0]:
                second = best[0]
                best = (score, title)
            elif score > second:
                second = score

        score, title = best
        if not title or score < 0.50:
            return Resolution(confidence=round(score, 3), reason="catalog_match_below_threshold")
        # Require a margin over runner-up to avoid fabricating identity.
        if score - second < 0.06 and score < 0.78:
            return Resolution(product_title=title, confidence=round(score, 3), reason="ambiguous_catalog_match")

        rows = self.by_product[title]
        # Any variant SKU safely identifies the product; the existing matcher can
        # resolve a requested sibling size inside that product.
        sku = next((str(r.get("sku") or "").strip() for r in rows if str(r.get("sku") or "").strip()), "")
        return Resolution(sku, title, round(score, 3), "fuzzy_product_match")
