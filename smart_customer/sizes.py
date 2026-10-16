from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any, Iterable

_SIZE_TOKEN = re.compile(r"(?<!\d)(1[8-9]|2\d|3[0-5])(?:[.,](0|5))?(?!\d)")
_SKU_SIZE = re.compile(r"-(1[8-9]|2\d|3[0-5])(?:[.,](0|5))?$")

def normalize_size(value: Any) -> str | None:
    raw = str(value or "").strip().replace(",", ".")
    if not raw:
        return None
    try: number = float(raw)
    except ValueError: return None
    if not 18 <= number <= 35: return None
    doubled = round(number * 2)
    if abs(number * 2 - doubled) > 1e-8: return None
    return str(doubled // 2) if doubled % 2 == 0 else f"{doubled / 2:.1f}"

def extract_size(variant_title: Any, sku: Any = None) -> str | None:
    title = str(variant_title or "").strip()
    direct = normalize_size(title)
    if direct: return direct
    candidates=[]
    for m in _SIZE_TOKEN.finditer(title):
        integer, decimal = m.group(1), m.group(2)
        v = integer if decimal in (None,"0") else f"{integer}.5"
        n = normalize_size(v)
        if n: candidates.append(n)
    unique=list(dict.fromkeys(candidates))
    if len(unique)==1: return unique[0]
    m=_SKU_SIZE.search(str(sku or "").strip())
    if m:
        integer, decimal=m.group(1),m.group(2)
        return normalize_size(integer if decimal in (None,"0") else f"{integer}.5")
    return None

def normalize_brand(value: Any) -> str | None:
    raw=" ".join(str(value or "").strip().split())
    return raw.upper() if raw else None

@dataclass(frozen=True)
class SizeProfile:
    preferred_size: str | None
    last_purchase_size: str | None
    observation_count: int
    unique_sizes: int
    confidence: float | None
    confidence_band: str
    size_counts: dict[str,int]
    first_observed_at: datetime | None
    last_observed_at: datetime | None

def _when(value: Any) -> datetime | None:
    if isinstance(value,datetime): return value
    if not value: return None
    try: return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except ValueError: return None

def build_size_profile(rows: Iterable[dict[str,Any]]) -> SizeProfile:
    obs=[]
    for row in rows:
        if bool(row.get("cancelled")): continue
        size=normalize_size(row.get("size")); qty=int(row.get("quantity") or 0)
        if size and qty>0: obs.append((size,qty,_when(row.get("purchased_at"))))
    if not obs:
        return SizeProfile(None,None,0,0,None,"NONE",{},None,None)
    counts=Counter(); latest={}; dated=[]
    for size,qty,when in obs:
        counts[size]+=qty
        if when is not None:
            dated.append((when,size))
            if size not in latest or when>latest[size]: latest[size]=when
    preferred=sorted(counts,key=lambda s:(-counts[s],-(latest.get(s).timestamp() if s in latest else 0),float(s)))[0]
    total=sum(counts.values()); confidence=counts[preferred]/total if total else None
    if total>=3 and confidence is not None and confidence>=0.70: band="HIGH"
    elif total>=2 and confidence is not None and confidence>=0.55: band="MEDIUM"
    else: band="LOW"
    dated.sort(); first=dated[0][0] if dated else None; last=dated[-1][0] if dated else None
    last_size=dated[-1][1] if dated else preferred
    return SizeProfile(preferred,last_size,total,len(counts),round(confidence,4),band,dict(sorted(counts.items(),key=lambda x:float(x[0]))),first,last)
