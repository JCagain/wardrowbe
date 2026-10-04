"""Append/update/disable rows in the human-edited docs/specs/vocabulary.md tables.

The markdown is the editing face and the compile source: every runtime
vocabulary write lands here *and* in the JSON at the same position, or
compile_vocabulary --check goes red. Positions follow the spec's rules —
types and styles insert at the pinyin slot (catch-alls last), colors insert
into the gradient (lightness high → low; neutral/metallic keep table order
so new rows append).
"""
from __future__ import annotations

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


def entry_sort_key(kind: str, value: str, label: str, family: str | None, hex_color: str | None) -> tuple:
    """Where an entry sits in its table (see the module docstring for rules)."""
    if kind == "styles":
        return (pinyin_sort_key(label),)
    if kind == "types":
        catchall = value in CATCHALL_SLUGS or label.startswith("其他")
        return (catchall, pinyin_sort_key(label))
    if family in TABLE_ORDER_FAMILIES:
        return (1, 0.0)  # table order kept: new rows append at the end
    return (0, -_luminance(hex_color or "#000000"))


def _insert_key(cells: list[str], kind: str, family: str | None) -> tuple:
    value, label = cells[0], cells[1]
    hex_color = None
    if kind == "colors" and len(cells) > 2:
        raw = cells[2].strip("`").split()[0]
        hex_color = raw if raw.startswith("#") else None
    return entry_sort_key(kind, value, label, family, hex_color)


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
        key = entry_sort_key(kind, value, label, family, entry.get("hex"))
        insert_at = end
        for j in range(start, end):
            if _is_data_row(lines[j]) and _insert_key(_cells(lines[j]), kind, family) > key:
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
