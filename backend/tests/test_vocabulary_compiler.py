"""Golden tests: docs/specs/vocabulary.md compiles to the v2 vocabulary JSON."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILE = ROOT / "backend" / "scripts" / "compile_vocabulary.py"
JSON_PATH = ROOT / "backend" / "app" / "data" / "garment_vocabulary.json"

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
