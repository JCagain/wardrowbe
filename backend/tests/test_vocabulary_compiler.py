"""Golden tests: docs/specs/vocabulary.md compiles to the v2 vocabulary JSON."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.compile_vocabulary import compile_vocabulary

ROOT = Path(__file__).resolve().parents[2]
COMPILE = ROOT / "backend" / "scripts" / "compile_vocabulary.py"

EXPECTED_COUNTS = {
    "body_parts": 7,
    "types": 48,
    "color_families": 9,
    "color_values": 48,
    "styles": 11,
    "seasons": 5,
    "materials": 15,
    "formality": 6,
}


def compile_to_dict():
    result = subprocess.run(
        [sys.executable, str(COMPILE), "--print"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_compiler_matches_committed_json():
    result = subprocess.run(
        [sys.executable, str(COMPILE), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_counts_and_shape():
    data = compile_to_dict()
    assert len(data["body_parts"]) == EXPECTED_COUNTS["body_parts"]
    assert len(data["types"]) == EXPECTED_COUNTS["types"]
    assert len(data["colors"]["families"]) == EXPECTED_COUNTS["color_families"]
    assert len(data["colors"]["values"]) == EXPECTED_COUNTS["color_values"]
    assert len(data["styles"]) == EXPECTED_COUNTS["styles"]
    assert len(data["seasons"]) == EXPECTED_COUNTS["seasons"]
    assert len(data["materials"]) == EXPECTED_COUNTS["materials"]
    assert len(data["formality"]) == EXPECTED_COUNTS["formality"]

    part_values = {p["value"] for p in data["body_parts"]}
    assert part_values == {
        "dresses", "accessories", "tops", "jewelry", "outerwear", "bottoms", "footwear"
    }

    for t in data["types"]:
        assert set(t) == {"value", "label", "body_part", "role", "wash_interval"}
        assert t["body_part"] in part_values
        assert t["role"] in {
            "base_top", "bottom", "full_body", "outer_layer", "mid_layer",
            "suit", "footwear", "socks", "neckwear", "accessory",
        }
        assert t["wash_interval"] > 0

    families = {f["value"] for f in data["colors"]["families"]}
    for c in data["colors"]["values"]:
        assert set(c) == {"value", "label", "family", "hex"}
        assert c["family"] in families
        assert c["hex"].startswith("#") and len(c["hex"]) == 7

    for s in data["styles"]:
        assert set(s) == {"value", "label"}
    for s in data["seasons"]:
        assert set(s) == {"value", "label"}


def test_pinyin_order_of_lists():
    from pypinyin import lazy_pinyin

    def pinyin_key(label):
        # Case-insensitive: Latin-initial labels like "Polo衫"/"T恤" sort by
        # letter position (P after M, T after Q), matching the document order.
        return "".join(lazy_pinyin(label)).lower()

    data = compile_to_dict()
    for collection in (data["body_parts"], data["styles"]):
        labels = [e["label"] for e in collection]
        assert labels == sorted(labels, key=pinyin_key), labels

    by_part = {}
    for t in data["types"]:
        by_part.setdefault(t["body_part"], []).append(t["label"])
    for part, labels in by_part.items():
        assert labels == sorted(labels, key=pinyin_key), (part, labels)

    family_labels = [f["label"] for f in data["colors"]["families"]]
    assert family_labels == sorted(family_labels, key=pinyin_key), family_labels


def test_neutral_and_metallic_are_pinyin_sorted_inside():
    from pypinyin import lazy_pinyin

    data = compile_to_dict()
    for family in ("neutral", "metallic"):
        labels = [
            c["label"] for c in data["colors"]["values"] if c["family"] == family
        ]
        assert labels == sorted(labels, key=lambda s: "".join(lazy_pinyin(s)).lower()), labels


def test_chromatic_families_anchor_正x_first():
    data = compile_to_dict()
    anchors = {
        "orange-yellow": "yellow", "pink": "pink", "red": "red", "blue": "blue",
        "green": "green", "purple": "purple", "brown": "brown",
    }
    for family, anchor in anchors.items():
        values = [c["value"] for c in data["colors"]["values"] if c["family"] == family]
        assert values[0] == anchor, (family, values)


TYPE_TABLE = """\
## 一、类型：部位 → 类别

### 上衣 `tops`

| slug | 中文名 | 备注 |
|------|--------|------|
"""

COLOR_TABLE = """\
## 二、颜色：色系 → 具体色

### 黑白灰系 `neutral`

| slug | 中文名 | hex |
|------|--------|------|
"""

STYLE_TABLE = """\
## 五、风格 `styles`（可随时增行）

| slug | 中文名 | 备注 |
|------|--------|------|
"""


def test_malformed_rows_raise_value_error():
    bad_slug = TYPE_TABLE + "| 背心 | 背心 | |\n"
    with pytest.raises(ValueError) as exc:
        compile_vocabulary(bad_slug)
    assert "| 背心 | 背心 | |" in str(exc.value)

    short_row = TYPE_TABLE + "| tank-top |\n"
    with pytest.raises(ValueError) as exc:
        compile_vocabulary(short_row)
    assert "| tank-top |" in str(exc.value)

    empty_label = TYPE_TABLE + "| tank-top |  | |\n"
    with pytest.raises(ValueError) as exc:
        compile_vocabulary(empty_label)
    assert "| tank-top |  | |" in str(exc.value)


def test_duplicate_slugs_raise_value_error():
    for md, lines in (
        (TYPE_TABLE + "| tank-top | 背心 | |\n| tank-top | 背心二 | |\n",
         ["| tank-top | 背心 | |", "| tank-top | 背心二 | |"]),
        (COLOR_TABLE + "| white | 白 | `#f7f7f7` |\n| white | 白二 | `#eeeeee` |\n",
         ["| white | 白 | `#f7f7f7` |", "| white | 白二 | `#eeeeee` |"]),
        (STYLE_TABLE + "| casual | 休闲 | |\n| casual | 休闲二 | |\n",
         ["| casual | 休闲 | |", "| casual | 休闲二 | |"]),
    ):
        with pytest.raises(ValueError) as exc:
            compile_vocabulary(md)
        for line in lines:
            assert line in str(exc.value), (line, exc.value)


def test_spaced_separator_row_is_ignored():
    with_sep = TYPE_TABLE + "| --- |\n| tank-top | 背心 | |\n"
    without = TYPE_TABLE + "| tank-top | 背心 | |\n"
    assert compile_vocabulary(with_sep) == compile_vocabulary(without)
