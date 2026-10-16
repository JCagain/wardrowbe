from uuid import uuid4

import numpy as np
import pytest

from app.models.item import ClothingItem, ItemStatus
from app.services.embedding_recall import load_candidates, top_k
from app.services.embedding_store import upsert_embedding
from app.utils.item_lifecycle import terminal_status


def _u(*xs):
    v = np.asarray(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_top_k_orders_by_cosine_and_truncates():
    a, b, c = uuid4(), uuid4(), uuid4()
    cands = [(a, list(_u(1, 0))), (b, list(_u(0.6, 0.8))), (c, list(_u(0, 1)))]
    ranked = top_k(np.array([2.0, 0.0]), cands, k=2)
    assert [r[0] for r in ranked] == [a, b]
    assert ranked[0][1] == pytest.approx(1.0)


def test_top_k_skips_dim_mismatch_and_handles_degenerate():
    a, b = uuid4(), uuid4()
    cands = [(a, [1.0, 0.0, 0.0]), (b, list(_u(1, 0)))]
    assert [r[0] for r in top_k(np.array([1.0, 0.0]), cands, k=5)] == [b]
    assert top_k(np.zeros(2), cands, k=5) == []
    assert top_k(np.array([1.0, 0.0]), cands, k=0) == []
    assert top_k(np.array([1.0, 0.0]), [], k=3) == []


def test_top_k_ties_keep_input_order():
    a, b = uuid4(), uuid4()
    v = list(_u(1, 1))
    assert [r[0] for r in top_k(np.array([1.0, 1.0]), [(a, v), (b, v)], k=2)] == [a, b]


@pytest.mark.asyncio
async def test_load_candidates_filters_user_model_and_part(db_session, test_user):
    from app.models.user import User

    other = User(id=uuid4(), external_id=f"o-{uuid4()}", email=f"o-{uuid4()}@x.com", display_name="o", timezone="UTC", is_active=True)
    db_session.add(other)

    def item(t, part, user=test_user, lifecycle=None):
        it = ClothingItem(
            id=uuid4(), user_id=user.id, type=t, body_part=part, image_path=f"x/{uuid4()}.jpg",
            status=ItemStatus.ready, primary_colors=["blue"], wear_count=0,
            wears_since_wash=0, needs_wash=False,
        )
        if lifecycle:
            it.lifecycle = lifecycle
            it.status = terminal_status(lifecycle, ItemStatus.ready)
        db_session.add(it)
        return it

    shirt = item("shirt", "tops")
    legacy_tee = item("t-shirt", None)          # part derived from type
    jeans = item("jeans", "bottoms")
    retired_top = item("shirt", "tops", lifecycle="retired")
    old_model = item("shirt", "tops")
    theirs = item("shirt", "tops", user=other)
    await db_session.commit()
    for it in (shirt, legacy_tee, jeans, retired_top, theirs):
        await upsert_embedding(db_session, it.id, "m1", "fp", _u(1, 0))
    await upsert_embedding(db_session, old_model.id, "m0", "fp", _u(1, 0))
    await db_session.commit()

    tops = {i for i, _ in await load_candidates(db_session, test_user.id, "m1", "tops")}
    assert tops == {shirt.id, legacy_tee.id, retired_top.id}
    everything = {i for i, _ in await load_candidates(db_session, test_user.id, "m1")}
    assert everything == {shirt.id, legacy_tee.id, jeans.id, retired_top.id}
