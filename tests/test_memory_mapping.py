from smart_memory.mapping import event_payload


def sample_row():
    return {
        "ts_log": "2026-10-01 00:37:56.078000",
        "event_uuid": "047eb17c-dccd-432a-af85-9424ad7ab8ee",
        "event_hash": "abc123",
        "fecha_evento": "2026-09-30 01:50:09",
        "telefono_e164": "+521234567890",
        "client_uuid": "77c177be-8b1c-4320-9b4c-b3efbb881ef3",
        "tipo_evento_id": "40",
        "tipo_evento_nombre": "COMPRA_TIENDA_FISICA",
        "detalle_evento": "compra tienda física",
        "sku": "2073-28",
        "talla": "28",
        "monto": "949",
        "canal": "tienda_fisica",
        "pct": "",
        "moneda": "MXN",
        "actor": "shopify",
        "device": "api",
        "origen": "shopify_sync",
        "silencio_flag_system": "",
        "meta_json": "{}",
        "status": "LOGGED",
    }


def test_event_hash_becomes_source_row_hash():
    payload = event_payload(sample_row())
    assert payload["source"] == "sportland_smart_v5"
    assert payload["source_row_hash"] == "abc123"


def test_phone_is_private_by_default():
    payload = event_payload(sample_row())
    assert payload["phone_e164"] is None


def test_phone_can_be_enabled_explicitly():
    payload = event_payload(sample_row(), store_phone=True)
    assert payload["phone_e164"] == "+521234567890"


def test_event_contract_is_preserved():
    payload = event_payload(sample_row())
    assert payload["event_type_id"] == 40
    assert payload["event_type_name"] == "COMPRA_TIENDA_FISICA"
    assert payload["sku"] == "2073-28"
    assert payload["size"] == "28"
    assert str(payload["amount"]) == "949"
