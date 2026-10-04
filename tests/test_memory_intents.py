from smart_memory.intents import state_from_match


def test_available_mapping():
    assert state_from_match("MATCH_AVAILABLE") == "AVAILABLE"


def test_out_of_stock_mapping():
    assert state_from_match("MATCH_OUT_OF_STOCK") == "WAITING_STOCK"


def test_unresolved_mapping():
    assert state_from_match("NEEDS_PRODUCT_RESOLUTION") == "UNRESOLVED"
    assert state_from_match("NO_SHOPIFY_MATCH") == "UNRESOLVED"
    assert state_from_match("SIZE_CONFLICT") == "UNRESOLVED"
