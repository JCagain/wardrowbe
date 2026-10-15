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


BROWN_AND_OY = """\
## 二、颜色：色系 → 具体色

### 棕色系 `brown`

| slug | 中文名 | hex |
|------|--------|------|
| brown | 正棕 | `#6d4c41` |
| khaki | 卡其 | `#bfa882` |
| coffee | 咖啡棕 | `#4e342e` |

### 橙黄系 `orange-yellow`

| slug | 中文名 | hex |
|------|--------|------|
| yellow | 正黄 | `#ffd600` |
| lemon | 柠檬黄 | `#f2e600` |
| cream | 米黄 | `#efe3c2` |
| ginger | 姜黄 | `#d29b2e` |
| pumpkin | 南瓜色 | `#f79433` |
| orange | 正橙 | `#ef6c00` |
| tangerine | 脏橘 | `#c26a3e` |

## 三、季节 / 温度
"""


def _family_rows(text: str, family: str) -> list[str]:
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("### ") and f"`{family}`" in ln)
    out = []
    for ln in lines[start + 1:]:
        if ln.startswith("#"):
            break
        if ln.startswith("| ") and not ln.startswith("| slug") and not ln.startswith("|---"):
            out.append(ln.split("|")[1].strip())
    return out


def test_bright_color_never_jumps_ahead_of_the_anchor(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(BROWN_AND_OY, encoding="utf-8")
    # 奶茶 is brighter than 正棕; it must still sit after the anchor, before khaki.
    sync_row(md, "colors", {"value": "milk-tea", "label": "奶茶", "hex": "#e3cfb4"}, family="brown")
    assert _family_rows(md.read_text(encoding="utf-8"), "brown") == ["brown", "milk-tea", "khaki", "coffee"]


def test_orange_yellow_inserts_by_hue_yellow_to_orange(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(BROWN_AND_OY, encoding="utf-8")
    # #ffb300 hue ≈ 42°: between 米黄 (≈44°) and 姜黄 (≈40°).
    sync_row(md, "colors", {"value": "mango", "label": "芒果黄", "hex": "#ffb300"}, family="orange-yellow")
    assert _family_rows(md.read_text(encoding="utf-8"), "orange-yellow") == [
        "yellow", "lemon", "cream", "mango", "ginger", "pumpkin", "orange", "tangerine",
    ]


def test_second_zheng_color_goes_to_the_gradient_not_first(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(BROWN_AND_OY, encoding="utf-8")
    # 正橘 #f28500 hue ≈ 33°: after 姜黄 (≈40°), before 南瓜色 (≈30°).
    sync_row(md, "colors", {"value": "mandarin", "label": "正橘", "hex": "#f28500"}, family="orange-yellow")
    rows = _family_rows(md.read_text(encoding="utf-8"), "orange-yellow")
    assert rows[0] == "yellow"
    assert rows.index("mandarin") == rows.index("pumpkin") - 1


def test_zheng_color_becomes_anchor_of_an_anchorless_family():
    from app.utils.vocabulary_md import color_insert_index

    rows = [("mist", "雾青", "#a0b8b0"), ("deep", "深青", "#204040")]
    assert color_insert_index(rows, ("teal", "正青", "#008080"), "teal") == 0
    assert color_insert_index(rows, ("pale", "浅青", "#d0e8e0"), "teal") == 0  # brightest, no anchor
