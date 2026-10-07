import pytest

from app.utils.color_migration import body_part_case_sql, migrate_legacy_colors


@pytest.mark.parametrize(
    "primary, colors, expected_primary, expected_secondary",
    [
        (None, None, [], []),
        (None, [], [], []),
        ("red", None, ["red"], []),
        ("red", [], ["red"], []),
        ("red", ["red"], ["red"], []),
        ("red", ["blue", "white"], ["red"], ["blue", "white"]),
        ("burgundy", ["tan"], ["wine"], ["camel"]),
        ("red", ["red", "blue", "blue"], ["red"], ["blue"]),
        ("unknown-slug", ["weird"], [], []),
        ("army-green", ["dark-brown"], ["army"], ["coffee"]),
        ("red", ["blue", "mystery"], ["red"], ["blue"]),
        (" Burgundy ", [], ["wine"], []),
    ],
)
def test_migrate_legacy_colors(primary, colors, expected_primary, expected_secondary):
    assert migrate_legacy_colors(primary, colors) == (expected_primary, expected_secondary)


def test_body_part_case_sql_covers_every_seed_type():
    from app.utils.garment_vocabulary import TYPES

    sql = body_part_case_sql("type")
    for value in TYPES:
        assert f"'{value}'" in sql
    assert sql.strip().startswith("CASE") and sql.strip().endswith("END")


def test_live_vocabulary_colors_are_never_alias_rewritten():
    # "lavender" is a live color *and* a legacy alias for "taro": a direct hit
    # must win, or every re-tag rewrites the user's lavender items to taro.
    assert migrate_legacy_colors("lavender", []) == (["lavender"], [])


def test_alias_keys_that_are_live_colors_round_trip():
    from app.utils.color_migration import LEGACY_COLOR_ALIASES
    from app.utils.garment_vocabulary import COLOR_VALUE_SET

    for key in LEGACY_COLOR_ALIASES:
        if key in COLOR_VALUE_SET:
            assert migrate_legacy_colors(key, []) == ([key], [])


def test_body_part_case_sql_accepts_a_frozen_mapping():
    sql = body_part_case_sql("type", mapping={"shirt": "tops", "jeans": "bottoms"})
    assert "WHEN type = 'shirt' THEN 'tops'" in sql
    assert "WHEN type = 'jeans' THEN 'bottoms'" in sql
    # Nothing outside the snapshot may leak in from the live vocabulary.
    assert "'dress'" not in sql


def test_migrate_legacy_colors_accepts_a_frozen_valid_set():
    assert migrate_legacy_colors("red", ["blue", "chartreuse"], valid={"red", "blue"}) == (
        ["red"],
        ["blue"],
    )
