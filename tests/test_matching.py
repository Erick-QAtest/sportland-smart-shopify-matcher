from pathlib import Path

from sportland_matcher.config import load_config
from sportland_matcher.smart_source import demand_events_from_rows, load_csv_rows
from sportland_matcher.shopify_source import LocationInventory, ShopifyVariant
from sportland_matcher.matcher import DemandSupplyMatcher


def cfg_for_fixture(monkeypatch):
    fixture = Path(__file__).parent / "fixtures" / "smart_events.csv"
    monkeypatch.setenv("SMART_SOURCE", "csv")
    monkeypatch.setenv("SMART_CSV_PATH", str(fixture))
    monkeypatch.setenv(
        "SMART_DEMAND_EVENTS",
        "PREGUNTA_TALLA_PRECIO,PREGUNTA_MODELO_ESPECIFICO,PRUEBA_MULTIPLES_MODELOS",
    )
    monkeypatch.setenv("SMART_ACCEPTED_STATUSES", "LOGGED")
    return load_config(env_file=None)


def _variant(*, sku, size, qty, product="P1", variant="V1"):
    return ShopifyVariant(
        variant_id=variant,
        variant_legacy_id=variant,
        product_id=product,
        product_legacy_id=product,
        product_handle="product",
        product_title="Product",
        product_status="ACTIVE",
        variant_title=size,
        sku=sku,
        size=size,
        inventory_total=qty,
        price="100",
        compare_at_price="",
        inventory_item_id="I1",
        locations=[LocationInventory(location_id="L1", location_name="Store", available=qty)],
    )


def test_smart_filters_and_legacy_size(monkeypatch):
    cfg = cfg_for_fixture(monkeypatch)
    events = demand_events_from_rows(load_csv_rows(cfg), cfg)
    assert len(events) == 3
    abc = next(x for x in events if x.smart_sku == "ABC-27")
    assert abc.requested_size == "27"
    assert abc.size_source == "LEGACY_SKU_SUFFIX"


def test_exact_available(monkeypatch):
    cfg = cfg_for_fixture(monkeypatch)
    events = demand_events_from_rows(load_csv_rows(cfg), cfg)
    event = next(x for x in events if x.smart_sku == "ABC-27")
    result = DemandSupplyMatcher([_variant(sku="ABC-27", size="27", qty=2)]).match(event)
    assert result.match_status == "MATCH_AVAILABLE"
    assert result.match_confidence == "EXACT"
    assert result.inventory_total == 2


def test_exact_out_of_stock(monkeypatch):
    cfg = cfg_for_fixture(monkeypatch)
    events = demand_events_from_rows(load_csv_rows(cfg), cfg)
    event = next(x for x in events if x.smart_sku == "DEF-26")
    result = DemandSupplyMatcher([_variant(sku="DEF-26", size="26", qty=0)]).match(event)
    assert result.match_status == "MATCH_OUT_OF_STOCK"


def test_unresolved_model_without_sku(monkeypatch):
    cfg = cfg_for_fixture(monkeypatch)
    events = demand_events_from_rows(load_csv_rows(cfg), cfg)
    event = next(x for x in events if not x.smart_sku)
    result = DemandSupplyMatcher([]).match(event)
    assert result.match_status == "NEEDS_PRODUCT_AND_SIZE_RESOLUTION"
