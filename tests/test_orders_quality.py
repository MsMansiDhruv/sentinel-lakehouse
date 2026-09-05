
from sentinel.quality.orders import ORDER_RULES

EXPECTED_RULES = {
    "valid_order_id",
    "valid_customer_id",
    "valid_product_id",
    "valid_quantity",
    "valid_unit_price",
    "valid_total_amount",
    "valid_status",
    "valid_payment_method",
    "valid_order_timestamp",
    "valid_amount_calculation",
}


def test_all_expected_order_rules_exist():
    assert set(ORDER_RULES) == EXPECTED_RULES


def test_order_rules_are_not_empty():
    assert all(
        isinstance(expression, str) and expression.strip()
        for expression in ORDER_RULES.values()
    )


def test_quantity_requires_positive_value():
    rule = ORDER_RULES["valid_quantity"]

    assert "quantity_clean IS NOT NULL" in rule
    assert "quantity_clean > 0" in rule


def test_price_requires_positive_value():
    rule = ORDER_RULES["valid_unit_price"]

    assert "unit_price_clean IS NOT NULL" in rule
    assert "unit_price_clean > 0" in rule


def test_amount_requires_positive_value():
    rule = ORDER_RULES["valid_total_amount"]

    assert "total_amount_clean IS NOT NULL" in rule
    assert "total_amount_clean > 0" in rule


def test_amount_calculation_uses_clean_columns():
    rule = ORDER_RULES["valid_amount_calculation"]

    assert "total_amount_clean" in rule
    assert "quantity_clean" in rule
    assert "unit_price_clean" in rule