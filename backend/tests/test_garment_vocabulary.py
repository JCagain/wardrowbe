import json
import re

import pytest

from app.services.item_scorer import (
    FORMALITY_ORDER,
    HEAVY_LAYER_MATERIALS,
    HEAVY_LAYER_TYPES,
    OCCASION_FORMALITY,
    RAIN_LAYER_TYPES,
    WARM_LAYER_TYPES,
)
from app.utils import garment_vocabulary as gv
from app.utils.clothing import _CANONICAL_ROLE_ORDER
from app.utils.garment_vocabulary import (
    DEFAULT_WASH_INTERVALS,
    FORMALITY,
    ITEM_ROLE,
    MATERIALS,
    TYPES,
    render_tagging_prompt,
)
from app.utils.prompts import load_prompt


def _prompt_options(heading: str) -> set[str]:
    prompt = render_tagging_prompt(load_prompt("clothing_analysis"))
    match = re.search(rf"^{heading} \([^)]*\):\n(.+)\n", prompt, re.MULTILINE)
    assert match, f"{heading} line not found in clothing_analysis prompt"
    return {term.strip() for term in match.group(1).split(",")}


def test_vocabulary_entries_are_unique():
    assert len(set(TYPES)) == len(TYPES)
    assert len(set(MATERIALS)) == len(MATERIALS)
    assert len(set(FORMALITY)) == len(FORMALITY)


def test_every_type_has_a_known_role_and_a_positive_wash_interval():
    assert set(ITEM_ROLE.values()) <= set(_CANONICAL_ROLE_ORDER)
    assert all(interval > 0 for interval in DEFAULT_WASH_INTERVALS.values())


def test_prompt_template_tokens_are_all_rendered():
    template = load_prompt("clothing_analysis")
    for token in ("<<TYPES>>", "<<MATERIALS>>", "<<FORMALITY>>"):
        assert token in template
    assert "<<" not in render_tagging_prompt(template)


def test_type_lists_agree():
    prompt_types = _prompt_options("TYPE")
    assert prompt_types == set(gv.TYPES)
    assert prompt_types == set(ITEM_ROLE)
    assert prompt_types == set(DEFAULT_WASH_INTERVALS)


@pytest.mark.parametrize(
    ("heading", "vocabulary"),
    [("MATERIAL", set(gv.MATERIALS)), ("FORMALITY", set(gv.FORMALITY))],
)
def test_prompt_offers_exactly_the_validated_vocabulary(heading, vocabulary):
    assert _prompt_options(heading) == vocabulary


def test_scorer_formality_scale_is_the_validated_vocabulary():
    assert set(FORMALITY_ORDER) == set(gv.FORMALITY)
    for occasion, formalities in OCCASION_FORMALITY.items():
        assert set(formalities) <= set(gv.FORMALITY), occasion


def test_scorer_layer_types_are_real_types():
    scorer_types = RAIN_LAYER_TYPES | WARM_LAYER_TYPES | HEAVY_LAYER_TYPES
    assert scorer_types <= set(gv.TYPES)


def test_scorer_heavy_materials_are_real_materials():
    assert HEAVY_LAYER_MATERIALS <= set(gv.MATERIALS)


def test_v2_sections_are_loaded():
    from app.utils import garment_vocabulary as gv

    assert len(gv.BODY_PARTS) == 7
    assert len(gv.TYPE_LABELS) == 52
    assert len(gv.COLOR_FAMILIES) == 9
    assert len(gv.COLOR_VALUES) == 48
    assert len(gv.STYLE_VALUES) == 11
    assert set(gv.SEASON_VALUES) == {"spring", "summer", "fall", "winter", "all-season"}
    assert gv.BODY_PART_BY_TYPE["tank-top"] == "tops"
    assert gv.BODY_PART_BY_TYPE["necklace"] == "jewelry"
    assert set(gv.TYPES_BY_PART) == {p["value"] for p in gv.BODY_PARTS}
    assert sum(len(v) for v in gv.TYPES_BY_PART.values()) == 52


def test_render_tagging_prompt_renders_new_tokens():
    from app.utils.garment_vocabulary import render_tagging_prompt

    rendered = render_tagging_prompt(
        "<<BODY_PARTS>>|<<TYPES>>|<<COLORS>>|<<STYLES>>|<<SEASONS>>|<<MATERIALS>>|<<FORMALITY>>"
    )
    assert "<<" not in rendered
    # Assert on value slugs (what render_tagging_prompt projects); 军绿/泛三坑 are the labels of army/three-pits.
    assert "army" in rendered and "three-pits" in rendered and "all-season" in rendered


def test_every_color_slug_is_unique_and_hex_is_lowercase():
    from app.utils import garment_vocabulary as gv

    values = [c["value"] for c in gv.COLOR_VALUES]
    assert len(values) == len(set(values))
    for c in gv.COLOR_VALUES:
        assert c["hex"] == c["hex"].lower()


def test_ai_validation_sets_come_from_the_vocabulary():
    """ai_service accepts values the vocabulary defines.

    Its validation sets are no longer module snapshots (VALID_* are gone); they
    are resolved per call in _parse_tags_from_response from the same gv names,
    so a vocabulary value must pass through that real path untouched. The
    freshness pins in test_vocabulary_api.py cover the runtime-write side.
    """
    from app.services.ai_service import AIService

    color = sorted(gv.ACTIVE_COLOR_VALUE_SET)[0]
    style = gv.ACTIVE_STYLE_VALUES[0]
    season = gv.SEASON_VALUES[0]
    tags = AIService()._parse_tags_from_response(
        json.dumps(
            {
                "type": "shirt",
                "primary_colors": [color],
                "secondary_colors": [],
                "style": [style],
                "season": [season],
            }
        )
    )
    assert tags.primary_colors == [color]
    assert tags.secondary_colors == []
    assert tags.style == [style]
    assert tags.season == [season]


def test_legacy_color_aliases_point_at_new_slugs():
    from app.services.ai_service import LEGACY_COLOR_ALIASES
    from app.utils.garment_vocabulary import COLOR_VALUE_SET

    assert set(LEGACY_COLOR_ALIASES.values()) <= COLOR_VALUE_SET
    assert LEGACY_COLOR_ALIASES["burgundy"] == "wine"
    assert LEGACY_COLOR_ALIASES["tan"] == "camel"
    assert LEGACY_COLOR_ALIASES["beige"] == "khaki"
    assert LEGACY_COLOR_ALIASES["light-blue"] == "sky"


def _write_vocab(path, data):
    import os

    before = path.stat().st_mtime_ns
    path.write_text(json.dumps(data, ensure_ascii=False))
    # lru_cache is keyed on mtime_ns: guarantee it advances on coarse clocks.
    if path.stat().st_mtime_ns <= before:
        os.utime(path, ns=(before + 1_000_000, before + 1_000_000))


def test_prompt_lists_every_active_color_style_season_with_labels(vocab_file):
    from pathlib import Path

    template = (
        Path(gv.__file__).parent.parent / "prompts" / "clothing_analysis.txt"
    ).read_text()
    prompt = render_tagging_prompt(template)
    data = json.loads(vocab_file.read_text())
    for c in data["colors"]["values"]:
        if not c.get("disabled"):
            assert f'{c["value"]}={c["label"]}' in prompt
    for s in data["styles"]:
        if not s.get("disabled"):
            assert f'{s["value"]}={s["label"]}' in prompt
    for s in data["seasons"]:
        assert f'{s["value"]}={s["label"]}' in prompt
    # 旧硬编码列表彻底消失
    # Only for values the vocabulary does not (now) contain: a user may later add
    # e.g. a `preppy` style, which must not turn this red.
    current = {c["value"] for c in data["colors"]["values"]}
    current |= {s["value"] for s in data["styles"]}
    current |= {s["value"] for s in data["seasons"]}
    current |= {t["value"] for t in data["types"]}
    current |= set(data["materials"]) | set(data["formality"])
    for legacy in ("light-blue", "burgundy", "bohemian", "preppy", "rugged"):
        if legacy not in current:
            assert legacy not in prompt
    assert "<<" not in prompt


def test_disabled_entries_never_reach_the_prompt_or_active_sets(vocab_file):
    data = json.loads(vocab_file.read_text())
    color = data["colors"]["values"][0]
    style = data["styles"][0]
    typ = data["types"][0]
    for e in (color, style, typ):
        e["disabled"] = True
    _write_vocab(vocab_file, data)

    assert color["value"] not in gv.ACTIVE_COLOR_VALUE_SET
    assert style["value"] not in gv.ACTIVE_STYLE_VALUES
    assert typ["value"] not in gv.ACTIVE_TYPES
    # 历史值集合不受影响（手改/旧数据仍可显示）
    assert color["value"] in gv.COLOR_VALUE_SET

    prompt = gv.render_tagging_prompt("<<COLORS_BY_FAMILY>>|<<STYLES_LABELED>>|<<TYPES>>")
    assert f'{color["value"]}=' not in prompt
    assert f'{style["value"]}=' not in prompt
    assert typ["value"] not in prompt.split("|")[2].split(", ")


def test_runtime_added_color_reaches_the_prompt_without_restart(vocab_file):
    # D1：写入即生效
    data = json.loads(vocab_file.read_text())
    data["colors"]["values"].append(
        {"value": "test-mint", "label": "测薄荷", "family": "green", "hex": "#aaffcc"}
    )
    _write_vocab(vocab_file, data)
    assert "test-mint=测薄荷" in gv.render_tagging_prompt("<<COLORS_BY_FAMILY>>")
