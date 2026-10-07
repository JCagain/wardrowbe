import json
from functools import lru_cache
from pathlib import Path

VOCABULARY_PATH = Path(__file__).parent.parent / "data" / "garment_vocabulary.json"


@lru_cache(maxsize=8)
def _data_at(mtime_ns: int) -> dict:
    # Keyed on mtime so a soft-vocabulary write is picked up by every
    # process (API + arq worker) at its next access — the file is the sole
    # source of truth and is runtime-mutable (see app.api.vocabulary).
    return json.loads(VOCABULARY_PATH.read_text())


def _data() -> dict:
    return _data_at(VOCABULARY_PATH.stat().st_mtime_ns)


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


def render_tagging_prompt(template: str) -> str:
    data = _data()
    replacements = {
        "<<TYPES>>": ", ".join(t["value"] for t in data["types"]),
        "<<MATERIALS>>": ", ".join(data["materials"]),
        "<<FORMALITY>>": ", ".join(data["formality"]),
        "<<BODY_PARTS>>": ", ".join(p["value"] for p in data["body_parts"]),
        "<<COLORS>>": ", ".join(c["value"] for c in data["colors"]["values"]),
        "<<STYLES>>": ", ".join(s["value"] for s in data["styles"]),
        "<<SEASONS>>": ", ".join(s["value"] for s in data["seasons"]),
    }
    for token, value in replacements.items():
        template = template.replace(token, value)
    return template


def __getattr__(name: str):
    """Derived vocabulary names, computed on access from the current file.

    The old module ran these comprehensions once at import. The vocabulary is
    runtime-mutable, so access must observe writes without a restart.
    """
    data = _data()
    types = data["types"]
    body_parts = data["body_parts"]
    colors = data["colors"]
    if name == "TYPES":
        return tuple(entry["value"] for entry in types)
    if name == "ITEM_ROLE":
        return {entry["value"]: entry["role"] for entry in types}
    if name == "DEFAULT_WASH_INTERVALS":
        return {entry["value"]: entry["wash_interval"] for entry in types}
    if name == "MATERIALS":
        return tuple(data["materials"])
    if name == "FORMALITY":
        # Ordered from least to most formal; the scorer measures distance along this scale.
        return tuple(data["formality"])
    if name == "BODY_PARTS":
        return tuple(body_parts)
    if name == "BODY_PART_BY_TYPE":
        return {t["value"]: t["body_part"] for t in types}
    if name == "TYPES_BY_PART":
        return {
            part["value"]: tuple(
                t["value"] for t in types if t["body_part"] == part["value"]
            )
            for part in body_parts
        }
    if name == "TYPE_LABELS":
        return {t["value"]: t["label"] for t in types}
    if name == "COLOR_FAMILIES":
        return tuple(colors["families"])
    if name == "COLOR_VALUES":
        return tuple(colors["values"])
    if name == "COLOR_VALUE_SET":
        return {c["value"] for c in colors["values"]}
    if name == "STYLE_VALUES":
        return tuple(s["value"] for s in data["styles"])
    if name == "STYLE_LABELS":
        return {s["value"]: s["label"] for s in data["styles"]}
    if name == "SEASON_VALUES":
        return tuple(s["value"] for s in data["seasons"])
    if name == "SEASON_LABELS":
        return {s["value"]: s["label"] for s in data["seasons"]}
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
