from datetime import date

import pytest

from app.utils.season import RECORD_SEASONS, season_for_date


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (1, "winter"), (2, "winter"), (3, "spring"), (4, "spring"), (5, "spring"),
        (6, "summer"), (7, "summer"), (8, "summer"), (9, "summer"),
        (10, "fall"), (11, "fall"), (12, "winter"),
    ],
)
def test_season_for_date_spec_months(month, expected):
    assert season_for_date(date(2026, month, 15)) == expected


def test_record_seasons_are_vocab_slugs_without_all_season():
    assert RECORD_SEASONS == ("spring", "summer", "fall", "winter")
