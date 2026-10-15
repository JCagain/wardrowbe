"""Append/update/disable rows in the human-edited docs/specs/vocabulary.md tables.

The markdown is the editing face and the compile source: every runtime
vocabulary write lands here *and* in the JSON at the same position, or
compile_vocabulary --check goes red. Positions follow the spec's rules —
types and styles insert at the pinyin slot (catch-alls last); colors keep the
family's 正X anchor first, then follow the gradient (lightness high → low;
orange-yellow by hue yellow → orange; neutral/metallic keep table order so
new rows append).
"""
from __future__ import annotations

import colorsys
from pathlib import Path

from app.utils.pinyin import pinyin_sort_key

# Sibling of the backend tree: <repo>/docs on the host, /docs in the container
# (compose mounts ./docs:/docs — same layout the compiler resolves).
BACKEND_ROOT = Path(__file__).resolve().parents[2]
MD_PATH = BACKEND_ROOT.parent / "docs" / "specs" / "vocabulary.md"

SECTION_TITLES = {
    "styles": "## 五、风格",
    "types": "## 一、类型",
    "colors": "## 二、颜色",
}
CATCHALL_SLUGS = {"top", "bottom", "accessories", "jewelry"}
TABLE_ORDER_FAMILIES = {"neutral", "metallic"}
DISABLED_MARK = "已停用"
ANCHOR_PREFIX = "正"


def _is_data_row(line: str) -> bool:
    return line.startswith("|") and "slug" not in line and not line.startswith("|--")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _row_line(cells: list[str]) -> str:
    # Human format: "| a | b | |" — an empty cell is a single space.
    return "|" + "|".join(f" {c} " if c else " " for c in cells) + "|"


def _find_table_region(lines: list[str], kind: str, family: str | None) -> tuple[int, int]:
    """Return [start, end) of the target table's data rows."""
    title = SECTION_TITLES[kind]
    start = next(i for i, ln in enumerate(lines) if ln.startswith(title))
    end = len(lines)
    if kind in ("types", "colors"):
        if family is None:
            raise ValueError(f"family is required for {kind} rows")
        heading = f"`{family}`"
        start = next(
            i
            for i, ln in enumerate(lines[start:], start)
            if ln.startswith("### ") and heading in ln
        )
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("### ") or lines[i].startswith("## "):
            end = i
            break
    return start, end


def _row_index(lines: list[str], kind: str, value: str, family: str | None) -> int:
    start, end = _find_table_region(lines, kind, family)
    for i in range(start, end):
        if _is_data_row(lines[i]) and _cells(lines[i])[0] == value:
            return i
    raise ValueError(f"no row for {value!r} in {kind}/{family}")


def _luminance(hex_color: str) -> float:
    """Relative luminance (linear approximation is fine for ordering)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _hue_key(hex_color: str) -> float:
    """Yellow → orange: larger hue first. Reds past 0° wrap negative so they sort last."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    hue, _s, _v = colorsys.rgb_to_hsv(r, g, b)
    deg = hue * 360
    if deg > 180:
        deg -= 360
    return -deg


def _gradient_key(family: str | None, hex_color: str | None) -> float:
    hex_color = hex_color or "#000000"
    if family == "orange-yellow":
        return _hue_key(hex_color)
    return -_luminance(hex_color)


def color_insert_index(
    rows: list[tuple[str, str, str | None]], new: tuple[str, str, str], family: str
) -> int:
    """Where a new color row goes inside its family (vocabulary.md 二、颜色 header):
    neutral/metallic append; the family's single 正X anchor stays first; the rest
    follow the gradient (lightness high → low; orange-yellow by hue yellow → orange)."""
    if family in TABLE_ORDER_FAMILIES:
        return len(rows)
    has_anchor = bool(rows) and rows[0][1].startswith(ANCHOR_PREFIX)
    if not has_anchor and new[1].startswith(ANCHOR_PREFIX):
        return 0
    start = 1 if has_anchor else 0
    key = _gradient_key(family, new[2])
    for i in range(start, len(rows)):
        if _gradient_key(family, rows[i][2]) > key:
            return i
    return len(rows)


def entry_sort_key(kind: str, value: str, label: str) -> tuple:
    """Where a styles/types entry sits in its table (colors use color_insert_index)."""
    if kind == "colors":
        raise ValueError("entry_sort_key does not order colors; use color_insert_index")
    if kind == "styles":
        return (pinyin_sort_key(label),)
    catchall = value in CATCHALL_SLUGS or label.startswith("其他")
    return (catchall, pinyin_sort_key(label))


def _cell_hex(cells: list[str]) -> str | None:
    if len(cells) > 2 and cells[2].strip("`").split():
        raw = cells[2].strip("`").split()[0]
        return raw if raw.startswith("#") else None
    return None


def _insert_key(cells: list[str], kind: str, family: str | None) -> tuple:
    return entry_sort_key(kind, cells[0], cells[1])


def sync_row(md_path: Path, kind: str, entry: dict, family: str | None = None) -> None:
    """Insert or relabel one row; notes and hex cells survive relabels."""
    lines = md_path.read_text(encoding="utf-8").splitlines()
    value, label = entry["value"], entry["label"]
    try:
        i = _row_index(lines, kind, value, family)
    except ValueError:
        i = None
    if i is not None:
        cells = _cells(lines[i])
        cells[1] = label
        lines[i] = _row_line(cells)
    else:
        if kind == "colors":
            row = _row_line([value, label, f"`{entry['hex'].lower()}`"])
        else:
            row = _row_line([value, label, ""])
        start, end = _find_table_region(lines, kind, family)
        data_rows = [j for j in range(start, end) if _is_data_row(lines[j])]
        insert_at = end
        if kind == "colors":
            existing = []
            for j in data_rows:
                cells = _cells(lines[j])
                existing.append((cells[0], cells[1], _cell_hex(cells)))
            idx = color_insert_index(existing, (value, label, entry["hex"]), family or "")
            if idx < len(data_rows):
                insert_at = data_rows[idx]
        else:
            key = entry_sort_key(kind, value, label)
            for j in data_rows:
                if _insert_key(_cells(lines[j]), kind, family) > key:
                    insert_at = j
                    break
        lines.insert(insert_at, row)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _set_disabled_mark(md_path: Path, kind: str, value: str, family: str | None, on: bool) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    i = _row_index(lines, kind, value, family)
    cells = _cells(lines[i])
    last = cells[-1]
    if on and DISABLED_MARK not in last:
        cells[-1] = f"{last} {DISABLED_MARK}".strip()
    elif not on and DISABLED_MARK in last:
        cells[-1] = last.replace(DISABLED_MARK, "").strip()
    lines[i] = _row_line(cells)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def mark_disabled(md_path: Path, kind: str, value: str, family: str | None = None) -> None:
    _set_disabled_mark(md_path, kind, value, family, on=True)


def unmark_disabled(md_path: Path, kind: str, value: str, family: str | None = None) -> None:
    _set_disabled_mark(md_path, kind, value, family, on=False)


def ensure_family_section(md_path: Path, family_value: str, family_label: str) -> None:
    """Append a new color-family section at the end of the colors region."""
    lines = md_path.read_text(encoding="utf-8").splitlines()
    title = SECTION_TITLES["colors"]
    start = next(i for i, ln in enumerate(lines) if ln.startswith(title))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    if any(ln.startswith("### ") and f"`{family_value}`" in ln for ln in lines[start:end]):
        return
    block = [
        "",
        f"### {family_label} `{family_value}`",
        "",
        "| slug | 中文名 | hex |",
        "|------|--------|------|",
    ]
    lines[end:end] = block
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
