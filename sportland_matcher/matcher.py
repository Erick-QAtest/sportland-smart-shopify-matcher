from __future__ import annotations

from dataclasses import dataclass, asdict
from collections import defaultdict
import json

from .normalization import normalize_size, normalize_sku, parse_legacy_sku_size, strip_known_size_suffix
from .shopify_source import ShopifyVariant
from .smart_source import DemandEvent


@dataclass
class MatchResult:
    event_uuid: str
    event_hash: str
    fecha_evento: str
    client_uuid: str
    event_type: str
    smart_sku: str
    requested_size: str
    size_source: str
    match_status: str
    match_confidence: str
    reason: str
    product_id: str = ""
    product_legacy_id: str = ""
    product_handle: str = ""
    product_title: str = ""
    variant_id: str = ""
    variant_legacy_id: str = ""
    shopify_sku: str = ""
    shopify_size: str = ""
    inventory_total: int | None = None
    available_locations: str = ""
    price: str = ""
    compare_at_price: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DemandSupplyMatcher:
    def __init__(self, variants: list[ShopifyVariant]):
        self.variants = variants
        self.by_sku: dict[str, list[ShopifyVariant]] = defaultdict(list)
        self.by_product: dict[str, list[ShopifyVariant]] = defaultdict(list)
        self.by_base_sku: dict[str, list[ShopifyVariant]] = defaultdict(list)
        for variant in variants:
            sku = normalize_sku(variant.sku)
            if sku:
                self.by_sku[sku].append(variant)
            if variant.product_id:
                self.by_product[variant.product_id].append(variant)
            base = strip_known_size_suffix(variant.sku, variant.size)
            if base:
                self.by_base_sku[base].append(variant)

    @staticmethod
    def _locations_json(variant: ShopifyVariant) -> str:
        rows = [
            {"location_id": x.location_id, "location_name": x.location_name, "available": x.available}
            for x in variant.locations if x.available != 0
        ]
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))

    def _result(self, event: DemandEvent, *, status: str, confidence: str, reason: str,
                variant: ShopifyVariant | None = None) -> MatchResult:
        kwargs = {}
        if variant:
            kwargs = dict(
                product_id=variant.product_id,
                product_legacy_id=variant.product_legacy_id,
                product_handle=variant.product_handle,
                product_title=variant.product_title,
                variant_id=variant.variant_id,
                variant_legacy_id=variant.variant_legacy_id,
                shopify_sku=variant.sku,
                shopify_size=variant.size,
                inventory_total=variant.inventory_total,
                available_locations=self._locations_json(variant),
                price=variant.price,
                compare_at_price=variant.compare_at_price,
            )
        return MatchResult(
            event_uuid=event.event_uuid,
            event_hash=event.event_hash,
            fecha_evento=event.fecha_evento,
            client_uuid=event.client_uuid,
            event_type=event.event_type,
            smart_sku=event.smart_sku,
            requested_size=event.requested_size,
            size_source=event.size_source,
            match_status=status,
            match_confidence=confidence,
            reason=reason,
            **kwargs,
        )

    def match(self, event: DemandEvent) -> MatchResult:
        sku = normalize_sku(event.smart_sku)
        requested_size = normalize_size(event.requested_size)

        exact = self.by_sku.get(sku, []) if sku else []
        if len(exact) == 1:
            variant = exact[0]
            if requested_size and variant.size and requested_size != normalize_size(variant.size):
                siblings = self.by_product.get(variant.product_id, [])
                same_size = [x for x in siblings if normalize_size(x.size) == requested_size]
                if len(same_size) == 1:
                    variant = same_size[0]
                    status = "MATCH_AVAILABLE" if variant.inventory_total > 0 else "MATCH_OUT_OF_STOCK"
                    return self._result(
                        event, status=status, confidence="HIGH",
                        reason="SKU identificó el producto; talla explícita resolvió la variante hermana.",
                        variant=variant,
                    )
                return self._result(
                    event, status="SIZE_CONFLICT", confidence="LOW",
                    reason="El SKU coincide, pero la talla pedida contradice la variante Shopify.",
                    variant=variant,
                )
            status = "MATCH_AVAILABLE" if variant.inventory_total > 0 else "MATCH_OUT_OF_STOCK"
            return self._result(
                event, status=status, confidence="EXACT",
                reason="Coincidencia exacta por SKU de variante.", variant=variant,
            )
        if len(exact) > 1:
            return self._result(
                event, status="AMBIGUOUS_MATCH", confidence="LOW",
                reason="Shopify contiene más de una variante con el mismo SKU.",
            )

        base_sku, legacy_size = parse_legacy_sku_size(sku)
        target_size = requested_size or legacy_size
        if base_sku and target_size:
            candidates = self.by_base_sku.get(base_sku, [])
            same_size = [x for x in candidates if normalize_size(x.size) == target_size]
            if len(same_size) == 1:
                variant = same_size[0]
                status = "MATCH_AVAILABLE" if variant.inventory_total > 0 else "MATCH_OUT_OF_STOCK"
                return self._result(
                    event, status=status, confidence="HIGH",
                    reason="Coincidencia por SKU base + talla normalizada (compatibilidad histórica).",
                    variant=variant,
                )
            if len(same_size) > 1:
                return self._result(
                    event, status="AMBIGUOUS_MATCH", confidence="LOW",
                    reason="SKU base + talla devuelve múltiples variantes.",
                )

        if not sku:
            if target_size:
                return self._result(
                    event, status="NEEDS_PRODUCT_RESOLUTION", confidence="NONE",
                    reason="Hay talla/intención, pero falta una identidad segura del producto.",
                )
            return self._result(
                event, status="NEEDS_PRODUCT_AND_SIZE_RESOLUTION", confidence="NONE",
                reason="El evento no contiene SKU ni talla suficiente para match.",
            )
        if not target_size:
            return self._result(
                event, status="NEEDS_SIZE_RESOLUTION", confidence="NONE",
                reason="El SKU no coincide exactamente y no hay talla resoluble.",
            )
        return self._result(
            event, status="NO_SHOPIFY_MATCH", confidence="NONE",
            reason="No se encontró variante por SKU exacto ni por SKU base + talla.",
        )

    def match_all(self, events: list[DemandEvent]) -> list[MatchResult]:
        return [self.match(event) for event in events]
