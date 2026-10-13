"""校色 API：检出 / 应用 / 手动白平衡 / 重置（计划风险 #1 的钉子也在这里）。

测试只验证行为：
- 校色两次后重置，工作图字节等于最初的 `_src.jpg`（且副本全程未被改动）
- 手动白平衡的增益夹在 [GAIN_MIN, GAIN_MAX]（去掉 clamp 变红）
- 四个端点都认 owner（漏了 user 校验变红）
"""

import logging
import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from httpx import AsyncClient
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.color_calibration import apply_gains
from app.services.image_service import ImageService

USER = uuid.UUID("00000000-0000-0000-0000-000000000009")


def _jpeg_bytes(color=(200, 60, 60), size=(600, 400)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _jpeg_textured(size=(600, 400)) -> bytes:
    """带纹理的照片内容。

    纯色图的 JPEG 重编码是字节幂等的（实测 solid 重编码后 bytes 不变），
    「重置必须字节还原」的钉子会因此空转；噪声/纹理才让重编码漂移可见。
    """
    rng = np.random.default_rng(7)
    arr = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    buf = BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=95, optimize=True)
    return buf.getvalue()


def _jpeg_with_gray_card() -> bytes:
    img = Image.new("RGB", (800, 600), (30, 90, 160))
    ImageDraw.Draw(img).rectangle((500, 300, 700, 460), fill=(128, 128, 128))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------- 服务层


@pytest.mark.asyncio
async def test_apply_then_reset_restores_the_pristine_source_bytes(tmp_path):
    """计划风险 #1：校色两次后重置，字节等于最初的 `_src.jpg`。

    三个断言各有钉子：副本不变（校色不得覆盖原副本）、工作图确实被改过
    （否则重置断言是空转）、重置后工作图与副本逐字节一致（原样还原）。
    """
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(USER, _jpeg_textured(), "coat.jpg")

    src = tmp_path / paths["calibration_original_path"]
    working = tmp_path / paths["image_path"]
    src_before = src.read_bytes()
    # 入库时工作图与副本本就逐字节一致
    assert working.read_bytes() == src_before

    svc.calibrate_image(
        paths["image_path"], paths["calibration_original_path"], (0, 0, 50, 50), "gray"
    )
    svc.calibrate_image(
        paths["image_path"], paths["calibration_original_path"], (60, 60, 120, 120), "white"
    )

    assert src.read_bytes() == src_before
    assert working.read_bytes() != src_before

    svc.reset_calibration(paths["image_path"], paths["calibration_original_path"])

    assert src.read_bytes() == src_before
    assert working.read_bytes() == src_before


def test_manual_white_balance_is_bounded_for_extreme_inputs(tmp_path):
    """滑块在 UI 上无界；服务层必须把增益夹在 [GAIN_MIN, GAIN_MAX]（防御纵深）。

    kelvin=100000 时未夹紧的增益是 [6.61, 1.0, -4.61]：R 爆到 255、B 被负增益压成 0。
    夹紧后是 [GAIN_MAX, 1.0, GAIN_MIN] = [4.0, 1.0, 0.25]。去掉 clamp 此测试变红。
    """
    svc = ImageService(storage_path=str(tmp_path))
    img = Image.new("RGB", (200, 200), (40, 40, 40))
    img.save(tmp_path / "w.jpg", format="JPEG", quality=95)
    img.save(tmp_path / "src.jpg", format="JPEG", quality=95)

    out = svc.manual_white_balance("w.jpg", "src.jpg", kelvin=100000.0, tint=0.0)

    expected = np.asarray(
        apply_gains(
            Image.open(tmp_path / "src.jpg").convert("RGB"),
            np.array([4.0, 1.0, 0.25]),
        ),
        dtype=np.float64,
    )
    got = np.asarray(Image.open(tmp_path / out["image_path"]).convert("RGB"), dtype=np.float64)
    # ±5 是再编码 JPEG 的漂移；去掉 clamp 时 B 通道差 ~10、R 通道差 ~95
    assert np.abs(got - expected).max() <= 5


# ---------------------------------------------------------------- API 层


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


@pytest.mark.asyncio
async def test_detect_reports_the_gray_card_box(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user, image_data=_jpeg_with_gray_card())

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/detect", headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "gray"
    l, t, r, b = body["box"]
    # 灰卡画在 (500,300)-(700,460) 含右下；JPEG 边缘漂移留 ±20
    assert 500 <= l <= 520 and 300 <= t <= 320
    assert 680 <= r <= 700 and 440 <= b <= 460


@pytest.mark.asyncio
async def test_detect_reports_no_reference_for_a_plain_photo(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(
        db_session, test_user, image_data=_jpeg_bytes(color=(180, 40, 90))
    )

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/detect", headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"kind": None, "box": None}


@pytest.mark.asyncio
async def test_detect_reports_all_three_cards_for_a_strip(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    """白-灰-黑三联检出时三框一起回给 UI（Task 7 渲染用），主参考仍是灰卡。"""
    img = Image.new("RGB", (800, 600), (30, 90, 160))
    d = ImageDraw.Draw(img)
    d.rectangle((100, 200, 299, 379), fill=(245, 245, 245))
    d.rectangle((310, 200, 509, 379), fill=(128, 128, 128))
    d.rectangle((520, 200, 719, 379), fill=(35, 35, 35))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    item = await _make_item(db_session, test_user, image_data=buf.getvalue())

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/detect", headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "gray"
    assert set(body["cards"]) == {"white", "gray", "black"}
    # 主参考 = 中间那块（灰卡），含右下契约
    assert body["cards"]["gray"] == body["box"]
    l, t, r, b = body["box"]
    assert 310 <= l <= 330 and 200 <= t <= 220
    assert 489 <= r <= 509 and 359 <= b <= 379


@pytest.mark.asyncio
async def test_apply_calibrates_the_working_image_without_touching_the_source(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user)
    svc = ImageService()
    src_before = svc.get_image_path(item.calibration_original_path).read_bytes()
    working_before = svc.get_image_path(item.image_path).read_bytes()

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/apply",
        json={"box": [0, 0, 50, 50], "baseline": "gray"},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["image_path"] == item.image_path
    assert svc.get_image_path(item.calibration_original_path).read_bytes() == src_before
    assert svc.get_image_path(item.image_path).read_bytes() != working_before


@pytest.mark.asyncio
async def test_manual_endpoint_writes_the_white_balanced_image(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user)
    svc = ImageService()
    src_before = svc.get_image_path(item.calibration_original_path).read_bytes()
    working_before = svc.get_image_path(item.image_path).read_bytes()

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/manual",
        json={"kelvin": 5500.0, "tint": -20.0},
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert svc.get_image_path(item.calibration_original_path).read_bytes() == src_before
    assert svc.get_image_path(item.image_path).read_bytes() != working_before


@pytest.mark.asyncio
async def test_reset_endpoint_restores_the_pristine_source_bytes(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user, image_data=_jpeg_textured())
    svc = ImageService()
    src_before = svc.get_image_path(item.calibration_original_path).read_bytes()

    applied = await client.post(
        f"/api/v1/items/{item.id}/calibration/apply",
        json={"box": [0, 0, 50, 50], "baseline": "gray"},
        headers=auth_headers,
    )
    assert applied.status_code == 200, applied.text
    assert svc.get_image_path(item.image_path).read_bytes() != src_before

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/reset", headers=auth_headers
    )

    assert resp.status_code == 200, resp.text
    assert svc.get_image_path(item.image_path).read_bytes() == src_before
    assert svc.get_image_path(item.calibration_original_path).read_bytes() == src_before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("detect", None),
        ("apply", {"box": [0, 0, 50, 50], "baseline": "gray"}),
        ("manual", {"kelvin": 6500.0, "tint": 0.0}),
        ("reset", None),
    ],
)
async def test_calibration_endpoints_reject_foreign_items(
    client: AsyncClient,
    test_user,
    auth_headers,
    db_session: AsyncSession,
    path: str,
    payload: dict | None,
):
    """别人的物品一律 404 —— 漏了 user 校验时这四条全部变红。"""
    other = await _make_user(db_session)
    item = await _make_item(db_session, other)

    kwargs: dict = {"headers": auth_headers}
    if payload is not None:
        kwargs["json"] = payload
    resp = await client.post(f"/api/v1/items/{item.id}/calibration/{path}", **kwargs)

    # 404 + "Item not found" 才是归属校验的语义（路由缺失的 404 是 "Not Found"，
    # 漏了 user 校验会放行 200 —— 两种都能被这条抓住）
    assert resp.status_code == 404, f"{path}: {resp.status_code} {resp.text}"
    assert resp.json() == {"detail": "Item not found"}


@pytest.mark.asyncio
async def test_detect_requires_authentication(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user)

    resp = await client.post(f"/api/v1/items/{item.id}/calibration/detect")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_apply_rejects_an_item_without_a_calibration_source(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user, calibration_original_path=None)

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/apply",
        json={"box": [0, 0, 50, 50], "baseline": "gray"},
        headers=auth_headers,
    )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_manual_rejects_kelvin_outside_the_slider_range(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user)

    for payload in ({"kelvin": 1000.0, "tint": 0.0}, {"kelvin": 20000.0, "tint": 0.0}):
        resp = await client.post(
            f"/api/v1/items/{item.id}/calibration/manual",
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_apply_rejects_a_bad_box_or_baseline(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    item = await _make_item(db_session, test_user)

    for payload in (
        {"box": [0, 0, 50], "baseline": "gray"},
        {"box": [0, 0, 50, 50], "baseline": "green"},
    ):
        resp = await client.post(
            f"/api/v1/items/{item.id}/calibration/apply",
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_calibrate_image_rejects_a_box_outside_the_image(tmp_path):
    """服务层兜底：越界 box 在裁剪/按面积分配内存之前就拒掉。

    越界裁剪会被 PIL 黑边填充地接受，参考均值带偏成错误颜色；超大 box 还会
    先按 box 面积分配内存。
    """
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(USER, _jpeg_bytes(size=(600, 400)), "coat.jpg")

    for box in ((0, 0, 2000, 2000), (-5, 0, 50, 50), (50, 50, 40, 60)):
        with pytest.raises(ValueError):
            svc.calibrate_image(
                paths["image_path"], paths["calibration_original_path"], box, "gray"
            )


@pytest.mark.asyncio
async def test_apply_rejects_an_out_of_bounds_box(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    """越界 box 是 400，不能 200 + 错误颜色。"""
    item = await _make_item(db_session, test_user)  # 600×400

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/apply",
        json={"box": [0, 0, 2000, 2000], "baseline": "gray"},
        headers=auth_headers,
    )

    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_write_endpoints_reject_an_item_with_a_running_job(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    """后台任务拥有三档文件（同 remove-background 的 409）；detect 只读不拦。"""
    item = await _make_item(
        db_session, test_user, status=ItemStatus.processing, ai_job_id="job-123"
    )

    for path, payload in (
        ("apply", {"box": [0, 0, 50, 50], "baseline": "gray"}),
        ("manual", {"kelvin": 6500.0, "tint": 0.0}),
        ("reset", None),
    ):
        kwargs: dict = {"headers": auth_headers}
        if payload is not None:
            kwargs["json"] = payload
        resp = await client.post(f"/api/v1/items/{item.id}/calibration/{path}", **kwargs)
        assert resp.status_code == 409, f"{path}: {resp.status_code} {resp.text}"

    detected = await client.post(
        f"/api/v1/items/{item.id}/calibration/detect", headers=auth_headers
    )
    assert detected.status_code == 200, detected.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,payload",
    [
        ("apply", {"box": [0, 0, 50, 50], "baseline": "gray"}),
        ("manual", {"kelvin": 6500.0, "tint": 0.0}),
        ("reset", None),
    ],
)
async def test_calibration_endpoints_clear_a_stale_mask(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, path, payload
):
    """校色后 mask 必须清掉（列置 None + 文件删掉），否则 update_mask 会拿过期 mask 合成。"""
    item = await _make_item(db_session, test_user)
    item_id = item.id
    svc = ImageService()
    provider = MagicMock()
    provider.remove.side_effect = lambda img: Image.new("RGBA", img.size, (0, 0, 255, 255))
    with patch("app.services.background_removal.get_provider", return_value=provider):
        matte = svc.remove_background(item.image_path)
    item.image_path = matte["image_path"]
    item.medium_path = matte["medium_path"]
    item.thumbnail_path = matte["thumbnail_path"]
    item.mask_path = matte["mask_path"]
    item.original_image_path = matte["original_backup_path"]
    await db_session.commit()
    mask_file = svc.get_image_path(matte["mask_path"])
    assert mask_file.exists()

    kwargs: dict = {"headers": auth_headers}
    if payload is not None:
        kwargs["json"] = payload
    resp = await client.post(f"/api/v1/items/{item_id}/calibration/{path}", **kwargs)

    assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"
    # 响应体里的 mask_cleared 是 UI「请重抠」提示的唯一依据，必须进 HTTP 响应
    assert resp.json()["mask_cleared"] is True, f"{path}: cleared mask not reported"
    assert not mask_file.exists(), f"{path}: stale mask sidecar left on disk"
    db_session.expire_all()
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    refreshed = result.scalar_one()
    assert refreshed.mask_path is None, f"{path}: mask_path not cleared"
    assert refreshed.original_image_path is None, f"{path}: stale cutout backup still restorable"
    assert resp.json()["original_image_path"] is None


@pytest.mark.asyncio
async def test_calibrating_a_legacy_cutout_retires_its_backup(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession
):
    """分支前抠过的旧物品：主图是合成白底 JPG + `_orig.jpg`，没有 mask。

    校色后工作图从 `_src` 重推导，旧备份描述的是被丢弃的像素——「还原原图」
    必须不再可用，而不是把旧合成图写回来。
    """
    item = await _make_item(db_session, test_user)
    svc = ImageService()
    backup = svc.get_image_path(item.image_path).with_name(
        svc.get_image_path(item.image_path).stem + "_orig.jpg"
    )
    backup.write_bytes(svc.get_image_path(item.image_path).read_bytes())
    item.original_image_path = str(backup.relative_to(svc.storage_path))
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/items/{item.id}/calibration/manual",
        json={"kelvin": 5000.0, "tint": 0.0},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["original_image_path"] is None
    assert resp.json()["mask_cleared"] is False
    assert not backup.exists()

    restore = await client.post(
        f"/api/v1/items/{item.id}/restore-original", headers=auth_headers
    )
    assert restore.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,payload",
    [
        ("apply", {"box": [0, 0, 50, 50], "baseline": "gray"}),
        ("manual", {"kelvin": 6500.0, "tint": 0.0}),
        ("reset", None),
    ],
)
async def test_calibration_endpoints_report_nothing_cleared_without_a_mask(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, path, payload
):
    """从没抠过的图校色完不该弹「请重抠」：mask_cleared 只在真删了 mask 文件时为 True。"""
    item = await _make_item(db_session, test_user)
    item_id = item.id
    assert item.mask_path is None

    kwargs: dict = {"headers": auth_headers}
    if payload is not None:
        kwargs["json"] = payload
    resp = await client.post(f"/api/v1/items/{item_id}/calibration/{path}", **kwargs)

    assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"
    assert resp.json()["mask_cleared"] is False, f"{path}: no mask file but mask_cleared=True"
    db_session.expire_all()
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    assert result.scalar_one().mask_path is None, f"{path}: mask_path must stay null"


@pytest.mark.asyncio
async def test_a_failed_image_op_logs_the_traceback(
    client: AsyncClient, test_user, auth_headers, db_session: AsyncSession, caplog
):
    """500 路径必须带堆栈：只记 f-string 的错误信息，线上排障无从下手。"""
    item = await _make_item(db_session, test_user)
    with patch.object(ImageService, "calibrate_image", side_effect=RuntimeError("boom")), \
            caplog.at_level(logging.ERROR, logger="app.api.calibration"):
        resp = await client.post(
            f"/api/v1/items/{item.id}/calibration/apply",
            json={"box": [0, 0, 50, 50], "baseline": "gray"},
            headers=auth_headers,
        )
    assert resp.status_code == 500
    records = [r for r in caplog.records if r.name == "app.api.calibration"]
    assert records, "the failure was not logged"
    assert records[-1].exc_info is not None, "the traceback was dropped"


@pytest.mark.parametrize("tint,low,high", [(100.0, 1.25, 1.35), (-100.0, 0.65, 0.75)])
def test_tint_slider_extremes_move_green_visibly(tmp_path, tint, low, high):
    """色调滑块拉满必须看得出来：绿通道 ±30%，红/蓝不动。"""
    svc = ImageService(storage_path=str(tmp_path))
    img = Image.new("RGB", (100, 100), (128, 128, 128))
    img.save(tmp_path / "w.jpg", format="JPEG", quality=95)
    img.save(tmp_path / "src.jpg", format="JPEG", quality=95)

    out = svc.manual_white_balance("w.jpg", "src.jpg", kelvin=6500.0, tint=tint)

    r, g, b = np.asarray(Image.open(tmp_path / out["image_path"]).convert("RGB"),
                         dtype=np.float64).reshape(-1, 3).mean(axis=0)
    assert low * 128 <= g <= high * 128, f"tint={tint}: green={g:.1f}"
    assert abs(r - 128) <= 3 and abs(b - 128) <= 3
