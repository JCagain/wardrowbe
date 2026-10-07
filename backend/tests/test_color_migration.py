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
    # A live-only color must be DROPPED under the frozen set: without this the
    # test stays green if `valid` is silently ignored ("red"/"blue" behave
    # identically under the live set and the frozen one).
    assert migrate_legacy_colors("navy", [], valid={"red", "blue"}) == ([], [])


def test_frozen_valid_set_is_honored_over_the_live_vocabulary():
    # Pin for the same invariant as a named case: `valid` must not be
    # silently hard-wired to the live set. "navy" is live-valid, so only a
    # frozen set drops it; "red" must still land under the frozen set.
    assert migrate_legacy_colors("navy", [], valid={"red", "blue"}) == ([], [])
    assert migrate_legacy_colors("red", [], valid={"red", "blue"}) == (["red"], [])


def test_migration_load_chain_never_imports_the_live_vocabulary(monkeypatch):
    """alembic loads every revision script at startup, and the vocabulary JSON
    is runtime-mutable (soft-vocab). A corrupted or missing vocabulary file
    must not take the migration chain down: the data migration runs off its
    own frozen snapshots (see e7f8a9b0c1d2_personal_wardrobe_fields) and the
    shared helpers must never pull the live vocabulary in at import time.
    """
    import importlib
    import importlib.util
    import sys
    from pathlib import Path

    for name in ("app.utils.garment_vocabulary", "app.utils.color_migration"):
        monkeypatch.delitem(sys.modules, name, raising=False)

    module = importlib.import_module("app.utils.color_migration")
    assert "app.utils.garment_vocabulary" not in sys.modules

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "e7f8a9b0c1d2_personal_wardrobe_fields.py"
    )
    spec = importlib.util.spec_from_file_location(
        "e7f8a9b0c1d2_load_chain_probe", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert "app.utils.garment_vocabulary" not in sys.modules

    # The frozen-snapshot entry points still work with no live vocabulary around.
    assert module.migrate_legacy_colors("navy", [], valid={"red", "blue"}) == ([], [])
    assert module.body_part_case_sql("type", mapping={"shirt": "tops"}) == (
        "CASE WHEN type = 'shirt' THEN 'tops' ELSE NULL END"
    )
