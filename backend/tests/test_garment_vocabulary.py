import re

import pytest

from app.schemas.item import DEFAULT_WASH_INTERVALS
from app.services.ai_service import TAGGING_PROMPT, VALID_FORMALITY, VALID_MATERIALS, VALID_TYPES
from app.services.item_scorer import (
    FORMALITY_ORDER,
    HEAVY_LAYER_MATERIALS,
    HEAVY_LAYER_TYPES,
    OCCASION_FORMALITY,
    RAIN_LAYER_TYPES,
    WARM_LAYER_TYPES,
)
from app.utils.clothing import _CANONICAL_ROLE_ORDER, ITEM_ROLE
from app.utils.garment_vocabulary import (
    FORMALITY,
    MATERIALS,
    TYPES,
    render_tagging_prompt,
)
from app.utils.prompts import load_prompt


def _prompt_options(heading: str) -> set[str]:
    match = re.search(rf"^{heading} \([^)]*\):\n(.+)\n", TAGGING_PROMPT, re.MULTILINE)
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
    assert prompt_types == VALID_TYPES
    assert prompt_types == set(ITEM_ROLE)
    assert prompt_types == set(DEFAULT_WASH_INTERVALS)


@pytest.mark.parametrize(
    ("heading", "vocabulary"),
    [("MATERIAL", VALID_MATERIALS), ("FORMALITY", VALID_FORMALITY)],
)
def test_prompt_offers_exactly_the_validated_vocabulary(heading, vocabulary):
    assert _prompt_options(heading) == vocabulary


def test_scorer_formality_scale_is_the_validated_vocabulary():
    assert set(FORMALITY_ORDER) == VALID_FORMALITY
    for occasion, formalities in OCCASION_FORMALITY.items():
        assert set(formalities) <= VALID_FORMALITY, occasion


def test_scorer_layer_types_are_real_types():
    scorer_types = RAIN_LAYER_TYPES | WARM_LAYER_TYPES | HEAVY_LAYER_TYPES
    assert scorer_types <= VALID_TYPES


def test_scorer_heavy_materials_are_real_materials():
    assert HEAVY_LAYER_MATERIALS <= VALID_MATERIALS


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
    # Assert on value slugs (what render_tagging_prompt projects); 军绿/泛三坑 are the labels of army/three-pits.
    assert "army" in rendered and "three-pits" in rendered and "all-season" in rendered


def test_every_color_slug_is_unique_and_hex_is_lowercase():
    from app.utils import garment_vocabulary as gv

    values = [c["value"] for c in gv.COLOR_VALUES]
    assert len(values) == len(set(values))
    for c in gv.COLOR_VALUES:
        assert c["hex"] == c["hex"].lower()
