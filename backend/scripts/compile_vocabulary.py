"""Compile docs/specs/vocabulary.md into backend/app/data/garment_vocabulary.json.

vocabulary.md is the human-edited source; the JSON is the runtime source of truth.
Run with --check to fail when the committed JSON is stale, --print to emit JSON on stdout.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Anchor to the backend tree, which sits at the same place in a source checkout
# and in the container (mounted at /app). vocabulary.md lives beside the backend
# tree — <repo>/docs on the host, /docs in the container (compose mounts
# ./docs:/docs) — so MD_PATH keeps the "sibling of the backend root" anchor.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
MD_PATH = BACKEND_ROOT.parent / "docs" / "specs" / "vocabulary.md"
JSON_PATH = BACKEND_ROOT / "app" / "data" / "garment_vocabulary.json"

MATERIALS = [
    "cotton", "denim", "leather", "wool", "polyester", "silk", "linen", "knit",
    "fleece", "suede", "velvet", "nylon", "canvas", "down", "shearling",
]
FORMALITY = [
    "very-casual", "casual", "smart-casual", "business-casual", "formal", "very-formal",
]

# value: (role, wash_interval) — 48 seed types. Slugs surviving from the v1 JSON keep
# their v1 role/wash_interval verbatim (the scorer/slot semantics stay unchanged);
# genuinely new slugs take these seed defaults. Runtime-added types fall back to
# FALLBACK_META (Task 11 adds types through the API, not through this script).
SEED_TYPE_META = {
    "tank-top": ("base_top", 1), "shirt": ("base_top", 2), "vest": ("mid_layer", 5),
    "sweater": ("base_top", 5), "bandeau": ("base_top", 1), "polo": ("base_top", 2),
    "top": ("base_top", 2), "t-shirt": ("base_top", 1), "hoodie": ("outer_layer", 4),
    "skirt": ("bottom", 3), "pants": ("bottom", 4), "shorts": ("bottom", 3),
    "jeans": ("bottom", 6), "bottom": ("bottom", 4), "slacks": ("bottom", 4),
    "sweatpants": ("bottom", 4),
    "jumpskirt": ("full_body", 3), "slip-dress": ("full_body", 2),
    "dress": ("full_body", 2), "suit": ("suit", 5),
    "coat": ("outer_layer", 10), "trench": ("outer_layer", 10),
    "jacket": ("outer_layer", 8), "cardigan": ("mid_layer", 5),
    "blazer": ("outer_layer", 5), "down-jacket": ("outer_layer", 12),
    "heels": ("footwear", 15), "sandals": ("footwear", 15), "shoes": ("footwear", 15),
    "slippers": ("footwear", 15), "socks": ("socks", 1), "boots": ("footwear", 15),
    "sneakers": ("footwear", 15),
    "bag": ("accessory", 20), "tie": ("neckwear", 20), "hat": ("accessory", 20),
    "accessories": ("accessory", 20), "watch": ("accessory", 20),
    "scarf": ("accessory", 10), "glasses": ("accessory", 20), "belt": ("accessory", 20),
    "earrings": ("accessory", 20), "ring": ("accessory", 20),
    "jewelry": ("accessory", 20), "bracelet": ("accessory", 20),
    "bangle": ("accessory", 20), "necklace": ("accessory", 20),
    "brooch": ("accessory", 20),
}
FALLBACK_META = ("accessory", 3)

SEASON_SEED = [("spring", "春"), ("summer", "夏"), ("fall", "秋"),
               ("winter", "冬"), ("all-season", "四季")]

HEX_RE = re.compile(r"`(#[0-9a-fA-F]{6})`")
# Slug must contain at least one alphanumeric so separator cells like "---" never match.
ROW_RE = re.compile(r"^\|\s*([a-z0-9-]*[a-z0-9][a-z0-9-]*)\s*\|")
SEP_CELL_RE = re.compile(r"^:?-+:?$")
# Matches '### label `slug`' and '## 五、风格 `styles`（可随时增行）' — both H2 and H3
# headings that carry a slug, with optional trailing annotation after the slug.
SECTION_RE = re.compile(r"^#{2,3}\s+(.+?)\s+`([a-z0-9-]+)`")


def _row_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator_row(line: str) -> bool:
    """Markdown separator rows ('|---|', '| --- |', '| :--- |') are skipped, not parsed."""
    cells = _row_cells(line)
    return bool(cells) and bool(SEP_CELL_RE.match(cells[0]))


def _data_row(line: str, section: str) -> tuple[str, str]:
    """Return (slug, label) from a table data row; raise ValueError on any malformation."""
    m = ROW_RE.match(line)
    cells = _row_cells(line) if m else []
    if not m or len(cells) < 2 or not cells[1]:
        raise ValueError(f"malformed table row in section '{section}': {line!r}")
    return m.group(1), cells[1]


def _iter_tables(text: str):
    """Yield (section_slug, [row_lines]) for every heading 'label `slug`' block with a table."""
    section = None
    rows: list[str] = []
    for line in text.splitlines():
        m = SECTION_RE.match(line)
        if m:
            if section:
                yield section, rows
            section, rows = m.group(2), []
            continue
        if line.startswith("## "):
            if section:
                yield section, rows
            section, rows = None, []
            continue
        if section and line.startswith("|") and "slug" not in line and not _is_separator_row(line):
            rows.append(line)
    if section:
        yield section, rows


def _section_label(md_text: str, section: str) -> str | None:
    for line in md_text.splitlines():
        m = SECTION_RE.match(line)
        if m and m.group(2) == section:
            return m.group(1)
    return None


DISABLED_MARK = "已停用"


def _disabled_flag(line: str) -> dict:
    """Runtime writes mark retired rows 已停用 in the last cell (摘不删, no delete)."""
    return {"disabled": True} if DISABLED_MARK in line else {}


def _remember(known: dict[str, str], value: str, line: str, section: str) -> None:
    if value in known:
        raise ValueError(
            f"duplicate slug '{value}' in section '{section}': {known[value]!r} and {line!r}"
        )
    known[value] = line


def compile_vocabulary(md_text: str) -> dict:
    body_parts, types, color_families, colors, styles = [], [], [], [], []
    seen_types: dict[str, str] = {}
    seen_colors: dict[str, str] = {}
    seen_styles: dict[str, str] = {}
    for section, rows in _iter_tables(md_text):
        if section in {"dresses", "accessories", "tops", "jewelry", "outerwear",
                       "bottoms", "footwear"}:
            body_parts.append({"value": section, "label": _section_label(md_text, section)})
            for line in rows:
                value, type_label = _data_row(line, section)
                _remember(seen_types, value, line, section)
                role, wash = SEED_TYPE_META.get(value, FALLBACK_META)
                types.append({
                    "value": value, "label": type_label, "body_part": section,
                    "role": role, "wash_interval": wash,
                    **_disabled_flag(line),
                })
        elif section == "styles":
            for line in rows:
                value, style_label = _data_row(line, section)
                _remember(seen_styles, value, line, section)
                styles.append({"value": value, "label": style_label,
                               **_disabled_flag(line)})
        else:
            color_families.append({"value": section, "label": _section_label(md_text, section)})
            for line in rows:
                value, color_label = _data_row(line, section)
                _remember(seen_colors, value, line, section)
                hex_m = HEX_RE.search(line)
                if not hex_m:
                    raise ValueError(f"color row without hex in section '{section}': {line!r}")
                colors.append({
                    "value": value, "label": color_label,
                    "family": section, "hex": hex_m.group(1).lower(),
                    **_disabled_flag(line),
                })

    return {
        "body_parts": body_parts,
        "types": types,
        "colors": {"families": color_families, "values": colors},
        "seasons": [{"value": v, "label": lab} for v, lab in SEASON_SEED],
        "styles": styles,
        "materials": MATERIALS,
        "formality": FORMALITY,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--print", dest="print_only", action="store_true")
    args = parser.parse_args()

    data = compile_vocabulary(MD_PATH.read_text(encoding="utf-8"))
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"

    if args.print_only:
        sys.stdout.write(rendered)
        return 0
    if args.check:
        current = JSON_PATH.read_text(encoding="utf-8") if JSON_PATH.exists() else ""
        if current != rendered:
            print("garment_vocabulary.json is out of date with docs/specs/vocabulary.md; "
                  "run `python scripts/compile_vocabulary.py`.", file=sys.stderr)
            return 1
        print("vocabulary-compile: OK")
        return 0
    JSON_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {JSON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
