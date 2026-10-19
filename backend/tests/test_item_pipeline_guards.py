"""D8 终审修复：在跑 job 的写保护、流水线失败的恢复与计数归属（final-findings #2–#5）。"""

import uuid
from io import BytesIO

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemImage, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService

CONFLICT = {"detail": "Item has a background job in progress"}


def _jpeg_bytes(color=(200, 60, 60), size=(400, 300)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


async def _make_item(db_session: AsyncSession, user: User, **overrides) -> ClothingItem:
    paths = await ImageService().process_and_store(
        user_id=user.id, image_data=_jpeg_bytes(), original_filename="coat.jpg"
    )
    defaults = {
        "user_id": user.id,
        "type": "shirt",
        "image_path": paths["image_path"],
        "medium_path": paths["medium_path"],
        "thumbnail_path": paths["thumbnail_path"],
        "calibration_original_path": paths["calibration_original_path"],
        "image_hash": paths["image_hash"],
        "status": ItemStatus.ready,
    }
    defaults.update(overrides)
    item = ClothingItem(**defaults)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _reload(db_session: AsyncSession, item_id) -> ClothingItem:
    db_session.expire_all()
    r = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return r.scalar_one()


async def _live_job_item(db_session, user) -> ClothingItem:
    return await _make_item(
        db_session,
        user,
        status=ItemStatus.processing,
        processing_kind="pipeline",
        ai_job_id="job-live",
    )


# ---- #5：rotate / PUT image / set-primary 在 job 在跑时 409 ----


@pytest.mark.asyncio
async def test_rotate_conflicts_with_a_running_job(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _live_job_item(db_session, test_user)
    before = ImageService().get_image_path(item.image_path).read_bytes()

    resp = await client.post(f"/api/v1/items/{item.id}/rotate?direction=cw", headers=auth_headers)

    assert resp.status_code == 409, resp.text
    assert resp.json() == CONFLICT
    assert ImageService().get_image_path(item.image_path).read_bytes() == before


@pytest.mark.asyncio
async def test_replace_image_conflicts_with_a_running_job(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _live_job_item(db_session, test_user)
    old_path = item.image_path

    resp = await client.put(
        f"/api/v1/items/{item.id}/image",
        files={"image": ("new.jpg", _jpeg_bytes((10, 10, 200)), "image/jpeg")},
        headers=auth_headers,
    )

    assert resp.status_code == 409, resp.text
    assert resp.json() == CONFLICT
    assert (await _reload(db_session, item.id)).image_path == old_path


@pytest.mark.asyncio
async def test_set_primary_conflicts_with_a_running_job(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _live_job_item(db_session, test_user)
    old_path = item.image_path
    gallery = ItemImage(item_id=item.id, image_path=f"gallery/{uuid.uuid4()}.jpg", position=1)
    db_session.add(gallery)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/items/{item.id}/images/{gallery.id}/set-primary", headers=auth_headers
    )

    assert resp.status_code == 409, resp.text
    assert resp.json() == CONFLICT
    assert (await _reload(db_session, item.id)).image_path == old_path


# ---- #4：set-primary 重置 calibration_state ----


@pytest.mark.asyncio
async def test_set_primary_resets_calibration_state(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user, calibration_state="done")
    gallery = ItemImage(item_id=item.id, image_path=f"gallery/{uuid.uuid4()}.jpg", position=1)
    db_session.add(gallery)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/items/{item.id}/images/{gallery.id}/set-primary", headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    assert (await _reload(db_session, item.id)).calibration_state == "none"


# ---- #2：手动校色成功清掉流水线错误 ----


@pytest.mark.asyncio
async def test_manual_calibration_clears_a_pipeline_error(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user, status=ItemStatus.error, processing_kind="pipeline")

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/apply",
        json={"box": [0, 0, 50, 50], "baseline": "gray"},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    item = await _reload(db_session, item.id)
    assert item.status == ItemStatus.ready
    assert item.processing_kind is None
    assert item.calibration_state == "done"


@pytest.mark.asyncio
async def test_manual_calibration_leaves_a_tagging_error_alone(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    """打标失败（kind=None）不是图像步骤的错：校色不该把它抹掉。"""
    item = await _make_item(db_session, test_user, status=ItemStatus.error)

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/apply",
        json={"box": [0, 0, 50, 50], "baseline": "gray"},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert (await _reload(db_session, item.id)).status == ItemStatus.error


# ---- #3：流水线图像失败不计入打标进度 ----


@pytest.mark.asyncio
async def test_tagging_progress_excludes_pipeline_image_steps(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    for status_, kind in [
        (ItemStatus.processing, "pipeline"),
        (ItemStatus.error, "pipeline"),
        (ItemStatus.processing, None),
        (ItemStatus.error, None),
    ]:
        db_session.add(
            ClothingItem(
                user_id=test_user.id,
                type="shirt",
                image_path=f"t/{uuid.uuid4()}.jpg",
                status=status_,
                processing_kind=kind,
            )
        )
    await db_session.commit()

    resp = await client.get("/api/v1/items/tagging-progress", headers=auth_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["processing"] == 1
    assert body["failed"] == 1
