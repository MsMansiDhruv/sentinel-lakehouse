ORDER_RULES = {
    "order_id_required":
        "order_id IS NOT NULL",

    "customer_id_required":
        "customer_id IS NOT NULL",

    "product_id_required":
        "product_id IS NOT NULL",

    "valid_quantity":
        """
        quantity_clean IS NOT NULL
        AND quantity_clean > 0
        """,

    "valid_unit_price":
        """
        unit_price_clean IS NOT NULL
        AND unit_price_clean >= 0
        """,

    "valid_total_amount":
        """
        total_amount_clean IS NOT NULL
        AND total_amount_clean >= 0
        """,

    "valid_order_status":
        """
        order_status IN (
            'PLACED',
            'CONFIRMED',
            'SHIPPED',
            'DELIVERED',
            'CANCELLED'
        )
        """,

    "valid_payment_method":
        """
        payment_method IN (
            'UPI',
            'CREDIT_CARD',
            'DEBIT_CARD',
            'NET_BANKING',
            'COD'
        )
        """,

    "valid_order_timestamp":
        """
        order_timestamp_clean IS NOT NULL
        AND order_timestamp_clean <= current_timestamp()
        """,

    "valid_order_amount":
        """
        abs(
            total_amount_clean -
            (quantity_clean * unit_price_clean)
        ) <= 0.01
        """
}