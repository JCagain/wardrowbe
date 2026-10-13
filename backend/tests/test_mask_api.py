"""mask 画笔 API：POST /items/{item_id}/mask（R3/R4/R5 的钉子在这里）。

测试只验证行为：
- 改完 mask 三档路径写回 DB，但 mask_path 原样不动（不能走 _persist_image_op）
- 后台 job 在跑时 409，文件不被抢写
- 没有 mask 时 400，文案含 run background removal first
- 他人的物品 404（同校色四端点语义）
"""

import uuid
from io import BytesIO
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.image_service import ImageService


def _jpeg_bytes(color=(200, 60, 60), size=(400, 300)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _opaque_provider():
    class FakeProvider:
        def remove(self, image):
            rgba = image.convert("RGBA")
            rgba.putalpha(Image.new("L", rgba.size, 255))
            return rgba

    return FakeProvider()


async def _make_item(
    db_session: AsyncSession,
    user: User,
    image_data: bytes | None = None,
    **overrides,
) -> ClothingItem:
    svc = ImageService()
    paths = await svc.process_and_store(
        user_id=user.id,
        image_data=image_data if image_data is not None else _jpeg_bytes(),
        original_filename="coat.jpg",
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


async def _make_item_with_mask(
    db_session: AsyncSession,
    user: User,
    **overrides,
) -> ClothingItem:
    item = await _make_item(db_session, user, **overrides)
    svc = ImageService()
    with patch("app.services.background_removal.get_provider", return_value=_opaque_provider()):
        matte = svc.remove_background(item.image_path)
    item.image_path = matte["image_path"]
    item.medium_path = matte["medium_path"]
    item.thumbnail_path = matte["thumbnail_path"]
    item.mask_path = matte["mask_path"]
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _make_user(db_session: AsyncSession) -> User:
    unique_id = uuid.uuid4()
    user = User(
        id=unique_id,
        external_id=f"test-user-{unique_id}",
        email=f"test-{unique_id}@example.com",
        display_name="Other User",
        timezone="UTC",
        is_active=True,
        onboarding_completed=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


_STROKE = {"x": 10, "y": 10, "radius": 20, "mode": "subtract"}


@pytest.mark.asyncio
async def test_editing_the_mask_keeps_the_mask_path_and_writes_the_three_sizes(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    """R3：三档写回 DB，mask_path 不动（走 _persist_image_op 会当场清掉）。"""
    item = await _make_item_with_mask(db_session, test_user)
    item_id = item.id
    mask_path = item.mask_path
    svc = ImageService()
    mask_file = svc.get_image_path(mask_path)
    assert mask_file.exists()

    resp = await client.post(
        f"/api/v1/items/{item_id}/mask",
        json={"strokes": [_STROKE]},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # mask_cleared 在这里没有意义（我们没清 mask）——那是校色的语义
    assert "mask_cleared" not in body

    db_session.expire_all()
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    refreshed = result.scalar_one()
    assert refreshed.mask_path == mask_path, "mask_path must survive the mask edit"
    assert refreshed.mask_path is not None
    assert mask_file.exists(), "the mask sidecar must still be on disk"
    assert Image.open(mask_file).getpixel((10, 10)) == 0, "the stroke must be applied to the mask"

    # 三档路径写回 DB（扩展名一变 DB 只能指向新文件）
    for key in ("image_path", "medium_path", "thumbnail_path"):
        assert getattr(refreshed, key) == body[key]
        assert body[key].endswith(".png")
        assert svc.get_image_path(body[key]).exists()
    # 主图 alpha 跟着改（三档同批重生成，fixes #13）
    main = Image.open(svc.get_image_path(body["image_path"]))
    assert main.getchannel("A").getpixel((10, 10)) == 0


@pytest.mark.asyncio
async def test_editing_the_mask_conflicts_with_a_running_job(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    """R4：后台 job 拥有三档文件，抢写会撕裂尺寸组——409 且一个文件都不许动。"""
    item = await _make_item_with_mask(
        db_session, test_user, status=ItemStatus.processing, ai_job_id="job-123"
    )
    item_id = item.id
    svc = ImageService()
    tracked = [item.image_path, item.medium_path, item.thumbnail_path, item.mask_path]
    before = {rel: svc.get_image_path(rel).read_bytes() for rel in tracked}

    resp = await client.post(
        f"/api/v1/items/{item_id}/mask",
        json={"strokes": [_STROKE]},
        headers=auth_headers,
    )

    assert resp.status_code == 409, resp.text
    assert resp.json() == {"detail": "Item has a background job in progress"}
    for rel, data in before.items():
        assert svc.get_image_path(rel).read_bytes() == data, f"{rel} was rewritten"


@pytest.mark.asyncio
async def test_editing_the_mask_requires_an_existing_mask(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    """没有 mask 就没法画：400 + 文案点明先跑背景移除（R5 定死的文案）。"""
    item = await _make_item(db_session, test_user)
    assert item.mask_path is None

    resp = await client.post(
        f"/api/v1/items/{item.id}/mask",
        json={"strokes": [_STROKE]},
        headers=auth_headers,
    )

    assert resp.status_code == 400, resp.text
    assert "run background removal first" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_editing_the_mask_rejects_foreign_items(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    """别人的物品一律 404 —— 漏了归属校验时这条变红。"""
    other = await _make_user(db_session)
    item = await _make_item_with_mask(db_session, other)

    resp = await client.post(
        f"/api/v1/items/{item.id}/mask",
        json={"strokes": [_STROKE]},
        headers=auth_headers,
    )

    assert resp.status_code == 404, f"{resp.status_code} {resp.text}"
    assert resp.json() == {"detail": "Item not found"}
