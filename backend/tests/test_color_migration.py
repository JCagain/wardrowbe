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
        ("unknown-slug", ["weird"], ["unknown-slug"], ["weird"]),
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
