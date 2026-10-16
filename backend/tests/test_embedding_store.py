import os
import time
from dataclasses import dataclass
from uuid import uuid4

import numpy as np
import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

from app.models.embedding import ItemEmbedding
from app.models.item import ClothingItem, ItemStatus
from app.services.embedding_client import EmbeddingUnavailableError
from app.services.embedding_store import (
    embedding_counts,
    embedding_input_image,
    mark_all_stale,
    source_fingerprint,
    stale_items,
    sync_item_embeddings,
    upsert_embedding,
)
from app.utils.item_lifecycle import terminal_status


@pytest.fixture
def storage(tmp_path):
    return tmp_path


def _write(storage, rel, color=(10, 20, 30), mode="RGB", size=(40, 30)):
    p = storage / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, size, color).save(p)
    return rel


@pytest_asyncio.fixture
async def make_item(db_session, test_user, storage):
    async def _make(name="a", status=ItemStatus.ready, user_id=None, with_file=True, lifecycle=None):
        rel = f"u/{name}.jpg"
        if with_file:
            _write(storage, rel)
        item = ClothingItem(
            id=uuid4(), user_id=user_id or test_user.id, type="shirt", image_path=rel,
            status=status, primary_colors=["blue"], wear_count=0, wears_since_wash=0,
            needs_wash=False,
        )
        if lifecycle:
            item.lifecycle = lifecycle
            item.status = terminal_status(lifecycle, status)
        db_session.add(item)
        await db_session.commit()
        return item
    return _make


@dataclass
class FakeClient:
    model: str = "m1"
    fail_on_call: int | None = None
    calls: int = 0

    async def embed_images(self, images, instruction=None, batch_size=8):
        self.calls += 1
        if self.fail_on_call == self.calls:
            raise EmbeddingUnavailableError("down")
        return [np.array([1.0, 1.0, 0.0], dtype=np.float32) / np.sqrt(2) for _ in images]


def test_fingerprint_changes_when_file_rewritten(storage):
    rel = _write(storage, "u/x.jpg")
    item = ClothingItem(image_path=rel, mask_path=None)
    fp1 = source_fingerprint(item, storage)
    assert fp1 and fp1.endswith("|-")
    st = os.stat(storage / rel)
    os.utime(storage / rel, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert source_fingerprint(item, storage) != fp1


def test_fingerprint_includes_mask_and_none_when_missing(storage):
    rel = _write(storage, "u/y.png", mode="RGBA", color=(255, 0, 0, 255))
    mask = _write(storage, "u/y_mask.png", mode="L", color=255)
    item = ClothingItem(image_path=rel, mask_path=mask)
    assert "y_mask.png" in source_fingerprint(item, storage)
    assert source_fingerprint(ClothingItem(image_path="u/missing.jpg"), storage) is None


def test_input_image_composites_cutout_on_white(storage):
    rel = "u/z.png"
    (storage / "u").mkdir(parents=True, exist_ok=True)
    rgba = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    rgba.putpixel((0, 0), (255, 0, 0, 255))
    rgba.save(storage / rel)
    mask = _write(storage, "u/z_mask.png", mode="L", color=0, size=(4, 4))
    img = embedding_input_image(ClothingItem(image_path=rel, mask_path=mask), storage)
    assert img.mode == "RGB"
    assert img.getpixel((0, 0)) == (255, 0, 0)
    assert img.getpixel((3, 3)) == (255, 255, 255)


def test_input_image_whitens_transparency_without_mask(storage):
    rel = "u/t.png"
    (storage / "u").mkdir(parents=True, exist_ok=True)
    rgba = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    rgba.putpixel((0, 0), (255, 0, 0, 255))
    rgba.save(storage / rel)
    img = embedding_input_image(ClothingItem(image_path=rel, mask_path=None), storage)
    assert img.mode == "RGB"
    assert img.getpixel((0, 0)) == (255, 0, 0)
    assert img.getpixel((3, 3)) == (255, 255, 255)


@pytest.mark.asyncio
async def test_stale_detection(db_session, make_item, storage, test_user):
    fresh = await make_item("fresh")
    other_model = await make_item("om")
    moved = await make_item("moved")
    missing = await make_item("gone", with_file=False)
    processing = await make_item("proc", status=ItemStatus.processing)
    v = np.array([1.0, 0.0], dtype=np.float32)
    await upsert_embedding(db_session, fresh.id, "m1", source_fingerprint(fresh, storage), v)
    await upsert_embedding(db_session, other_model.id, "m0", source_fingerprint(other_model, storage), v)
    await upsert_embedding(db_session, moved.id, "m1", "stale-fingerprint", v)
    await db_session.commit()
    no_row = await make_item("norow")

    ids = {i.id for i in await stale_items(db_session, test_user.id, "m1", storage)}
    assert ids == {other_model.id, moved.id, no_row.id}
    assert fresh.id not in ids and missing.id not in ids and processing.id not in ids


@pytest.mark.asyncio
async def test_upsert_normalizes_and_replaces(db_session, make_item, storage):
    item = await make_item("n")
    await upsert_embedding(db_session, item.id, "m1", "fp", np.array([3.0, 4.0], dtype=np.float32))
    await upsert_embedding(db_session, item.id, "m2", "fp2", np.array([0.0, 2.0], dtype=np.float32))
    await db_session.commit()
    rows = (await db_session.execute(select(ItemEmbedding).where(ItemEmbedding.item_id == item.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].model == "m2" and rows[0].dim == 2
    assert rows[0].vector == pytest.approx([0.0, 1.0])


@pytest.mark.asyncio
async def test_sync_writes_all_then_nothing_stale(db_session, make_item, storage, test_user):
    for n in "abc":
        await make_item(n)
    result = await sync_item_embeddings(db_session, test_user.id, FakeClient(), storage, batch_size=2)
    assert (result.done, result.remaining) == (3, 0)
    assert await stale_items(db_session, test_user.id, "m1", storage) == []


@pytest.mark.asyncio
async def test_sync_failure_keeps_committed_batches(db_session, make_item, storage, test_user):
    for n in "abcde":
        await make_item(n)
    client = FakeClient(fail_on_call=2)
    with pytest.raises(EmbeddingUnavailableError):
        await sync_item_embeddings(db_session, test_user.id, client, storage, batch_size=2)
    remaining = await stale_items(db_session, test_user.id, "m1", storage)
    assert len(remaining) == 3  # first batch of 2 survived
    client2 = FakeClient()
    result = await sync_item_embeddings(db_session, test_user.id, client2, storage, batch_size=2)
    assert (result.done, result.remaining) == (3, 0)


@pytest.mark.asyncio
async def test_sync_ignores_other_users(db_session, make_item, storage, test_user):
    from app.models.user import User

    other = User(id=uuid4(), external_id=f"o-{uuid4()}", email=f"o-{uuid4()}@x.com", display_name="o", timezone="UTC", is_active=True)
    db_session.add(other)
    await db_session.commit()
    await make_item("mine")
    await make_item("theirs", user_id=other.id)
    result = await sync_item_embeddings(db_session, test_user.id, FakeClient(), storage)
    assert result.done == 1


@pytest.mark.asyncio
async def test_retired_items_are_stale_and_synced(db_session, make_item, storage, test_user):
    retired = await make_item("old", lifecycle="retired")
    assert retired.status == ItemStatus.archived
    ids = {i.id for i in await stale_items(db_session, test_user.id, "m1", storage)}
    assert retired.id in ids
    result = await sync_item_embeddings(db_session, test_user.id, FakeClient(), storage)
    assert (result.done, result.remaining) == (1, 0)


@pytest.mark.asyncio
async def test_sync_skips_unreadable_image(db_session, make_item, storage, test_user):
    for n in "abcd":
        await make_item(n)
    (storage / "u/b.jpg").write_bytes(b"not an image")
    result = await sync_item_embeddings(db_session, test_user.id, FakeClient(), storage, batch_size=2)
    assert (result.done, result.skipped, result.remaining) == (3, 1, 1)


@pytest.mark.asyncio
async def test_sync_stops_at_deadline_between_batches(
    db_session, test_user, make_item, storage, monkeypatch
):
    items = [await make_item(f"d{i}") for i in range(3)]
    deadline = time.monotonic() + 3600
    real_monotonic = time.monotonic

    class ExpiringClient(FakeClient):
        async def embed_images(self, images, instruction=None, batch_size=8):
            out = await super().embed_images(images, instruction, batch_size)
            # budget runs out while batch 1 is in flight
            monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + 7200)
            return out

    client = ExpiringClient()
    res = await sync_item_embeddings(
        db_session, test_user.id, client, storage, batch_size=1, deadline=deadline
    )
    assert res.done == 1 and client.calls == 1
    still_stale = {i.id for i in await stale_items(db_session, test_user.id, "m1", storage)}
    assert len({i.id for i in items} & still_stale) == 2


@pytest.mark.asyncio
async def test_mark_all_stale_forces_resync_but_keeps_vectors(db_session, test_user, make_item, storage):
    item = await make_item("ms")
    await sync_item_embeddings(db_session, test_user.id, FakeClient(), storage)
    assert item.id not in {i.id for i in await stale_items(db_session, test_user.id, "m1", storage)}
    n = await mark_all_stale(db_session, test_user.id)
    await db_session.commit()
    assert n >= 1
    assert item.id in {i.id for i in await stale_items(db_session, test_user.id, "m1", storage)}
    row = (await db_session.execute(select(ItemEmbedding).where(ItemEmbedding.item_id == item.id))).scalar_one()
    assert row.vector  # old vector still served until replaced


@pytest.mark.asyncio
async def test_embedding_counts(db_session, test_user, make_item, storage):
    await make_item("c1")
    await make_item("c2", with_file=False)  # no image → not counted
    total0, stale0 = await embedding_counts(db_session, test_user.id, "m1", storage)
    await sync_item_embeddings(db_session, test_user.id, FakeClient(), storage)
    total1, stale1 = await embedding_counts(db_session, test_user.id, "m1", storage)
    assert total1 == total0 and stale1 == 0 and stale0 >= 1
