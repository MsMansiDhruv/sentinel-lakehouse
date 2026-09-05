from sentinel.quality.orders import ORDER_RULES


EXPECTED_RULES = {
    "order_id_required",
    "customer_id_required",
    "product_id_required",
    "valid_quantity",
    "valid_unit_price",
    "valid_total_amount",
    "valid_order_status",
    "valid_payment_method",
    "valid_order_timestamp",
    "valid_order_amount",
}


def test_all_expected_order_rules_exist():
    """The production DQ contract must contain exactly the expected rules."""
    assert set(ORDER_RULES) == EXPECTED_RULES


def test_order_rules_are_not_empty():
    """Every DQ rule must contain a usable SQL expression."""
    assert all(
        isinstance(expression, str) and expression.strip()
        for expression in ORDER_RULES.values()
    )


def test_required_business_keys_are_enforced():
    """Core business identifiers must not be null."""
    assert "order_id IS NOT NULL" in ORDER_RULES["order_id_required"]
    assert "customer_id IS NOT NULL" in ORDER_RULES["customer_id_required"]
    assert "product_id IS NOT NULL" in ORDER_RULES["product_id_required"]


def test_quantity_requires_positive_value():
    """An order cannot contain zero or negative quantity."""
    rule = ORDER_RULES["valid_quantity"]

    assert "quantity_clean IS NOT NULL" in rule
    assert "quantity_clean > 0" in rule


def test_price_allows_zero_but_not_negative():
    """Unit price may be zero, but negative prices are invalid."""
    rule = ORDER_RULES["valid_unit_price"]

    assert "unit_price_clean IS NOT NULL" in rule
    assert "unit_price_clean >= 0" in rule


def test_total_amount_allows_zero_but_not_negative():
    """Order amount may be zero, but negative amounts are invalid."""
    rule = ORDER_RULES["valid_total_amount"]

    assert "total_amount_clean IS NOT NULL" in rule
    assert "total_amount_clean >= 0" in rule


def test_order_amount_rule_uses_clean_numeric_columns():
    """Amount reconciliation must operate on typed numeric columns."""
    rule = ORDER_RULES["valid_order_amount"]

    assert "total_amount_clean" in rule
    assert "quantity_clean" in rule
    assert "unit_price_clean" in rule


def test_order_status_rule_exists():
    """Order status must be validated against the business contract."""
    rule = ORDER_RULES["valid_order_status"]

    assert "order_status" in rule


def test_payment_method_is_validated():
    """Payment method must participate in the DQ contract."""
    rule = ORDER_RULES["valid_payment_method"]

    assert "payment_method" in rule


def test_order_timestamp_is_validated():
    """Typed order timestamp must participate in the DQ contract."""
    rule = ORDER_RULES["valid_order_timestamp"]

    assert "order_timestamp_clean" in rule