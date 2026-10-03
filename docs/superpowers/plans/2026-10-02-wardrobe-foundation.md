# Wardrowbe 底座（词表单源 + schema + 裁剪 + zh-CN）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把个人化改造的底座落地：词表收敛为单一数据源（vocabulary.md → JSON → 前端生成物 + 运行时 API）、衣物表新字段迁移、产品壳摘除（families/notifications/learning/wash 摘、suggest 休眠）、UI 锁 zh-CN。

**Architecture:** `docs/specs/vocabulary.md` 是人工编辑面，编译器产出 `backend/app/data/garment_vocabulary.json`（运行时唯一事实源）；后端 loader 消费 JSON，前端由 `gen-garment-vocabulary.mjs` 生成类型安全投影 + 运行时 `GET /api/v1/vocabulary` 拉取软词表（UI 增改写回 JSON 并同步 vocabulary.md 行，保存即生效）。schema 用一个 Alembic 迁移加 `body_part`/`primary_colors[]`/`secondary_colors[]`/`temp_low`/`temp_high`/`purchase_date_precision`，迁移旧颜色数据后删旧列；`style`/`purchase_price`/`purchase_date`/`is_archived` 复用现有列。裁剪只卸挂载（路由/导航/worker 注册），代码与表结构保留。

**Tech Stack:** FastAPI + SQLAlchemy 2 async + Alembic + PostgreSQL（asyncpg）；Next.js 14 + TanStack Query + next-intl v4 + Vitest 4；pytest（真实 Postgres）；pypinyin（拼音排序）。

**Spec:** `docs/specs/personal-wardrobe-spec.md` + `docs/specs/vocabulary.md`（本计划只覆盖两份 spec 中属于"底座"的部分；整理/记录/浏览统计/AI 关联见后续计划）

## Global Constraints

- UI 语言 **zh-CN**；en 仅作 i18n 键源；i18n 校验（parity）只查 **zh-CN**，其余语言文件冻结不删。
- 词表排序：部位=固定逻辑序（上衣→下装→连衣裙/套装→外套→鞋袜→配饰→首饰）；部位内类别=中文名拼音、**兜底（其他xx）垫底**；色系=固定色序（黑白灰→棕→红→橙黄→绿→蓝→紫→粉→金属）；风格=中文名拼音。色系内部=正X 固定第一+渐变；黑白灰/金属内部保持表序。
- 软词表：类型/颜色/风格支持 UI **添加/改名/停用**（不物理删除）；改动写回 `garment_vocabulary.json` **并同步** `vocabulary.md` 对应表格行；保存即生效（前端运行时拉取）；颜色 hex **必填**；类型只能在现有 7 部位下加类别；材质/正式度闭集不可增改。
- 复用列语义：`style`=风格（值域换新词表）、`purchase_price`=价格、`purchase_date`=购买时间、`is_archived`=状态（False=在役/True=已退役，列表默认隐藏已退役，沿用现有接口默认）、`archive_reason`=退役原因、`archived_at`=退役时间。
- 购买时间精度：**年** 或 **年-月** 两档（不存日）；默认录入年月；可置空。年精度需要一个标记列 `purchase_date_precision`（'year'|'month'），日期本身存每月 1 日。
- 摘不删：产品壳（families/notifications/learning/wash）只摘导航/入口/路由挂载/worker 注册，**代码与表结构保留**；suggest/pairings **休眠**（不进导航，后端路由不动）。
- 词表固定计数（golden 基线）：**7 部位 / 52 类别 / 9 色系 / 48 色 / 11 风格 / 5 季节 / 15 材质 / 6 正式度**（2026-10-03 增补：耳骨夹/发饰/项环/美瞳；中性→无性别，slug `androgynous`→`genderless`）。
- 显示名约定：`subtype` 的 UI 名改为「**备注**」；模型另有 `notes` 列，其 UI 名用「**描述**」（错开，防撞名）。
- 测试命令：后端 `docker compose exec backend python -m pytest tests/<file> -v`；前端 `cd frontend && npm test`；词表 `cd frontend && npm run vocab:gen` / `npm run vocab:check`；i18n `cd frontend && npm run i18n:check`。
- 每步提交用 Conventional Commits，结尾带 `Co-Authored-By: Claude Code <noreply@anthropic.com>`。

## Review Focus

1. **词表编译失真**：vocabulary.md 表格行的边界格式（★ 标记、备注含特殊字符、hex 反引号、缺列）导致编译丢行/错位——Task 1 用真实 vocabulary.md 做 golden 测试，锁死 7/52/48/11/5 计数与排序规则。
2. **颜色迁移映射**：旧 `primary_color`/`colors` 的空值、主辅重叠、旧 slug（burgundy/tan/beige/light-blue）与新词表不一致——Task 5 参数化测试覆盖空/单/多/别名/未知值。
3. **软词表写回双文件漂移**：UI 增改后 JSON 与 vocabulary.md 行不一致、重复 slug、颜色缺 hex、类型选了不存在的部位——Task 11 测试断言两个文件同步且校验 4xx。
4. **i18n 门禁**：裁剪导航/改键后 en 与 zh-CN 键位漂移、冻结语言干扰 parity——Task 8 把 parity 范围收窄到 zh-CN，Task 10 清理键后 `npm run i18n:check` 必须绿。
5. **退役默认隐藏与购买精度往返**：复用 `is_archived` 后列表默认不显退役件、`is_archived=true` 筛选才显；`"2024"` 与 `"2024-03"` 存取往返不变形——Task 6 的 API 测试锁默认可见性与年/年-月 round-trip。

---

### Task 1: 词表编译器（vocabulary.md → JSON）与 v2 数据

**Files:**
- Create: `backend/scripts/compile_vocabulary.py`
- Create: `backend/tests/test_vocabulary_compiler.py`
- Modify: `backend/app/data/garment_vocabulary.json`（编译产出，v2 结构）

**Interfaces:**
- Consumes: `docs/specs/vocabulary.md` 各表格（类型/颜色/风格/季节）
- Produces: `garment_vocabulary.json` v2 结构——`body_parts: [{value,label}]`、`types: [{value,label,body_part,role,wash_interval}]`、`colors: {families: [{value,label}], values: [{value,label,family,hex}]}`、`seasons: [{value,label}]`、`styles: [{value,label}]`、`materials: [str]`、`formality: [str]`。后续 Task 2/3/11 都按此结构读取。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_vocabulary_compiler.py`：

```python
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
        return "".join(lazy_pinyin(label))

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
        assert labels == sorted(labels, key=lambda s: "".join(lazy_pinyin(s))), labels


def test_chromatic_families_anchor_正x_first():
    data = compile_to_dict()
    anchors = {
        "orange-yellow": "yellow", "pink": "pink", "red": "red", "blue": "blue",
        "green": "green", "purple": "purple", "brown": "brown",
    }
    for family, anchor in anchors.items():
        values = [c["value"] for c in data["colors"]["values"] if c["family"] == family]
        assert values[0] == anchor, (family, values)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec backend python -m pytest tests/test_vocabulary_compiler.py -v`
Expected: FAIL——`scripts/compile_vocabulary.py` 不存在（FileNotFoundError / 非零退出）。

- [ ] **Step 3: 实现编译器**

先装依赖（pypinyin，供编译器与后续 Task 11 排序复用）。在 `backend/requirements.txt` 的依赖列表末尾追加一行：

```
pypinyin>=0.51.0
```

创建 `backend/scripts/compile_vocabulary.py`：

```python
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

ROOT = Path(__file__).resolve().parents[2]
MD_PATH = ROOT / "docs" / "specs" / "vocabulary.md"
JSON_PATH = ROOT / "backend" / "app" / "data" / "garment_vocabulary.json"

MATERIALS = [
    "cotton", "denim", "leather", "wool", "polyester", "silk", "linen", "knit",
    "fleece", "suede", "velvet", "nylon", "canvas", "down", "shearling",
]
FORMALITY = [
    "very-casual", "casual", "smart-casual", "business-casual", "formal", "very-formal",
]

# value: (role, wash_interval) — 48 seed types. Runtime-added types fall back to
# FALLBACK_META (Task 11 adds types through the API, not through this script).
SEED_TYPE_META = {
    "tank-top": ("base_top", 1), "shirt": ("base_top", 2), "vest": ("mid_layer", 2),
    "sweater": ("mid_layer", 2), "bandeau": ("base_top", 1), "polo": ("base_top", 2),
    "top": ("base_top", 3), "t-shirt": ("base_top", 1), "hoodie": ("mid_layer", 3),
    "skirt": ("bottom", 3), "pants": ("bottom", 4), "shorts": ("bottom", 3),
    "jeans": ("bottom", 6), "bottom": ("bottom", 4), "slacks": ("bottom", 4),
    "sweatpants": ("bottom", 4),
    "jumpskirt": ("full_body", 3), "slip-dress": ("full_body", 2),
    "dress": ("full_body", 2), "suit": ("suit", 5),
    "coat": ("outer_layer", 10), "trench": ("outer_layer", 10),
    "jacket": ("outer_layer", 8), "cardigan": ("mid_layer", 4),
    "blazer": ("outer_layer", 8), "down-jacket": ("outer_layer", 12),
    "heels": ("footwear", 15), "sandals": ("footwear", 15), "shoes": ("footwear", 15),
    "slippers": ("footwear", 15), "socks": ("socks", 1), "boots": ("footwear", 15),
    "sneakers": ("footwear", 15),
    "bag": ("accessory", 20), "tie": ("neckwear", 5), "hat": ("accessory", 20),
    "accessories": ("accessory", 20), "watch": ("accessory", 20),
    "scarf": ("neckwear", 8), "glasses": ("accessory", 20), "belt": ("accessory", 20),
    "earrings": ("accessory", 20), "ring": ("accessory", 20),
    "jewelry": ("accessory", 20), "bracelet": ("accessory", 20),
    "bangle": ("accessory", 20), "necklace": ("accessory", 20),
    "brooch": ("accessory", 20),
}
FALLBACK_META = ("accessory", 3)

SEASON_SEED = [("spring", "春"), ("summer", "夏"), ("fall", "秋"),
               ("winter", "冬"), ("all-season", "四季")]

HEX_RE = re.compile(r"`(#[0-9a-fA-F]{6})`")
ROW_RE = re.compile(r"^\|\s*([a-z0-9-]+)\s*\|")
SECTION_RE = re.compile(r"^###\s+(.+?)\s+`([a-z0-9-]+)`\s*$")


def _row_cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _iter_tables(text: str):
    """Yield (section_slug, [row_lines]) for every '### label `slug`' block with a table."""
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
        if section and line.startswith("|") and not line.startswith("|--") and "slug" not in line:
            rows.append(line)
    if section:
        yield section, rows


def compile_vocabulary(md_text: str) -> dict:
    body_parts, types, color_families, colors, styles = [], [], [], [], []
    for section, rows in _iter_tables(md_text):
        if section in {"dresses", "accessories", "tops", "jewelry", "outerwear",
                       "bottoms", "footwear"}:
            label = None
            for line in md_text.splitlines():
                m = SECTION_RE.match(line)
                if m and m.group(2) == section:
                    label = m.group(1)
                    break
            body_parts.append({"value": section, "label": label})
            for line in rows:
                m = ROW_RE.match(line)
                value = m.group(1)
                cells = _row_cells(line)
                type_label = cells[1]
                role, wash = SEED_TYPE_META.get(value, FALLBACK_META)
                types.append({
                    "value": value, "label": type_label, "body_part": section,
                    "role": role, "wash_interval": wash,
                })
        elif section.endswith("-") or section in {
            "neutral", "red", "orange-yellow", "green", "blue", "purple",
            "pink", "brown", "metallic",
        }:
            label = None
            for line in md_text.splitlines():
                m = SECTION_RE.match(line)
                if m and m.group(2) == section:
                    label = m.group(1)
                    break
            color_families.append({"value": section, "label": label})
            for line in rows:
                m = ROW_RE.match(line)
                value = m.group(1)
                cells = _row_cells(line)
                hex_m = HEX_RE.search(line)
                if not hex_m:
                    raise ValueError(f"color row without hex: {line!r}")
                colors.append({
                    "value": value, "label": cells[1],
                    "family": section, "hex": hex_m.group(1).lower(),
                })
        elif section == "styles":
            for line in rows:
                m = ROW_RE.match(line)
                cells = _row_cells(line)
                styles.append({"value": m.group(1), "label": cells[1]})

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
```

注意 `--print` 与 argparse 的 `print` 冲突已用 `dest="print_only"` 避开。类型 section 的判定用了部位 slug 白名单；颜色 section 用色系 slug 白名单。

- [ ] **Step 4: 跑测试确认通过**

Run: `docker compose exec backend python scripts/compile_vocabulary.py`
Expected: `Wrote /.../backend/app/data/garment_vocabulary.json`

Run: `docker compose exec backend python -m pytest tests/test_vocabulary_compiler.py -v`
Expected: PASS（5 个用例全绿）。

此时旧消费方（`app/utils/garment_vocabulary.py` 读 `types[].value/role/wash_interval`、`materials`、`formality`）仍兼容——v2 结构是 v1 的超集，`materials`/`formality` 形态不变。

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/compile_vocabulary.py backend/tests/test_vocabulary_compiler.py backend/app/data/garment_vocabulary.json backend/requirements.txt
git commit -m "feat(vocab): compile vocabulary.md into v2 garment_vocabulary.json

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 后端 loader 扩展（部位/颜色/风格/季节）

**Files:**
- Modify: `backend/app/utils/garment_vocabulary.py`
- Modify: `backend/tests/test_garment_vocabulary.py`

**Interfaces:**
- Consumes: Task 1 的 v2 JSON（`body_parts`/`types[].label/body_part`/`colors`/`seasons`/`styles`）
- Produces: 新常量 `BODY_PARTS: tuple[dict]`、`TYPES_BY_PART: dict[str, tuple[str, ...]]`、`TYPE_LABELS: dict[str, str]`、`COLOR_FAMILIES: tuple[dict]`、`COLOR_VALUES: tuple[dict]`、`COLOR_VALUE_SET: set[str]`、`STYLE_VALUES: tuple[str, ...]`、`STYLE_LABELS: dict[str, str]`、`SEASON_VALUES: tuple[str, ...]`、`SEASON_LABELS: dict[str, str]`、`BODY_PART_BY_TYPE: dict[str, str]`；`render_tagging_prompt` 支持 `<<STYLES>>`/`<<COLORS>>`/`<<SEASONS>>`/`<<BODY_PARTS>>` 令牌。旧导出（`TYPES`/`ITEM_ROLE`/`DEFAULT_WASH_INTERVALS`/`MATERIALS`/`FORMALITY`）签名不变。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_garment_vocabulary.py` 末尾追加：

```python
def test_v2_sections_are_loaded():
    from app.utils import garment_vocabulary as gv

    assert len(gv.BODY_PARTS) == 7
    assert len(gv.TYPE_LABELS) == 48
    assert len(gv.COLOR_FAMILIES) == 9
    assert len(gv.COLOR_VALUES) == 48
    assert len(gv.STYLE_VALUES) == 11
    assert set(gv.SEASON_VALUES) == {"spring", "summer", "fall", "winter", "all-season"}
    assert gv.BODY_PART_BY_TYPE["tank-top"] == "tops"
    assert gv.BODY_PART_BY_TYPE["necklace"] == "jewelry"
    assert set(gv.TYPES_BY_PART) == {p["value"] for p in gv.BODY_PARTS}
    assert sum(len(v) for v in gv.TYPES_BY_PART.values()) == 48


def test_render_tagging_prompt_renders_new_tokens():
    from app.utils.garment_vocabulary import render_tagging_prompt

    rendered = render_tagging_prompt(
        "<<BODY_PARTS>>|<<TYPES>>|<<COLORS>>|<<STYLES>>|<<SEASONS>>|<<MATERIALS>>|<<FORMALITY>>"
    )
    assert "<<" not in rendered
    assert "军绿" in rendered and "泛三坑" in rendered and "all-season" in rendered


def test_every_color_slug_is_unique_and_hex_is_lowercase():
    from app.utils import garment_vocabulary as gv

    values = [c["value"] for c in gv.COLOR_VALUES]
    assert len(values) == len(set(values))
    for c in gv.COLOR_VALUES:
        assert c["hex"] == c["hex"].lower()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec backend python -m pytest tests/test_garment_vocabulary.py -v`
Expected: FAIL——`AttributeError: module 'app.utils.garment_vocabulary' has no attribute 'BODY_PARTS'`。

- [ ] **Step 3: 扩展 loader**

`backend/app/utils/garment_vocabulary.py` 现有结构是：`_DATA = json.loads(...)` 后导出 `TYPES`/`ITEM_ROLE`/`DEFAULT_WASH_INTERVALS`/`MATERIALS`/`FORMALITY` + `render_tagging_prompt`。在 `FORMALITY` 导出之后追加（现有行不动）：

```python
BODY_PARTS: tuple[dict, ...] = tuple(_DATA["body_parts"])
BODY_PART_BY_TYPE: dict[str, str] = {t["value"]: t["body_part"] for t in _DATA["types"]}
TYPES_BY_PART: dict[str, tuple[str, ...]] = {
    part["value"]: tuple(
        t["value"] for t in _DATA["types"] if t["body_part"] == part["value"]
    )
    for part in _DATA["body_parts"]
}
TYPE_LABELS: dict[str, str] = {t["value"]: t["label"] for t in _DATA["types"]}
COLOR_FAMILIES: tuple[dict, ...] = tuple(_DATA["colors"]["families"])
COLOR_VALUES: tuple[dict, ...] = tuple(_DATA["colors"]["values"])
COLOR_VALUE_SET: set[str] = {c["value"] for c in _DATA["colors"]["values"]}
STYLE_VALUES: tuple[str, ...] = tuple(s["value"] for s in _DATA["styles"])
STYLE_LABELS: dict[str, str] = {s["value"]: s["label"] for s in _DATA["styles"]}
SEASON_VALUES: tuple[str, ...] = tuple(s["value"] for s in _DATA["seasons"])
SEASON_LABELS: dict[str, str] = {s["value"]: s["label"] for s in _DATA["seasons"]}
```

并在 `render_tagging_prompt` 的替换循环里（现替换 `<<TYPES>>`/`<<MATERIALS>>`/`<<FORMALITY>>` 的位置）补四个令牌。重写该函数为：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `docker compose exec backend python -m pytest tests/test_garment_vocabulary.py tests/test_clothing_utils.py -v`
Expected: PASS（含原有用例不回归）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/utils/garment_vocabulary.py backend/tests/test_garment_vocabulary.py
git commit -m "feat(vocab): expose body parts, colors, styles and seasons from the vocabulary

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 前端生成管线扩展（TS 投影 + parity 测试）

**Files:**
- Modify: `frontend/scripts/gen-garment-vocabulary.mjs`
- Modify: `frontend/lib/generated/garment-vocabulary.ts`（`npm run vocab:gen` 产出）
- Modify: `frontend/tests/garment-vocabulary-parity.test.ts`

**Interfaces:**
- Consumes: v2 JSON（Task 1）
- Produces: 新导出 `BODY_PART_VALUES`、`TYPE_ENTRIES: {value,label,body_part}[]`、`COLOR_FAMILY_VALUES`、`COLOR_VALUES: {value,label,family,hex}[]`、`STYLE_VALUES`、`SEASON_VALUES`（旧导出 `CLOTHING_TYPE_VALUES`/`MATERIAL_VALUES`/`FORMALITY_VALUES`/`ITEM_ROLE` 不变）。

- [ ] **Step 1: 写失败测试**

在 `frontend/tests/garment-vocabulary-parity.test.ts` 追加（沿用该文件现有的 `readFileSync(resolve(__dirname,'..','..','backend',...))` 读 JSON 的方式）：

```ts
it('exposes v2 sections matching the backend JSON', () => {
  expect(BODY_PART_VALUES).toEqual(vocabulary.body_parts.map((p: { value: string }) => p.value));
  expect(TYPE_ENTRIES.map((t) => t.value)).toEqual(vocabulary.types.map((t: { value: string }) => t.value));
  expect(COLOR_VALUES.map((c) => c.hex)).toEqual(vocabulary.colors.values.map((c: { hex: string }) => c.hex));
  expect(STYLE_VALUES).toEqual(vocabulary.styles.map((s: { value: string }) => s.value));
  expect(SEASON_VALUES).toEqual(vocabulary.seasons.map((s: { value: string }) => s.value));
});
```

在该文件顶部 import 行扩展为：

```ts
import {
  FORMALITY_VALUES, ITEM_ROLE, MATERIAL_VALUES,
  BODY_PART_VALUES, TYPE_ENTRIES, COLOR_FAMILY_VALUES, COLOR_VALUES, STYLE_VALUES, SEASON_VALUES,
} from '@/lib/generated/garment-vocabulary';
```

（注：`COLOR_VALUES` 与旧测试文件里若有同名变量冲突，重命名 import 为 `GENERATED_COLOR_VALUES` 并同步断言。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test -- garment-vocabulary-parity`
Expected: FAIL——导出不存在（TS 编译/运行错误）。

- [ ] **Step 3: 扩展生成器并重新生成**

`frontend/scripts/gen-garment-vocabulary.mjs`：把 `render({ types, materials, formality })` 的解构和内容替换为（保持旧导出格式不变，`key()`/`list()` 辅助函数不动）：

```js
function render({ body_parts, types, colors, seasons, styles, materials, formality }) {
  const roles = types.map(({ value, role }) => `  ${key(value)}: ${quote(role)},`).join('\n');
  const json = (value) => JSON.stringify(value);
  return [
    '// Generated from backend/app/data/garment_vocabulary.json by scripts/gen-garment-vocabulary.mjs.',
    '// Do not edit by hand; run `npm run vocab:gen`.',
    `export const CLOTHING_TYPE_VALUES = ${list(types.map((t) => t.value))};`,
    `export const MATERIAL_VALUES = ${list(materials)};`,
    `export const FORMALITY_VALUES = ${list(formality)};`,
    `export const BODY_PART_VALUES = ${list(body_parts.map((p) => p.value))};`,
    `export const SEASON_VALUES = ${list(seasons.map((s) => s.value))};`,
    `export const STYLE_VALUES = ${list(styles.map((s) => s.value))};`,
    `export const COLOR_FAMILY_VALUES = ${list(colors.families.map((f) => f.value))};`,
    `export const TYPE_ENTRIES = ${json(types.map(({ value, label, body_part }) => ({ value, label, body_part })))} as const;`,
    `export const COLOR_VALUES = ${json(colors.values)} as const;`,
    `export const STYLE_LABELS = ${json(Object.fromEntries(styles.map((s) => [s.value, s.label])))} as const;`,
    '',
    'export const ITEM_ROLE: Record<string, string> = {',
    roles,
    '};',
    '',
  ].join('\n');
}
```

`JSON.stringify` 产双引号对象字面量，TS 可直接用 `as const`。

Run: `cd frontend && npm run vocab:gen`
Expected: `Wrote .../frontend/lib/generated/garment-vocabulary.ts`

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npm test -- garment-vocabulary-parity && npm run vocab:check && npx tsc --noEmit`
Expected: 全部 PASS / `vocab-check: OK` / tsc 无错误。

- [ ] **Step 5: 提交**

```bash
git add frontend/scripts/gen-garment-vocabulary.mjs frontend/lib/generated/garment-vocabulary.ts frontend/tests/garment-vocabulary-parity.test.ts
git commit -m "feat(vocab): project body parts, colors, styles and seasons into the generated TS

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 收敛硬编码词表集合（ai_service VALID_* 与前端 CLOTHING_COLORS）

**Files:**
- Create: `backend/app/utils/color_migration.py`（仅 `LEGACY_COLOR_ALIASES` 表，Task 5 追加函数）
- Modify: `backend/app/services/ai_service.py`（VALID_COLORS/VALID_STYLES/VALID_SEASONS/COLOR_ALIASES 区块，约 64–115 行）
- Modify: `backend/tests/test_garment_vocabulary.py`
- Modify: `frontend/lib/types.ts`（`CLOTHING_COLORS` 定义，约 171 行起）
- Modify: `frontend/components/color-eyedropper.tsx`、`frontend/lib/hooks/use-translated-constants.ts`（如有 `CLOTHING_COLORS` 字段名差异只调映射）

**Interfaces:**
- Consumes: Task 2 loader 常量；Task 3 生成导出 `COLOR_VALUES`
- Produces: `ai_service.VALID_COLORS: set[str]`（= 新 48 色 slug）、`VALID_STYLES: set[str]`（= 11 风格）、`VALID_SEASONS: set[str]`（= 5 季节）、`LEGACY_COLOR_ALIASES: dict[str, str]`；前端 `CLOTHING_COLORS` 变为由 `COLOR_VALUES` 派生的兼容层 `{name: label, value, hex}[]`（旧消费者零改动）。

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_garment_vocabulary.py` 追加：

```python
def test_ai_validation_sets_come_from_the_vocabulary():
    from app.services.ai_service import VALID_COLORS, VALID_SEASONS, VALID_STYLES
    from app.utils import garment_vocabulary as gv

    assert VALID_COLORS == gv.COLOR_VALUE_SET
    assert VALID_STYLES == set(gv.STYLE_VALUES)
    assert VALID_SEASONS == set(gv.SEASON_VALUES)


def test_legacy_color_aliases_point_at_new_slugs():
    from app.services.ai_service import LEGACY_COLOR_ALIASES
    from app.utils.garment_vocabulary import COLOR_VALUE_SET

    assert set(LEGACY_COLOR_ALIASES.values()) <= COLOR_VALUE_SET
    assert LEGACY_COLOR_ALIASES["burgundy"] == "wine"
    assert LEGACY_COLOR_ALIASES["tan"] == "camel"
    assert LEGACY_COLOR_ALIASES["beige"] == "khaki"
    assert LEGACY_COLOR_ALIASES["light-blue"] == "sky"
```

前端在 `frontend/tests/garment-vocabulary-parity.test.ts` 追加：

```ts
it('CLOTHING_COLORS is derived from the generated color values', () => {
  expect(CLOTHING_COLORS.map((c) => c.value)).toEqual(COLOR_VALUES.map((c) => c.value));
  expect(CLOTHING_COLORS.every((c) => Boolean(c.hex))).toBe(true);
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec backend python -m pytest tests/test_garment_vocabulary.py -v`
Expected: FAIL——`ImportError: cannot import name 'LEGACY_COLOR_ALIASES'`（VALID_COLORS 也与新集合不符）。

- [ ] **Step 3: 实现收敛**

`backend/app/services/ai_service.py`：
1. 文件顶部 import 行扩展：

```python
from app.utils.garment_vocabulary import (
    FORMALITY,
    MATERIALS,
    TYPES,
    COLOR_VALUE_SET,
    SEASON_VALUES,
    STYLE_VALUES,
    render_tagging_prompt,
)
```

2. 把 `VALID_COLORS`（现 20 值字面量）、`VALID_STYLES`（现 12 值）、`VALID_SEASONS`（现 5 值字面量）三个赋值替换为：

```python
VALID_COLORS = COLOR_VALUE_SET
VALID_STYLES = set(STYLE_VALUES)
VALID_SEASONS = set(SEASON_VALUES)
```

3. 创建 `backend/app/utils/color_migration.py`（纯模块，迁移工具在 Task 5 追加到这里）：

```python
"""Legacy vocabulary mapping kept in one place (AI parsing + DB migration)."""

LEGACY_COLOR_ALIASES = {
    "burgundy": "wine",
    "light-blue": "sky",
    "tan": "camel",
    "beige": "khaki",
    "charcoal": "dark-gray",
    "teal": "klein",
    "mustard": "ginger",
    "lavender": "taro",
    "chocolate": "coffee",
}
```

`ai_service.py` 原 `COLOR_ALIASES` 位置替换为（保留旧引用名，`_parse_tags_from_response` 不用改调用点）：

```python
from app.utils.color_migration import LEGACY_COLOR_ALIASES

COLOR_ALIASES = LEGACY_COLOR_ALIASES  # 兼容旧引用名
```

`frontend/lib/types.ts`：把 `CLOTHING_COLORS` 的 22 行字面量数组替换为派生兼容层：

```ts
import { COLOR_VALUES } from '@/lib/generated/garment-vocabulary';

export const CLOTHING_COLORS = COLOR_VALUES.map((c) => ({
  name: c.label,
  value: c.value,
  hex: c.hex,
}));
```

（`color-eyedropper.tsx` 与 `use-translated-constants.ts` 里把色名翻译 `tConst('colors.…')` 改为直接用 `name`——词表自带中文名；见 Task 7 的 UI 层面收口，本任务先保证值域一致。）

- [ ] **Step 4: 跑测试确认通过**

Run: `docker compose exec backend python -m pytest tests/test_garment_vocabulary.py tests/test_clothing_utils.py -v`
Run: `cd frontend && npm test -- garment-vocabulary-parity && npx tsc --noEmit`
Expected: PASS / 无类型错误。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/ai_service.py backend/tests/test_garment_vocabulary.py frontend/lib/types.ts frontend/components/color-eyedropper.tsx frontend/lib/hooks/use-translated-constants.ts
git commit -m "refactor(vocab): derive AI validation sets and frontend colors from the vocabulary

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 颜色迁移映射工具（旧列 → 主/辅色数组）

**Files:**
- Modify: `backend/app/utils/color_migration.py`（Task 4 已建，本任务追加两个函数）
- Create: `backend/tests/test_color_migration.py`

**Interfaces:**
- Consumes: Task 4 的 `LEGACY_COLOR_ALIASES`（同文件常量）、Task 2 的 `BODY_PART_BY_TYPE`
- Produces: `migrate_legacy_colors(primary_color: str | None, colors: list[str] | None) -> tuple[list[str], list[str]]`（主色数组、辅色数组）；`body_part_case_sql(type_column: str) -> str`（生成 CASE 表达式）。Task 6 迁移直接调用这两个函数。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_color_migration.py`：

```python
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
        ("unknown-slug", ["weird"], ["unknown-slug"], ["weird"]),
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec backend python -m pytest tests/test_color_migration.py -v`
Expected: FAIL——`ImportError: cannot import name 'migrate_legacy_colors'`（Task 4 只建了别名表）。

- [ ] **Step 3: 实现映射工具**

向 `backend/app/utils/color_migration.py` 追加（别名表下方，勿再写模块 docstring）：

```python
from __future__ import annotations

from app.utils.garment_vocabulary import BODY_PART_BY_TYPE


def _normalize(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().lower()
    return LEGACY_COLOR_ALIASES.get(value, value)


def migrate_legacy_colors(
    primary_color: str | None, colors: list[str] | None
) -> tuple[list[str], list[str]]:
    primary = _normalize(primary_color)
    primary_list = [primary] if primary else []
    secondary: list[str] = []
    for raw in colors or []:
        value = _normalize(raw)
        if value and value not in primary_list and value not in secondary:
            secondary.append(value)
    return primary_list, secondary


def body_part_case_sql(type_column: str) -> str:
    branches = " ".join(
        f"WHEN {type_column} = '{value}' THEN '{part}'"
        for value, part in sorted(BODY_PART_BY_TYPE.items())
    )
    return f"CASE {branches} ELSE NULL END"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `docker compose exec backend python -m pytest tests/test_color_migration.py -v`
Expected: PASS（10 个用例）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/utils/color_migration.py backend/tests/test_color_migration.py
git commit -m "feat(db): add legacy color migration mapping helpers

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: Alembic 迁移 + 模型/Schema/API 新字段

**Files:**
- Create: `backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py`
- Modify: `backend/app/models/item.py`（ClothingItem 列定义）
- Modify: `backend/app/schemas/item.py`（ItemCreate/ItemUpdate/ItemResponse 字段）
- Modify: `backend/tests/test_items.py`（新增用例）

**Interfaces:**
- Consumes: Task 5 的 `migrate_legacy_colors`/`body_part_case_sql`
- Produces: `clothing_items` 新列 `body_part`、`primary_colors[]`、`secondary_colors[]`、`temp_low`、`temp_high`、`purchase_date_precision`；`outfits.occasion` 放宽可空；旧列 `primary_color`/`colors` 删除。API 字段：`body_part`、`primary_colors`、`secondary_colors`、`temp_low`、`temp_high`、`purchase_date`（`"YYYY"` 或 `"YYYY-MM"`）、`purchase_price`、`purchase_date_precision`（响应返回）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_items.py` 追加（沿用该文件 `class TestItemList:` 的 client/auth_headers/db_session 风格；新类亦可）：

```python
class TestPersonalWardrobeFields:
    async def test_create_item_with_new_fields(self, client, auth_headers):
        payload = {
            "type": "tank-top",
            "image_path": "test.jpg",
            "body_part": "tops",
            "primary_colors": ["army", "black"],
            "secondary_colors": [],
            "temp_low": 12,
            "temp_high": 22,
            "purchase_date": "2024-03",
            "purchase_price": 199.0,
        }
        resp = await client.post("/api/v1/items", json=payload, headers=auth_headers)
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        assert data["primary_colors"] == ["army", "black"]
        assert data["temp_low"] == 12
        assert data["purchase_date"].startswith("2024-03")
        assert data["purchase_date_precision"] == "month"

    async def test_purchase_date_year_only_roundtrip(self, client, auth_headers):
        payload = {"type": "shirt", "image_path": "test.jpg", "purchase_date": "2023"}
        resp = await client.post("/api/v1/items", json=payload, headers=auth_headers)
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        assert data["purchase_date"].startswith("2023-01")
        assert data["purchase_date_precision"] == "year"

    async def test_list_hides_retired_by_default(self, client, auth_headers, db_session):
        create = await client.post(
            "/api/v1/items",
            json={"type": "shirt", "image_path": "a.jpg"},
            headers=auth_headers,
        )
        item_id = create.json()["id"]
        await client.patch(
            f"/api/v1/items/{item_id}",
            json={"is_archived": True, "archive_reason": "donated"},
            headers=auth_headers,
        )
        default_list = await client.get("/api/v1/items", headers=auth_headers)
        assert item_id not in [i["id"] for i in default_list.json()["items"]]
        filtered = await client.get(
            "/api/v1/items", params={"is_archived": "true"}, headers=auth_headers
        )
        assert item_id in [i["id"] for i in filtered.json()["items"]]

    async def test_occasion_is_optional_on_outfits(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/outfits",
            json={"source": "manual", "scheduled_for": "2026-10-01"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201, 422)  # 422 若 route 有其它必填；但不得因 occasion 缺失
        if resp.status_code != 422:
            assert resp.json().get("occasion") in (None, "")
        else:
            assert "occasion" not in resp.text
```

（`test_items.py` 的 fixture 名以文件现状为准：若 create 走 multipart form 而非 JSON，本用例的 payload 提交方式随现有 create 用例调整，断言不变。）

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec backend python -m pytest tests/test_items.py -v`
Expected: FAIL——创建响应不含 `primary_colors`/`purchase_date_precision`（字段不存在）。

- [ ] **Step 3: 写迁移**

创建 `backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py`（沿用 `d5e6f7a8b9c0_add_ai_completed_at_to_items.py` 的头部风格）：

```python
"""personal wardrobe fields: body_part, primary/secondary colors, temp bounds

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-10-02

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.utils.color_migration import body_part_case_sql

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clothing_items", sa.Column("body_part", sa.String(50), nullable=True))
    op.add_column(
        "clothing_items",
        sa.Column("primary_colors", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "clothing_items",
        sa.Column("secondary_colors", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.add_column("clothing_items", sa.Column("temp_low", sa.Float(), nullable=True))
    op.add_column("clothing_items", sa.Column("temp_high", sa.Float(), nullable=True))
    op.add_column(
        "clothing_items", sa.Column("purchase_date_precision", sa.String(8), nullable=True)
    )

    # 旧颜色数据 -> 新数组：主色进 primary_colors，其余去重进 secondary_colors。
    # 别名归一由 Python 端逐行处理（值域小，行数 < 1000）。
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, type, primary_color, colors FROM clothing_items")
    ).fetchall()
    from app.utils.color_migration import migrate_legacy_colors

    for row in rows:
        primary_list, secondary_list = migrate_legacy_colors(row.primary_color, row.colors)
        conn.execute(
            sa.text(
                "UPDATE clothing_items SET body_part = "
                + body_part_case_sql("type")
                + ", primary_colors = :p, secondary_colors = :s WHERE id = :id"
            ),
            {
                "p": primary_list,
                "s": secondary_list,
                "id": row.id,
            },
        )
    # 老行 type 映射不到 body_part 的兜底：全表再刷一次 CASE（新行由应用层写入）。
    op.execute(
        sa.text(
            "UPDATE clothing_items SET body_part = "
            + body_part_case_sql("type")
            + " WHERE body_part IS NULL"
        )
    )

    op.alter_column("outfits", "occasion", existing_type=sa.String(50), nullable=True)
    op.drop_column("clothing_items", "primary_color")
    op.drop_column("clothing_items", "colors")


def downgrade() -> None:
    op.add_column(
        "clothing_items",
        sa.Column("colors", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "clothing_items", sa.Column("primary_color", sa.String(50), nullable=True)
    )
    op.execute(
        sa.text(
            "UPDATE clothing_items SET primary_color = primary_colors[1], "
            "colors = primary_colors || secondary_colors"
        )
    )
    op.alter_column("outfits", "occasion", existing_type=sa.String(50), nullable=False)
    op.drop_column("clothing_items", "purchase_date_precision")
    op.drop_column("clothing_items", "temp_high")
    op.drop_column("clothing_items", "temp_low")
    op.drop_column("clothing_items", "secondary_colors")
    op.drop_column("clothing_items", "primary_colors")
    op.drop_column("clothing_items", "body_part")
```

迁移里数组参数绑定按 asyncpg 的 ARRAY 适配；如 `execute(text(...), {"p": [...]})` 在该驱动下报绑定错误，改为字符串构造 `ARRAY[...]::varchar[]` 字面量（对列表元素做单引号转义）——**不允许**跳过数据迁移。

- [ ] **Step 4: 改模型与 Schema**

`backend/app/models/item.py` ClothingItem：
1. `colors`/`primary_color` 两列定义删除。
2. 在 `style` 列附近追加：

```python
    body_part: Mapped[str | None] = mapped_column(String(50))
    primary_colors: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    secondary_colors: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    temp_low: Mapped[float | None] = mapped_column(Float)
    temp_high: Mapped[float | None] = mapped_column(Float)
    purchase_date_precision: Mapped[str | None] = mapped_column(String(8))
```

（`Float` 若未导入则补 `from sqlalchemy import Float`；`ARRAY` 已有。）

`backend/app/schemas/item.py`：
1. `ItemCreate`/`ItemUpdate`/`ItemResponse` 中 `colors: list[str]`/`primary_color: str | None` 字段替换为：

```python
    body_part: str | None = None
    primary_colors: list[str] = Field(default_factory=list)
    secondary_colors: list[str] = Field(default_factory=list)
    temp_low: float | None = None
    temp_high: float | None = None
```

2. `purchase_date` 的校验收紧为 `"YYYY"` 或 `"YYYY-MM"`（Pydantic v2）：

```python
    purchase_date: str | None = Field(
        default=None, pattern=r"^\d{4}(-\d{2})?$"
    )
```

3. `ItemResponse` 增加 `purchase_date_precision: str | None = None`。响应的 `purchase_date` 输出 `"YYYY-MM"`（存储的当月 1 日格式化为 `YYYY-MM`）；`purchase_date_precision == "year"` 时前端按年显示（Task 7 处理）。
4. 服务层 `item_service.py` 中如有把 `purchase_date` 字符串转 `date` 的路径：`"YYYY"` → `date(year, 1, 1)` 且写 `purchase_date_precision="year"`；`"YYYY-MM"` → `date(year, month, 1)` 且写 `purchase_date_precision="month"`；空 → 两列皆 NULL。

- [ ] **Step 5: 跑测试确认通过**

Run: `docker compose exec backend python -m pytest tests/test_items.py tests/test_color_migration.py -v`
Run: `docker compose exec backend python scripts/check_migration_heads.py`
Expected: PASS；migration heads 检查绿（唯一 head = e7f8a9b0c1d2）。

- [ ] **Step 6: 提交**

```bash
git add backend/migrations/versions/e7f8a9b0c1d2_personal_wardrobe_fields.py backend/app/models/item.py backend/app/schemas/item.py backend/app/services/item_service.py backend/tests/test_items.py
git commit -m "feat(db): add body_part, color arrays and temp bounds; retire legacy color columns

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: 表单/详情 UI 适配新字段

**Files:**
- Modify: `frontend/lib/types.ts`（`Item`/`ItemTags`/`ItemFilter`）
- Modify: `frontend/components/add-item-dialog.tsx`
- Modify: `frontend/components/item-detail-dialog.tsx`
- Modify: `frontend/lib/hooks/use-translated-constants.ts`
- Create: `frontend/components/vocab/part-type-select.tsx`
- Create: `frontend/components/vocab/color-multi-select.tsx`
- Create: `frontend/lib/purchase-date.ts`
- Create: `frontend/tests/purchase-date.test.ts`

**Interfaces:**
- Consumes: Task 3 生成导出（`TYPE_ENTRIES`/`COLOR_VALUES`/`STYLE_VALUES`/`BODY_PART_VALUES`）、Task 6 的 API 字段
- Produces: `formatPurchaseDate(value: string | null | undefined, precision: string | null): string`、`normalizePurchaseDate(input: string): string`（输入 `"2024"`/`"2024-03"` 校验归一）；表单字段名 `primary_colors`/`secondary_colors`/`style`/`temp_low`/`temp_high`/`purchase_date`/`purchase_price`/`is_archived`。

- [ ] **Step 1: 写失败测试**

创建 `frontend/tests/purchase-date.test.ts`：

```ts
import { describe, expect, it } from 'vitest';
import { formatPurchaseDate, normalizePurchaseDate } from '@/lib/purchase-date';

describe('purchase date', () => {
  it('accepts year-only and year-month', () => {
    expect(normalizePurchaseDate('2024')).toBe('2024');
    expect(normalizePurchaseDate('2024-03')).toBe('2024-03');
    expect(() => normalizePurchaseDate('2024-03-05')).toThrow();
    expect(() => normalizePurchaseDate('abcd')).toThrow();
    expect(normalizePurchaseDate('')).toBe('');
  });

  it('formats by precision', () => {
    expect(formatPurchaseDate('2024-01', 'year')).toBe('2024');
    expect(formatPurchaseDate('2024-03', 'month')).toBe('2024-03');
    expect(formatPurchaseDate('2024-03', null)).toBe('2024-03');
    expect(formatPurchaseDate(null, null)).toBe('');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test -- purchase-date`
Expected: FAIL——模块不存在。

- [ ] **Step 3: 实现工具与类型**

创建 `frontend/lib/purchase-date.ts`：

```ts
const PATTERN = /^\d{4}(-\d{2})?$/;

export function normalizePurchaseDate(input: string): string {
  const value = input.trim();
  if (value === '') return '';
  if (!PATTERN.test(value)) throw new Error(`invalid purchase date: ${input}`);
  return value;
}

export function formatPurchaseDate(
  value: string | null | undefined,
  precision: string | null | undefined,
): string {
  if (!value) return '';
  const [year, month] = value.split('-');
  if (precision === 'year' || !month) return year;
  return `${year}-${month}`;
}
```

`frontend/lib/types.ts` 的 `Item`：
1. `colors: string[]` 与 `primary_color?` 字段替换为：

```ts
  body_part?: string | null;
  primary_colors: string[];
  secondary_colors: string[];
  temp_low?: number | null;
  temp_high?: number | null;
  purchase_date_precision?: string | null;
```

2. `ItemFilter` 的 `colors` 语义不变（后端沿用 `colors` 参数过滤主/辅色并集，Task 6 服务层保证）。

- [ ] **Step 4: 改表单组件**

先建两个叶子组件（完整实现，对话框只负责接线）。

创建 `frontend/components/vocab/part-type-select.tsx`：

```tsx
'use client';

import type { TypeEntry, VocabEntry } from '@/lib/types';

export function PartTypeSelect({
  parts,
  entries,
  bodyPart,
  type,
  onBodyPartChange,
  onTypeChange,
}: {
  parts: VocabEntry[];
  entries: TypeEntry[];
  bodyPart: string;
  type: string;
  onBodyPartChange: (value: string) => void;
  onTypeChange: (value: string) => void;
}) {
  return (
    <div className="flex gap-2">
      <select
        className="border rounded px-2 py-1"
        value={bodyPart}
        onChange={(e) => {
          onBodyPartChange(e.target.value);
          onTypeChange('');
        }}
      >
        <option value="">部位</option>
        {parts.map((p) => (
          <option key={p.value} value={p.value}>{p.label}</option>
        ))}
      </select>
      <select
        className="border rounded px-2 py-1"
        value={type}
        onChange={(e) => onTypeChange(e.target.value)}
      >
        <option value="">类别</option>
        {entries
          .filter((t) => t.body_part === bodyPart)
          .map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
      </select>
    </div>
  );
}
```

创建 `frontend/components/vocab/color-multi-select.tsx`：

```tsx
'use client';

import type { ColorEntry } from '@/lib/types';

export function ColorMultiSelect({
  values,
  options,
  onChange,
}: {
  values: string[];
  options: ColorEntry[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((c) => {
        const active = values.includes(c.value);
        return (
          <button
            key={c.value}
            type="button"
            aria-pressed={active}
            onClick={() =>
              onChange(
                active ? values.filter((v) => v !== c.value) : [...values, c.value],
              )
            }
            className={`flex flex-col items-center rounded-md p-1 ${active ? 'ring-2 ring-primary' : ''}`}
          >
            <span className="block h-6 w-6 rounded" style={{ backgroundColor: c.hex }} />
            <span className="text-xs">{c.label}</span>
          </button>
        );
      })}
    </div>
  );
}
```

`frontend/components/add-item-dialog.tsx` 与 `frontend/components/item-detail-dialog.tsx`（两处相同的改动）：

1. **两级类型选择**：把现有单列 `useClothingTypes()` 的 Select 换成 `<PartTypeSelect>`（`parts` 传词表 `body_parts` 带 label，`entries` 传 `types`）——先选部位再选类别；保存值仍是类别 `value`，同时写 `body_part`。
2. **颜色主/辅多选**：把现有单选颜色控件换成两个 `<ColorMultiSelect>`（options 传 `ColorEntry[]`：运行时词表或 `COLOR_VALUES`，色块用 `hex`、名称用 `label`）：`primary_colors`、`secondary_colors`（辅色可空）。色块网格按词表序呈现。
3. **风格多选**：`style` 字段（`Item.tags.style` 现状是 tags 内数组，保持提交路径不变）用 `STYLE_VALUES` 色块/文字 chip 多选，可空。
4. **温度区间**：两个数字输入 `temp_low`/`temp_high`（℃，可空）。
5. **购买时间/价格**：文本输入 `purchase_date`（placeholder `2024 或 2024-03`，保存前 `normalizePurchaseDate` 校验）、数字输入 `purchase_price`；展示处用 `formatPurchaseDate(item.purchase_date, item.purchase_date_precision)`。
6. **状态**：`is_archived` 开关，label「状态」，两档「在役 / 已退役」；选已退役时可填 `archive_reason`（退役原因，可空）。
7. **改名**：`subtype` 输入的 label 从「子类型/Subtype」改为「**备注**」；`notes` 文本域 label 用「**描述**」。
8. 词表自带中文名（`label`），因此这些选择器**不再走** `tConst('colors.*')`/`tConst('types.*')` 翻译——直接显示 `label`。

- [ ] **Step 5: 跑测试确认通过**

Run: `cd frontend && npm test && npm run i18n:check && npx tsc --noEmit`
Expected: PASS；`i18n:scan` 不报新增硬编码中文（组件里所有新增可见文案走 `t('...')` 或词表 label——「在役/已退役/备注/描述」等新文案加进 `messages/en/wardrobe.json` 与 `messages/zh-CN/wardrobe.json`，en 值用英文）。

- [ ] **Step 6: 提交**

```bash
git add frontend/lib/types.ts frontend/lib/purchase-date.ts frontend/tests/purchase-date.test.ts frontend/components/add-item-dialog.tsx frontend/components/item-detail-dialog.tsx frontend/lib/hooks/use-translated-constants.ts frontend/messages/en/wardrobe.json frontend/messages/zh-CN/wardrobe.json
git commit -m "feat(ui): edit new wardrobe fields with two-level types and color multi-select

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: zh-CN 锁 + i18n 校验范围放宽

**Files:**
- Modify: `frontend/lib/i18n/locales.ts`（`DEFAULT_LOCALE`）
- Modify: `frontend/scripts/i18n-check.mjs`（parity 语言范围）
- Modify: `frontend/components/header.tsx`（LocaleSwitcher 摘除）

**Interfaces:**
- Consumes: 现有 next-intl 管线
- Produces: 默认语言 zh-CN；parity 只查 zh-CN；LocaleSwitcher 不再渲染（组件文件保留）。

- [ ] **Step 1: 收窄 parity 范围**

`frontend/scripts/i18n-check.mjs` 中：

```js
const locales = readdirSync(MESSAGES_DIR).filter((d) => statSync(join(MESSAGES_DIR, d)).isDirectory()).sort();
```

替换为：

```js
// Parity only gates zh-CN; en is the key source. Other locales are frozen (kept, not checked).
const CHECKED_LOCALES = ['zh-CN'];
const locales = readdirSync(MESSAGES_DIR)
  .filter((d) => statSync(join(MESSAGES_DIR, d)).isDirectory())
  .filter((d) => CHECKED_LOCALES.includes(d))
  .sort();
```

Run: `cd frontend && npm run i18n:parity`
Expected: PASS（冻结语言的缺键不再报错）。

- [ ] **Step 2: 默认语言改 zh-CN**

`frontend/lib/i18n/locales.ts`：

```ts
export const DEFAULT_LOCALE: SupportedLocale = 'zh-CN';
```

（`detectLocale()` 逻辑不动：cookie 优先，无 cookie 时落 DEFAULT_LOCALE → 现在落 zh-CN。）

- [ ] **Step 3: 摘 LocaleSwitcher**

`frontend/components/header.tsx`：删除 `<LocaleSwitcher />` 的渲染行（import 一并去掉，组件文件 `components/locale-switcher.tsx` 保留不删）。header 右侧原有布局容器保持，不塌陷。

- [ ] **Step 4: 全量校验**

Run: `cd frontend && npm run i18n:check && npm test && npx tsc --noEmit`
Expected: 全 PASS。手动冒烟：`npm run dev` 打开首页 → UI 为中文，header 无语言切换。

- [ ] **Step 5: 提交**

```bash
git add frontend/lib/i18n/locales.ts frontend/scripts/i18n-check.mjs frontend/components/header.tsx
git commit -m "feat(i18n): lock UI to zh-CN and gate parity on zh-CN only

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: 裁剪后端（路由不挂 + worker 注册摘除，代码保留）

**Files:**
- Modify: `backend/app/api/router.py`（卸 include）
- Modify: `backend/app/api/items.py`（wash 两个端点摘装饰器）
- Modify: `backend/app/workers/worker.py`（functions/cron_jobs 清单）
- Modify: `backend/tests/test_items.py`（新增 404 断言）

**Interfaces:**
- Consumes: 现有路由/worker 注册点（见下）
- Produces: `/api/v1/families`、`/api/v1/notifications`、`/api/v1/learning`、`/api/v1/pairings` 全部 404（families/notifications/learning 摘；pairings 按 spec 是"休眠不进导航"——**后端路由不动**，此任务只摘 families/notifications/learning）；`POST /items/{id}/wash`、`GET /items/{id}/wash-history` 不再挂载；worker 不再注册通知/学习/洗护任务。suggest 端点在 `api/outfits.py` 内**不动**（休眠）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_items.py` 追加：

```python
class TestPrunedRoutes:
    async def test_families_notifications_learning_are_unmounted(self, client, auth_headers):
        for path in ("/api/v1/families", "/api/v1/notifications", "/api/v1/learning"):
            resp = await client.get(path, headers=auth_headers)
            assert resp.status_code == 404, path

    async def test_wash_endpoints_are_unmounted(self, client, auth_headers):
        resp = await client.post("/api/v1/items/some-id/wash", headers=auth_headers)
        assert resp.status_code == 404
        resp = await client.get("/api/v1/items/some-id/wash-history", headers=auth_headers)
        assert resp.status_code == 404

    async def test_pairings_stays_mounted_but_dormant(self, client, auth_headers):
        resp = await client.get("/api/v1/pairings", headers=auth_headers)
        assert resp.status_code != 404
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec backend python -m pytest tests/test_items.py::TestPrunedRoutes -v`
Expected: FAIL——families/notifications/learning 现在是 200/401/403 而非 404。

- [ ] **Step 3: 卸挂载**

1. `backend/app/api/router.py`：删除（或注释并在注释里写明"摘不删，spec §7"）以下 include 行——families、notifications（含 `prefix="/notifications"` 那条）、learning 三个模块的 `router.include_router(...)`。**保留** `pairings`、`analytics`、`outfits` 的 include。
2. `backend/app/api/items.py`：定位 wash 两个端点（约 1449 行 `POST /items/{item_id}/wash`、约 1492 行 `GET /items/{item_id}/wash-history`），删除其 `@router.post`/`@router.get` 装饰器行，函数体保留，函数上方加注释：

```python
# 摘不删（spec §7）：洗衣跟踪入口已下线，函数保留备查。
```

3. `backend/app/workers/worker.py`：`functions` 列表删除 `send_notification`、`retry_failed_notifications`、`check_scheduled_notifications`、`process_scheduled_notification`、`check_wash_reminders`、`update_learning_profiles` 六个名字（对应 import 一并去掉，`app/workers/notifications.py` 文件保留）；`cron_jobs` 列表删除这些任务的注册项，保留 `recover_stale_processing_items` 与图片 worker 全部内容。

- [ ] **Step 4: 跑测试确认通过**

Run: `docker compose exec backend python -m pytest tests/test_items.py tests/test_outfits.py -v`
Expected: PASS（TestPrunedRoutes 绿；其余不回归）。若 `test_outfits.py` 或其它既有测试引用了被摘路由（如调用 `/families`），把对应测试文件**整体移到** `backend/tests/pruned/` 目录（保留代码不删），并确认 `testpaths = tests` 仍覆盖（pytest 递归含子目录；若 pruned 目录里的测试被收集而失败，则在该目录加 `pytest.ini` 级 ignore——在 `backend/pytest.ini` 的 `addopts` 追加 `--ignore=tests/pruned`）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/router.py backend/app/api/items.py backend/app/workers/worker.py backend/tests/test_items.py backend/pytest.ini
git commit -m "refactor: unmount families/notifications/learning and wash endpoints (keep code)

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: 裁剪前端导航 + 键清理

**Files:**
- Modify: `frontend/components/sidebar.tsx`、`frontend/components/mobile-sidebar.tsx`、`frontend/components/mobile-nav.tsx`
- Modify: `frontend/messages/en/nav.json`、`frontend/messages/zh-CN/nav.json`

**Interfaces:**
- Consumes: 现有导航数组（label key → href）
- Produces: 主导航只剩 `dashboard`/`wardrobe`/`outfits`/`history`/`analytics`；次导航只剩 `settings`；mobile-nav 去掉 suggest 项；nav.json（en+zh-CN）删除未用键。

- [ ] **Step 1: 改导航数组**

`frontend/components/sidebar.tsx` 与 `frontend/components/mobile-sidebar.tsx`（两份相同的 `navigation`/`secondaryNavigation` 数组——一并改，保持镜像一致）：

- `navigation` 删除条目：`suggestOutfit`（/dashboard/suggest）、`pairings`（/dashboard/pairings）、`familyFeed`（/dashboard/family/feed）、`aiLearning`（/dashboard/learning）。保留：dashboard、wardrobe、outfits、history、analytics。
- `secondaryNavigation` 删除条目：`family`、`notifications`。保留 settings。

`frontend/components/mobile-nav.tsx`：五项里删 `suggest-outfits` 项，补 `outfits`（/dashboard/outfits，图标 LayoutGrid）——保留 dashboard/wardrobe/outfits/settings 四项。

`analytics` 的 zh-CN 显示名顺手改为「统计」（`messages/zh-CN/nav.json` 中 `"analytics": "统计"`），en 保持 "Analytics"（Task 11 计划里统计页改名到「统计」，此处只改显示名）。

- [ ] **Step 2: 清理 nav 键**

`frontend/messages/en/nav.json` 与 `frontend/messages/zh-CN/nav.json` 同步删除键：`suggestOutfit`、`pairings`、`familyFeed`、`aiLearning`、`family`、`notifications`。两个文件键集必须一致。

- [ ] **Step 3: 校验**

Run: `cd frontend && npm run i18n:check && npm test && npx tsc --noEmit`
Expected: 全 PASS。`i18n:keys --orphans` 若列出被摘页面文件（`app/dashboard/suggest/page.tsx` 等）仍在引用的 namespace 键（suggest/pairings/family/notifications/learning），**不处理**——页面文件摘不删保留，其键仍被引用属正常。

- [ ] **Step 4: 提交**

```bash
git add frontend/components/sidebar.tsx frontend/components/mobile-sidebar.tsx frontend/components/mobile-nav.tsx frontend/messages/en/nav.json frontend/messages/zh-CN/nav.json
git commit -m "refactor(ui): drop product-shell entries from navigation (pages kept)

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 11: 运行时词表 API（增改写回 JSON + vocabulary.md）

**Files:**
- Create: `backend/app/api/vocabulary.py`
- Create: `backend/app/utils/vocabulary_md.py`
- Create: `backend/app/utils/pinyin.py`
- Modify: `backend/app/api/router.py`（挂载）
- Create: `backend/tests/test_vocabulary_api.py`
- Create: `backend/tests/test_vocabulary_md.py`

**Interfaces:**
- Consumes: v2 JSON（Task 1）、loader 常量（Task 2）、`pypinyin`（Task 1）
- Produces:
  - `GET /api/v1/vocabulary` → 完整 v2 JSON（同构）
  - `POST /api/v1/vocabulary/types` `{value,label,body_part}` → 新类别（限定 7 部位）
  - `POST /api/v1/vocabulary/colors/values` `{value,label,family,hex}` → 新具体色（hex 必填）
  - `POST /api/v1/vocabulary/colors/families` `{value,label}` → 新色系
  - `POST /api/v1/vocabulary/styles` `{value,label}` → 新风格
  - `PATCH /api/v1/vocabulary/{kind}/{value}` `{label?, disabled?}` → 改名（只改 label）/停用
  - `pinyin_sort_key(label: str) -> str`（`backend/app/utils/pinyin.py`）
  - `sync_row(md_path, kind, entry)` / `mark_disabled(md_path, kind, value)`（`backend/app/utils/vocabulary_md.py`）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_vocabulary_md.py`：

```python
from pathlib import Path

from app.utils.vocabulary_md import mark_disabled, sync_row


SAMPLE = """## 五、风格 `styles`（可随时增行）

| slug | 中文名 | 备注 |
|------|--------|------|
| casual | 休闲 | |
| retro | 复古 | |
"""


def test_sync_row_appends_in_pinyin_position(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(SAMPLE, encoding="utf-8")
    sync_row(md, "styles", {"value": "goth", "label": "哥特"})
    text = md.read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.startswith("| goth") or ln.startswith("| casual") or ln.startswith("| retro")]
    assert lines == ["| casual | 休闲 | |", "| goth | 哥特 | |", "| retro | 复古 | |"]


def test_sync_row_rewrites_existing_value(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(SAMPLE, encoding="utf-8")
    sync_row(md, "styles", {"value": "retro", "label": "复古风"})
    text = md.read_text(encoding="utf-8")
    assert "| retro | 复古风 | |" in text
    assert text.count("| retro |") == 1


def test_mark_disabled_flags_the_row(tmp_path: Path):
    md = tmp_path / "vocabulary.md"
    md.write_text(SAMPLE, encoding="utf-8")
    mark_disabled(md, "styles", "retro")
    text = md.read_text(encoding="utf-8")
    assert "已停用" in text
```

创建 `backend/tests/test_vocabulary_api.py`：

```python
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "backend" / "app" / "data" / "garment_vocabulary.json"
MD_PATH = ROOT / "docs" / "specs" / "vocabulary.md"


@pytest.fixture()
def vocab_snapshot():
    before_json = JSON_PATH.read_text(encoding="utf-8")
    before_md = MD_PATH.read_text(encoding="utf-8")
    yield
    JSON_PATH.write_text(before_json, encoding="utf-8")
    MD_PATH.write_text(before_md, encoding="utf-8")


class TestVocabularyApi:
    async def test_get_vocabulary(self, client, auth_headers):
        resp = await client.get("/api/v1/vocabulary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["body_parts"]) == 7
        assert len(data["colors"]["values"]) == 48

    async def test_add_style_writes_json_and_md(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/styles",
            json={"value": "y2k", "label": "Y2K"},
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), resp.text
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        assert any(s["value"] == "y2k" for s in data["styles"])
        assert "y2k" in MD_PATH.read_text(encoding="utf-8")

    async def test_add_color_requires_hex(self, client, auth_headers, vocab_snapshot):
        bad = await client.post(
            "/api/v1/vocabulary/colors/values",
            json={"value": "haze", "label": "雾色", "family": "blue"},
            headers=auth_headers,
        )
        assert bad.status_code == 422
        good = await client.post(
            "/api/v1/vocabulary/colors/values",
            json={"value": "haze", "label": "雾色", "family": "blue", "hex": "#8fa9bf"},
            headers=auth_headers,
        )
        assert good.status_code in (200, 201)

    async def test_add_type_rejects_unknown_body_part(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/types",
            json={"value": "hoodie-dress", "label": "卫衣裙", "body_part": "unknown"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_duplicate_slug_rejected(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/styles",
            json={"value": "casual", "label": "休闲2"},
            headers=auth_headers,
        )
        assert resp.status_code == 409

    async def test_rename_and_disable(self, client, auth_headers, vocab_snapshot):
        rename = await client.patch(
            "/api/v1/vocabulary/styles/casual",
            json={"label": "休闲风"},
            headers=auth_headers,
        )
        assert rename.status_code == 200
        disable = await client.patch(
            "/api/v1/vocabulary/styles/casual",
            json={"disabled": True},
            headers=auth_headers,
        )
        assert disable.status_code == 200
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        entry = next(s for s in data["styles"] if s["value"] == "casual")
        assert entry["label"] == "休闲风" and entry.get("disabled") is True

    async def test_materials_and_formality_are_closed(self, client, auth_headers, vocab_snapshot):
        resp = await client.post(
            "/api/v1/vocabulary/materials",
            json={"value": "cashmere", "label": "羊绒"},
            headers=auth_headers,
        )
        assert resp.status_code in (404, 405)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `docker compose exec backend python -m pytest tests/test_vocabulary_api.py tests/test_vocabulary_md.py -v`
Expected: FAIL——模块/路由不存在。

- [ ] **Step 3: 实现工具与 API**

创建 `backend/app/utils/pinyin.py`：

```python
"""Pinyin sort helpers — the vocabulary is ordered by Chinese-name pinyin."""
from pypinyin import lazy_pinyin


def pinyin_sort_key(label: str) -> str:
    return "".join(lazy_pinyin(label))
```

创建 `backend/app/utils/vocabulary_md.py`（sync_row/mark_disabled 的最小实现）：

```python
"""Append/update/disable rows in the human-edited docs/specs/vocabulary.md tables."""
from __future__ import annotations

from pathlib import Path

from app.utils.pinyin import pinyin_sort_key

SECTION_TITLES = {
    "styles": "## 五、风格",
    "types": "## 一、类型",
    "colors": "## 二、颜色",
}


def _find_table_region(lines: list[str], kind: str, family: str | None = None) -> tuple[int, int]:
    """Return [start, end) line-index range of the target table body rows."""
    title = SECTION_TITLES[kind]
    start = next(i for i, ln in enumerate(lines) if ln.startswith(title))
    if kind == "types" or kind == "colors":
        heading = f"### "
        part_start = None
        for i in range(start, len(lines)):
            if lines[i].startswith(heading) and (family is None or f"`{family}`" in lines[i]):
                part_start = i
                if family is not None:
                    break
        start = part_start if part_start is not None else start
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("### ") or lines[i].startswith("## "):
            end = i
            break
    table_rows = [i for i in range(start, end) if lines[i].startswith("|") and "slug" not in lines[i] and not lines[i].startswith("|--")]
    return table_rows[0], table_rows[-1] + 1


def sync_row(md_path: Path, kind: str, entry: dict, family: str | None = None) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    lo, hi = _find_table_region(lines, kind, family)
    value = entry["value"]
    label = entry["label"]
    if kind == "colors":
        row = f"| {value} | {label} | `{entry['hex']}` |"
    else:
        row = f"| {value} | {label} | |"
    existing = [i for i in range(lo, hi) if lines[i].startswith(f"| {value} ")]
    if existing:
        lines[existing[0]] = row
    else:
        entries = []
        for i in range(lo, hi):
            cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            entries.append((pinyin_sort_key(cells[1]), i))
        entries.append((pinyin_sort_key(label), None))
        insert_at = hi
        for key, i in sorted(entries, key=lambda e: e[0]):
            if i is None:
                break
            insert_at = i + 1
        lines.insert(insert_at, row)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def mark_disabled(md_path: Path, kind: str, value: str, family: str | None = None) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    lo, hi = _find_table_region(lines, kind, family)
    for i in range(lo, hi):
        if lines[i].startswith(f"| {value} "):
            lines[i] = lines[i].replace("| |", "| 已停用 |") if lines[i].count("| |") == 1 else lines[i] + " 已停用"
            break
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

（若 `_find_table_region` 对颜色表的多色系定位在测试里暴露歧义——同名 `###` 多段——就给 `sync_row` 显式传 `family`，API 层从请求体带上。）

创建 `backend/app/api/vocabulary.py`：

```python
"""Runtime vocabulary: read the whole vocab; add/rename/disable soft entries."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.utils.auth import get_current_user
from app.utils.pinyin import pinyin_sort_key
from app.utils.vocabulary_md import mark_disabled, sync_row

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])

ROOT = Path(__file__).resolve().parents[3]
JSON_PATH = ROOT / "backend" / "app" / "data" / "garment_vocabulary.json"
MD_PATH = ROOT / "docs" / "specs" / "vocabulary.md"
BODY_PART_VALUES = {"dresses", "accessories", "tops", "jewelry", "outerwear", "bottoms", "footwear"}


class StyleIn(BaseModel):
    value: str = Field(pattern=r"^[a-z0-9-]+$")
    label: str


class ColorValueIn(BaseModel):
    value: str = Field(pattern=r"^[a-z0-9-]+$")
    label: str
    family: str
    hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class TypeIn(BaseModel):
    value: str = Field(pattern=r"^[a-z0-9-]+$")
    label: str
    body_part: str


class PatchIn(BaseModel):
    label: str | None = None
    disabled: bool | None = None


def _load() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    JSON_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _insert_pinyin(entries: list[dict], entry: dict) -> None:
    key = pinyin_sort_key(entry["label"])
    idx = next(
        (i for i, e in enumerate(entries) if pinyin_sort_key(e["label"]) > key),
        len(entries),
    )
    entries.insert(idx, entry)


@router.get("")
async def get_vocabulary(current_user: Annotated[object, Depends(get_current_user)]) -> dict:
    return _load()


@router.post("/styles", status_code=201)
async def add_style(
    body: StyleIn, current_user: Annotated[object, Depends(get_current_user)]
) -> dict:
    data = _load()
    if any(s["value"] == body.value for s in data["styles"]):
        raise HTTPException(status_code=409, detail="slug exists")
    entry = {"value": body.value, "label": body.label}
    _insert_pinyin(data["styles"], entry)
    _save(data)
    sync_row(MD_PATH, "styles", entry)
    return entry


@router.post("/colors/values", status_code=201)
async def add_color_value(
    body: ColorValueIn, current_user: Annotated[object, Depends(get_current_user)]
) -> dict:
    data = _load()
    if any(c["value"] == body.value for c in data["colors"]["values"]):
        raise HTTPException(status_code=409, detail="slug exists")
    if not any(f["value"] == body.family for f in data["colors"]["families"]):
        raise HTTPException(status_code=422, detail="unknown family")
    entry = {"value": body.value, "label": body.label, "family": body.family, "hex": body.hex.lower()}
    values = [c for c in data["colors"]["values"] if c["family"] == body.family]
    _insert_pinyin(values, entry)
    data["colors"]["values"] = [
        c for c in data["colors"]["values"] if c["family"] != body.family
    ] + values
    _save(data)
    sync_row(MD_PATH, "colors", entry, family=body.family)
    return entry


@router.post("/colors/families", status_code=201)
async def add_color_family(
    body: StyleIn, current_user: Annotated[object, Depends(get_current_user)]
) -> dict:
    data = _load()
    if any(f["value"] == body.value for f in data["colors"]["families"]):
        raise HTTPException(status_code=409, detail="slug exists")
    entry = {"value": body.value, "label": body.label}
    _insert_pinyin(data["colors"]["families"], entry)
    _save(data)
    return entry


@router.post("/types", status_code=201)
async def add_type(
    body: TypeIn, current_user: Annotated[object, Depends(get_current_user)]
) -> dict:
    data = _load()
    if body.body_part not in BODY_PART_VALUES:
        raise HTTPException(status_code=422, detail="unknown body_part")
    if any(t["value"] == body.value for t in data["types"]):
        raise HTTPException(status_code=409, detail="slug exists")
    entry = {
        "value": body.value, "label": body.label, "body_part": body.body_part,
        "role": "accessory", "wash_interval": 3,
    }
    part_types = [t for t in data["types"] if t["body_part"] == body.body_part]
    _insert_pinyin(part_types, entry)
    data["types"] = [t for t in data["types"] if t["body_part"] != body.body_part] + part_types
    _save(data)
    sync_row(MD_PATH, "types", entry, family=body.body_part)
    return entry


@router.patch("/{kind}/{value}")
async def patch_entry(
    kind: Literal["styles", "types", "colors"],
    value: str,
    body: PatchIn,
    current_user: Annotated[object, Depends(get_current_user)],
) -> dict:
    data = _load()
    bucket = data["styles"] if kind == "styles" else (
        data["types"] if kind == "types" else data["colors"]["values"]
    )
    entry = next((e for e in bucket if e["value"] == value), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown entry")
    if body.label is not None:
        entry["label"] = body.label
        sync_row(MD_PATH, "types" if kind == "colors" else kind, entry,
                 family=entry.get("family") or entry.get("body_part"))
    if body.disabled is not None:
        entry["disabled"] = body.disabled
        if body.disabled:
            mark_disabled(MD_PATH, "types" if kind == "colors" else kind, value,
                          family=entry.get("family") or entry.get("body_part"))
    _save(data)
    return entry
```

在 `backend/app/api/router.py` 的 include 列表（items 之后）追加：

```python
from app.api import vocabulary
...
router.include_router(vocabulary.router)
```

注意 `patch_entry` 里 kind 到 md 分区的映射（colors 的行在色系表里）按 `vocabulary_md._find_table_region` 的 family 参数走。

- [ ] **Step 4: 跑测试确认通过**

Run: `docker compose exec backend python -m pytest tests/test_vocabulary_api.py tests/test_vocabulary_md.py tests/test_vocabulary_compiler.py -v`
Expected: PASS。注意 test_vocabulary_api 的 fixture 会在用例后还原两个文件，跑完 `python scripts/compile_vocabulary.py --check` 仍应 OK（还原保证幂等）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/vocabulary.py backend/app/utils/vocabulary_md.py backend/app/utils/pinyin.py backend/app/api/router.py backend/tests/test_vocabulary_api.py backend/tests/test_vocabulary_md.py
git commit -m "feat(vocab): runtime vocabulary API with JSON+markdown write-back

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 12: 前端运行时词表 + 选择器「添加/改名/停用」

**Files:**
- Create: `frontend/lib/hooks/use-vocabulary.ts`
- Create: `frontend/components/vocab-add-dialog.tsx`
- Modify: `frontend/lib/hooks/use-translated-constants.ts`
- Create: `frontend/tests/use-vocabulary.test.ts`

**Interfaces:**
- Consumes: Task 11 的 `/api/v1/vocabulary` 端点；Task 3 的生成导出（离线兜底）
- Produces: `useVocabulary()` → `UseQueryResult<Vocabulary>`（`['vocabulary']` 键）；`useAddStyle()`/`useAddColorValue()`/`useAddType()`/`usePatchVocabulary()` mutation（成功后 `invalidateQueries(['vocabulary'])`）；`Vocabulary` 类型 = v2 JSON 形状。选择器数据源从生成物切到运行时（生成物做兜底初始值）。

- [ ] **Step 1: 写失败测试**

创建 `frontend/tests/use-vocabulary.test.ts`（照 `frontend/tests/hooks.test.ts` 的 `renderHook` + QueryClientProvider + `vi.mocked(global.fetch)` 风格）：

```ts
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useVocabulary } from '@/lib/hooks/use-vocabulary';

describe('useVocabulary', () => {
  it('fetches the runtime vocabulary', async () => {
    const payload = { body_parts: [], types: [], colors: { families: [], values: [] },
      seasons: [], styles: [], materials: [], formality: [] };
    vi.mocked(global.fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => payload,
    } as Response);

    const client = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useVocabulary(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(payload);
  });
});
```

（`global.fetch` 的 mock 方式与 `tests/setup.ts` 既有配置对齐；`api.get('/vocabulary')` 走 `/api/v1/vocabulary`。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npm test -- use-vocabulary`
Expected: FAIL——模块不存在。

- [ ] **Step 3: 实现 hooks 与添加对话框**

创建 `frontend/lib/hooks/use-vocabulary.ts`：

```ts
'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

export interface VocabEntry {
  value: string;
  label: string;
  disabled?: boolean;
}
export interface ColorEntry extends VocabEntry {
  family: string;
  hex: string;
}
export interface TypeEntry extends VocabEntry {
  body_part: string;
  role?: string;
  wash_interval?: number;
}
export interface Vocabulary {
  body_parts: VocabEntry[];
  types: TypeEntry[];
  colors: { families: VocabEntry[]; values: ColorEntry[] };
  seasons: VocabEntry[];
  styles: VocabEntry[];
  materials: string[];
  formality: string[];
}

export function useVocabulary() {
  return useQuery({
    queryKey: ['vocabulary'],
    queryFn: () => api.get<Vocabulary>('/vocabulary'),
    staleTime: 5 * 60 * 1000,
  });
}

function useInvalidate() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ['vocabulary'] });
}

export function useAddStyle() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { value: string; label: string }) => api.post('/vocabulary/styles', body),
    onSuccess: invalidate,
  });
}

export function useAddColorValue() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { value: string; label: string; family: string; hex: string }) =>
      api.post('/vocabulary/colors/values', body),
    onSuccess: invalidate,
  });
}

export function useAddType() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: { value: string; label: string; body_part: string }) =>
      api.post('/vocabulary/types', body),
    onSuccess: invalidate,
  });
}

export function usePatchVocabulary() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (args: {
      kind: 'styles' | 'types' | 'colors';
      value: string;
      label?: string;
      disabled?: boolean;
    }) => {
      const { kind, value, ...body } = args;
      return api.patch(`/vocabulary/${kind}/${value}`, body);
    },
    onSuccess: invalidate,
  });
}
```

创建 `frontend/components/vocab-add-dialog.tsx`：一个受控对话框（shadcn Dialog 沿用仓库现有组件用法），props：

```ts
interface VocabAddDialogProps {
  kind: 'styles' | 'types' | 'colors';
  open: boolean;
  onOpenChange: (open: boolean) => void;
  family?: string;       // colors: 目标色系；types: 目标部位
}
```

表单字段：显示名（label）、slug（value，`^[a-z0-9-]+$`，前端提示小写连字符）、颜色多一个 hex 输入（`<input type="color">` 色板 + hex 文本框联动，hex 必填）。提交走对应 mutation，成功后关窗；失败（409/422）显示错误文案（走 `t('wardrobe.vocabSlugExists')` 等新键，en+zh-CN 都加）。

`frontend/lib/hooks/use-translated-constants.ts`：`useClothingTypes`/`useClothingColors`/`useStyles` 的数据源改为——`useVocabulary()` 有数据用数据，`isLoading` 期间回落到生成导出（`TYPE_ENTRIES`/`COLOR_VALUES`/`STYLE_LABELS`）。每个选择器列表尾部追加一个「添加…」项，点击打开 `VocabAddDialog`（选中已有项的改名/停用入口放 hover 菜单，调 `usePatchVocabulary`）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npm test && npm run i18n:check && npx tsc --noEmit`
Expected: 全 PASS。手动冒烟：`docker compose up` 后在表单里添加一个风格「Y2K」→ 选择器立即出现该选项 → `backend/app/data/garment_vocabulary.json` 与 `docs/specs/vocabulary.md` 都出现新行（按拼音位）。

- [ ] **Step 5: 提交**

```bash
git add frontend/lib/hooks/use-vocabulary.ts frontend/components/vocab-add-dialog.tsx frontend/lib/hooks/use-translated-constants.ts frontend/tests/use-vocabulary.test.ts frontend/messages/en/wardrobe.json frontend/messages/zh-CN/wardrobe.json
git commit -m "feat(vocab): runtime vocabulary hooks and add/rename/disable picker actions

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 13: 全量回归 + 文档收尾

**Files:**
- Modify: `README.md`、`CONTRIBUTING.md`（词表/裁剪/迁移说明）
- Modify: `docs/specs/personal-wardrobe-spec.md`（若实现中发现 spec 需补口径，在 §10 追加声明）

**Interfaces:**
- Consumes: Task 1–12 全部产出
- Produces: 全绿的后端 pytest、前端 vitest/i18n/vocab/tsc、migration heads 检查；文档与实现一致。

- [ ] **Step 1: 后端全量**

Run: `docker compose exec backend python -m pytest tests/ -v --tb=short`
Expected: PASS。失败逐个修复（常见：被摘路由的旧用例未进 `tests/pruned/`、schema 影响 studio/outfits 的字段引用）。

- [ ] **Step 2: 前端全量**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run i18n:check && npm run vocab:check && npm test -- --run`
Expected: 全 PASS / `vocab-check: OK`。

- [ ] **Step 3: 迁移与编译幂等**

Run: `docker compose exec backend python scripts/check_migration_heads.py`
Run: `docker compose exec backend python scripts/compile_vocabulary.py --check`
Expected: 唯一 head；`vocabulary-compile: OK`。

- [ ] **Step 4: 词表 JSON 运行时持久化**

词表 JSON 运行时可写且重启不丢（软词表写回只改容器内文件的话，重建镜像即丢）。`docker-compose.dev.yml` 与 `docker-compose.yml` 的 backend 服务确认/追加数据目录挂载（JSON 所在目录必须是 volume，不是镜像层）：

```yaml
    volumes:
      - ./backend/app/data:/app/app/data
```

（若 backend 容器工作目录不是 `/app`，按 `docker compose exec backend pwd` 实际路径对齐。）

Run: `docker compose exec backend python -c "from pathlib import Path; p = Path('app/data/garment_vocabulary.json'); p.write_text(p.read_text(encoding='utf-8'), encoding='utf-8'); print('writable')"`
Expected: `writable`（无权限错误）。README 备份清单（Step 5 里写）把 `garment_vocabulary.json` 与数据库 dump、`storage_path` 并列。

- [ ] **Step 5: 文档更新**

`README.md`：
1. 开发流程段补：词表双文件编辑流（改 `docs/specs/vocabulary.md` → `python scripts/compile_vocabulary.py` → `cd frontend && npm run vocab:gen`）。
2. 迁移段补一行：`docker compose exec backend alembic upgrade head`（已有则确认涵盖新 head）。
3. 功能列表里 families/notifications/learning/wash/suggest 标注「已下线/休眠（代码保留）」。

`CONTRIBUTING.md` 的 "Garment vocabulary" 节改写：单一数据源现为 `docs/specs/vocabulary.md`（人工编辑面）→ `garment_vocabulary.json`（运行时）→ 生成 TS；软词表 UI 增改写回两处；`vocab:check` 与 `compile_vocabulary.py --check` 双护栏。

- [ ] **Step 6: 冒烟**

Run: `docker compose up`，走一遍：登录（dev 模式）→ 衣橱页（默认只见在役）→ 加一件（两级类型、主辅色多选、风格、温度、购买年月、价格）→ 详情编辑 → 标已退役 → 筛「已退役」可见带标注 → 设置页正常、导航无产品壳入口。

Expected: 全流程可用；无 500、无空白选择器。

- [ ] **Step 7: 提交**

```bash
git add README.md CONTRIBUTING.md docs/specs/personal-wardrobe-spec.md docker-compose.dev.yml docker-compose.yml
git commit -m "docs: reflect vocabulary single-source and product-shell pruning

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```
