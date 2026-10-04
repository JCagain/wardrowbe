"""Write-back of the human-edited docs/specs/vocabulary.md tables.

Runtime vocabulary edits must land in the markdown at the same position the
JSON takes, or compile_vocabulary --check goes red on the next run.
"""
from pathlib import Path

from app.utils.vocabulary_md import mark_disabled, sync_row, unmark_disabled

STYLES = """## 五、风格 `styles`（可随时增行）

| slug | 中文名 | 备注 |
|------|--------|------|
| retro | 复古 | |
| casual | 休闲 | |
"""

TYPES = """## 一、类型：部位 → 类别

### 上衣 `tops`

| slug | 中文名 | 备注 |
|------|--------|------|
| shirt | 衬衫 | |
| top | 其他上衣 | 兜底 |
"""

COLORS = """## 二、颜色：色系 → 具体色

### 棕色系 `brown`

| slug | 中文名 | hex |
|------|--------|------|
| camel | 驼色 | `#c19a6b` |
| coffee | 咖啡 | `#6f4e37` |
"""


def _rows(text: str) -> list[str]:
    return [
        ln
        for ln in text.splitlines()
        if ln.startswith("|") and "slug" not in ln and not ln.startswith("|--")
    ]


def test_sync_row_appends_style_in_pinyin_position(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(STYLES, encoding="utf-8")
    sync_row(md, "styles", {"value": "goth", "label": "哥特"})
    rows = _rows(md.read_text(encoding="utf-8"))
    # pinyin: fugu(复古) < gete(哥特) < xiuxian(休闲)
    assert rows == ["| retro | 复古 | |", "| goth | 哥特 | |", "| casual | 休闲 | |"]


def test_sync_row_puts_new_type_before_the_catchall(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(TYPES, encoding="utf-8")
    sync_row(md, "types", {"value": "tunic", "label": "罩衫"}, family="tops")
    rows = _rows(md.read_text(encoding="utf-8"))
    # pinyin: chen/shan < zhao/shan < 其他上衣 last
    assert rows == ["| shirt | 衬衫 | |", "| tunic | 罩衫 | |", "| top | 其他上衣 | 兜底 |"]


def test_sync_row_inserts_color_by_lightness(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(COLORS, encoding="utf-8")
    # Gradient rule: lightness high → low. #a67b5b sits between camel and coffee.
    sync_row(md, "colors", {"value": "mocha", "label": "摩卡", "hex": "#a67b5b"}, family="brown")
    rows = _rows(md.read_text(encoding="utf-8"))
    assert rows == [
        "| camel | 驼色 | `#c19a6b` |",
        "| mocha | 摩卡 | `#a67b5b` |",
        "| coffee | 咖啡 | `#6f4e37` |",
    ]


def test_sync_row_rewrites_label_and_keeps_the_note(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(STYLES.replace("| retro | 复古 | |", "| retro | 复古 | 老派 |"), encoding="utf-8")
    sync_row(md, "styles", {"value": "retro", "label": "复古风"})
    text = md.read_text(encoding="utf-8")
    assert "| retro | 复古风 | 老派 |" in text
    assert text.count("| retro |") == 1


def test_mark_disabled_flags_the_row(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(STYLES, encoding="utf-8")
    mark_disabled(md, "styles", "retro")
    text = md.read_text(encoding="utf-8")
    assert "| retro | 复古 | 已停用 |" in text


def test_unmark_disabled_clears_the_flag(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(STYLES, encoding="utf-8")
    mark_disabled(md, "styles", "retro")
    unmark_disabled(md, "styles", "retro")
    text = md.read_text(encoding="utf-8")
    assert "| retro | 复古 | |" in text
    assert "已停用" not in text
