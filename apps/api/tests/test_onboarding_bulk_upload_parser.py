from decimal import Decimal

import pandas as pd

from routers.onboarding import validate_bulk_frame


def test_bottom_reel_bulk_rows_default_blank_weight_to_zero():
    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "bottom_size_mm": 65,
                "total_individual_rolls": 49,
                "total_weight_kg": None,
            }
        ]
    )

    rows, errors = validate_bulk_frame(frame, "bottom_reel", "Raw Materials", row_offset=20)

    assert errors == []
    assert rows == [
        {
            "row_type": "ACTUAL",
            "bottom_size_mm": 65,
            "total_individual_rolls": 49,
            "total_weight_kg": Decimal("0"),
        }
    ]


def test_plastic_stock_bulk_rows_expand_comma_separated_cup_sizes():
    frame = pd.DataFrame(
        [
            {
                "row_type": "ACTUAL",
                "plastic_size_type": "3.5*18",
                "used_for_cup_size_ml": "55,65",
                "total_boras_sacks": 4,
                "weight_per_bora_kg": 30,
                "price_per_kg_rs": 180,
            }
        ]
    )

    rows, errors = validate_bulk_frame(frame, "plastic_stock", "Raw Materials", row_offset=64)

    assert errors == []
    assert [row["used_for_cup_size_ml"] for row in rows] == [55, 65]
    assert {row["plastic_size_type"] for row in rows} == {"3.5*18"}
