from smart_memory.inventory import is_restock


def test_first_snapshot_is_not_restock():
    assert is_restock(None, 4) is False


def test_zero_to_positive_is_restock():
    assert is_restock(0, 3) is True


def test_negative_to_positive_is_restock():
    assert is_restock(-1, 2) is True


def test_positive_to_positive_is_not_restock():
    assert is_restock(2, 5) is False


def test_zero_to_zero_is_not_restock():
    assert is_restock(0, 0) is False
