"""Backend role / wash lookups must see types added to the vocabulary at runtime
(fixes #54: vocabulary edits take effect without a restart)."""

import json
from uuid import uuid4

import pytest

from app.schemas.item import ItemResponse
from app.utils.clothing import (
    canonical_item_order,
    count_composition,
    deduplicate_by_body_slot,
    role_for_type,
)


@pytest.fixture
def runtime_types(vocab_file):
    """Add two types after the modules above were imported, as the vocabulary API would."""
    data = json.loads(vocab_file.read_text())
    data["types"] += [
        {"value": "tabi-boots", "label": "x", "body_part": "footwear", "role": "footwear", "wash_interval": 20},
        {"value": "smock-top", "label": "y", "body_part": "tops", "role": "base_top", "wash_interval": 2},
    ]
    vocab_file.write_text(json.dumps(data, ensure_ascii=False))
    return vocab_file


def test_role_for_type_sees_runtime_type(runtime_types):
    assert role_for_type("tabi-boots") == "footwear"
    assert role_for_type("no-such-type") is None


def test_canonical_order_places_runtime_type_by_role(runtime_types):
    boots, shirt = uuid4(), uuid4()
    order = canonical_item_order([boots, shirt], {boots: "tabi-boots", shirt: "shirt"})
    assert order == [shirt, boots]


def test_dedup_treats_runtime_type_as_its_slot(runtime_types):
    shirt, smock = uuid4(), uuid4()
    kept = deduplicate_by_body_slot([shirt, smock], {shirt: "shirt", smock: "smock-top"})
    assert kept == [shirt]


def test_composition_counts_runtime_type(runtime_types):
    assert count_composition([("smock-top", 2)]).base_tops == 2


def test_effective_wash_interval_uses_runtime_default(runtime_types):
    item = ItemResponse.model_construct(type="tabi-boots", wash_interval=None)
    assert item.effective_wash_interval == 20
