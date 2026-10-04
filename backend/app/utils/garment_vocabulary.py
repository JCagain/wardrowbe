import json
from pathlib import Path

VOCABULARY_PATH = Path(__file__).parent.parent / "data" / "garment_vocabulary.json"
_DATA = json.loads(VOCABULARY_PATH.read_text())

TYPES: tuple[str, ...] = tuple(entry["value"] for entry in _DATA["types"])
ITEM_ROLE: dict[str, str] = {entry["value"]: entry["role"] for entry in _DATA["types"]}
DEFAULT_WASH_INTERVALS: dict[str, int] = {
    entry["value"]: entry["wash_interval"] for entry in _DATA["types"]
}
MATERIALS: tuple[str, ...] = tuple(_DATA["materials"])
# Ordered from least to most formal; the scorer measures distance along this scale.
FORMALITY: tuple[str, ...] = tuple(_DATA["formality"])

BODY_PARTS: tuple[dict, ...] = tuple(_DATA["body_parts"])
BODY_PART_BY_TYPE: dict[str, str] = {t["value"]: t["body_part"] for t in _DATA["types"]}
TYPES_BY_PART: dict[str, tuple[str, ...]] = {
    part["value"]: tuple(
        t["value"] for t in _DATA["types"] if t["body_part"] == part["value"]
    )
    for part in _DATA["body_parts"]
}
TYPE_LABELS: dict[str, str] = {t["value"]: t["label"] for t in _DATA["types"]}
# Types without a seed entry (runtime additions) inherit role/wash from their
# body part. Single source for both the runtime API and the compiler — the
# pre-seeded fallback types in accessories/jewelry keep (accessory, 3).
ROLE_BY_PART: dict[str, str] = {
    "tops": "base_top", "bottoms": "bottom", "dresses": "full_body",
    "outerwear": "outer_layer", "footwear": "footwear",
    "accessories": "accessory", "jewelry": "accessory",
}
WASH_BY_PART: dict[str, int] = {
    "tops": 2, "bottoms": 4, "dresses": 3, "outerwear": 8,
    "footwear": 15, "accessories": 3, "jewelry": 3,
}
COLOR_FAMILIES: tuple[dict, ...] = tuple(_DATA["colors"]["families"])
COLOR_VALUES: tuple[dict, ...] = tuple(_DATA["colors"]["values"])
COLOR_VALUE_SET: set[str] = {c["value"] for c in _DATA["colors"]["values"]}
STYLE_VALUES: tuple[str, ...] = tuple(s["value"] for s in _DATA["styles"])
STYLE_LABELS: dict[str, str] = {s["value"]: s["label"] for s in _DATA["styles"]}
SEASON_VALUES: tuple[str, ...] = tuple(s["value"] for s in _DATA["seasons"])
SEASON_LABELS: dict[str, str] = {s["value"]: s["label"] for s in _DATA["seasons"]}


def render_tagging_prompt(template: str) -> str:
    replacements = {
        "<<TYPES>>": ", ".join(t["value"] for t in _DATA["types"]),
        "<<MATERIALS>>": ", ".join(MATERIALS),
        "<<FORMALITY>>": ", ".join(FORMALITY),
        "<<BODY_PARTS>>": ", ".join(p["value"] for p in _DATA["body_parts"]),
        "<<COLORS>>": ", ".join(c["value"] for c in _DATA["colors"]["values"]),
        "<<STYLES>>": ", ".join(s["value"] for s in _DATA["styles"]),
        "<<SEASONS>>": ", ".join(s["value"] for s in _DATA["seasons"]),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template
