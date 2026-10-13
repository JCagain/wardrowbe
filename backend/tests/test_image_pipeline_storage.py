import io
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from PIL import Image, ImageChops, ImageDraw, ImageStat
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem
from app.services.color_calibration import detect_reference
from app.services.image_service import ImageService

USER = uuid.UUID("00000000-0000-0000-0000-000000000001")

GREEN = (10, 200, 30)
RED = (220, 30, 20)


def _jpeg_bytes(color=(200, 60, 60), size=(600, 400)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def _pixel(path) -> tuple[int, int, int]:
    return Image.open(path).convert("RGB").getpixel((5, 5))


def _close(a: tuple, b: tuple, tolerance: int = 20) -> bool:
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


@pytest.mark.asyncio
async def test_upload_keeps_a_pristine_source_beside_the_working_image(tmp_path):
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER, image_data=_jpeg_bytes(), original_filename="coat.jpg"
    )
    assert paths["calibration_original_path"].endswith("_src.jpg")
    assert (tmp_path / paths["calibration_original_path"]).exists()
    assert paths["calibration_original_path"] != paths["image_path"]


@pytest.mark.asyncio
async def test_regenerating_sizes_never_touches_the_source(tmp_path):
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER, image_data=_jpeg_bytes(), original_filename="coat.jpg"
    )
    src = tmp_path / paths["calibration_original_path"]
    before = src.read_bytes()

    svc._save_all_sizes(Image.new("RGB", (100, 100), (0, 255, 0)), paths["image_path"])

    assert src.read_bytes() == before


@pytest.mark.asyncio
async def test_skipping_the_source_writes_no_src_file(tmp_path):
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER,
        image_data=_jpeg_bytes(),
        original_filename="detail.jpg",
        keep_source=False,
    )
    assert paths["calibration_original_path"] is None
    assert list(tmp_path.glob("*/*_src.jpg")) == []
    # The working image itself is still stored.
    assert (tmp_path / paths["image_path"]).exists()


@pytest.mark.asyncio
async def test_additional_image_upload_writes_no_src_file(
    client: AsyncClient, auth_headers, db_session: AsyncSession
):
    created = await client.post(
        "/api/v1/items",
        files={"image": ("coat.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"type": "coat", "skip_ai": "true"},
        headers=auth_headers,
    )
    assert created.status_code in (200, 201), created.text

    before = set(ImageService().storage_path.glob("*/*_src.jpg"))
    added = await client.post(
        f"/api/v1/items/{created.json()['id']}/images",
        files={"image": ("detail.jpg", _jpeg_bytes(color=RED), "image/jpeg")},
        headers=auth_headers,
    )
    assert added.status_code == 201, added.text
    assert set(ImageService().storage_path.glob("*/*_src.jpg")) == before


async def _src_path_of(db_session: AsyncSession, item_id) -> str | None:
    db_item = (
        await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    ).scalar_one()
    return db_item.calibration_original_path


@pytest.mark.asyncio
async def test_create_item_persists_the_source_path(
    client: AsyncClient, auth_headers, db_session: AsyncSession
):
    response = await client.post(
        "/api/v1/items",
        files={"image": ("coat.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"type": "coat", "skip_ai": "true"},
        headers=auth_headers,
    )
    assert response.status_code in (200, 201), response.text

    src_rel = await _src_path_of(db_session, response.json()["id"])
    assert src_rel is not None
    assert src_rel.endswith("_src.jpg")
    assert ImageService().get_image_path(src_rel).exists()


@pytest.mark.asyncio
async def test_bulk_upload_persists_the_source_path(
    client: AsyncClient, auth_headers, db_session: AsyncSession
):
    response = await client.post(
        "/api/v1/items/bulk",
        files=[("images", ("coat.jpg", _jpeg_bytes(), "image/jpeg"))],
        data={"skip_ai": "true"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["successful"] == 1, response.json()

    src_rel = await _src_path_of(db_session, response.json()["results"][0]["item"]["id"])
    assert src_rel is not None
    assert src_rel.endswith("_src.jpg")
    assert ImageService().get_image_path(src_rel).exists()


@pytest.mark.asyncio
async def test_replacing_the_image_repoints_the_source_to_the_new_upload(
    client: AsyncClient, auth_headers, db_session: AsyncSession
):
    created = await client.post(
        "/api/v1/items",
        files={"image": ("old.jpg", _jpeg_bytes(color=GREEN), "image/jpeg")},
        data={"type": "coat", "skip_ai": "true"},
        headers=auth_headers,
    )
    assert created.status_code in (200, 201), created.text
    item_id = created.json()["id"]
    old_src_rel = await _src_path_of(db_session, item_id)
    assert old_src_rel is not None
    svc = ImageService()

    replaced = await client.put(
        f"/api/v1/items/{item_id}/image",
        files={"image": ("new.jpg", _jpeg_bytes(color=RED), "image/jpeg")},
        headers=auth_headers,
    )
    assert replaced.status_code == 200, replaced.text

    new_src_rel = await _src_path_of(db_session, item_id)
    assert new_src_rel is not None
    assert new_src_rel != old_src_rel
    new_src = svc.get_image_path(new_src_rel)
    assert new_src.exists()
    # Reset-after-replace must restore the NEW upload, not the old one.
    assert _close(_pixel(new_src), RED)
    assert not svc.get_image_path(old_src_rel).exists()


@pytest.mark.asyncio
async def test_deleting_the_item_removes_its_source_file(
    client: AsyncClient, auth_headers, db_session: AsyncSession
):
    created = await client.post(
        "/api/v1/items",
        files={"image": ("coat.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"type": "coat", "skip_ai": "true"},
        headers=auth_headers,
    )
    assert created.status_code in (200, 201), created.text
    src_rel = await _src_path_of(db_session, created.json()["id"])
    assert src_rel is not None
    svc = ImageService()
    assert svc.get_image_path(src_rel).exists()

    deleted = await client.delete(
        f"/api/v1/items/{created.json()['id']}", headers=auth_headers
    )
    assert deleted.status_code == 204
    assert not svc.get_image_path(src_rel).exists()


@pytest.mark.asyncio
async def test_bulk_delete_removes_source_files(
    client: AsyncClient, auth_headers, db_session: AsyncSession
):
    created = await client.post(
        "/api/v1/items",
        files={"image": ("coat.jpg", _jpeg_bytes(), "image/jpeg")},
        data={"type": "coat", "skip_ai": "true"},
        headers=auth_headers,
    )
    assert created.status_code in (200, 201), created.text
    item_id = created.json()["id"]
    src_rel = await _src_path_of(db_session, item_id)
    assert src_rel is not None
    svc = ImageService()
    assert svc.get_image_path(src_rel).exists()

    deleted = await client.post(
        "/api/v1/items/bulk/delete",
        json={"item_ids": [item_id]},
        headers=auth_headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == 1
    assert not svc.get_image_path(src_rel).exists()


# ---------------------------------------------------------------- 旋转同步 `_src`
# Task R23：detect 在工作图坐标系给框，calibrate/reset 从 `_src` 裁像素。
# rotate 不转 `_src` 就是坐标空间分裂——白平衡静默取错区域、重置连旋转一起撤销。
# 不变量：**任何时刻 `_src` 与工作图同尺寸同朝向。**


def _block_image(size: tuple[int, int] = (600, 400)) -> bytes:
    """非对称四象限色块：转错方向/轴立刻显形，JPEG 往返后仍稳定。"""
    img = Image.new("RGB", size, (15, 15, 15))
    w, h = size
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w // 2 - 1, h // 2 - 1), fill=(220, 40, 40))  # 左上 红
    d.rectangle((w // 2, 0, w - 1, h // 2 - 1), fill=(40, 220, 40))  # 右上 绿
    d.rectangle((0, h // 2, w // 2 - 1, h - 1), fill=(40, 40, 220))  # 左下 蓝
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _mean_channel_diff(a: Image.Image, b: Image.Image) -> float:
    """两图逐像素平均通道差。硬边缘的 JPEG 振铃只在边角（实测块内逐像素 0、
    角点最大 20/255），全局 max 对合成硬边过脆，改钉「整体接近」。"""
    assert a.size == b.size
    stat = ImageStat.Stat(ImageChops.difference(a.convert("RGB"), b.convert("RGB")))
    return max(stat.mean)


def _quadrant_samples(size: tuple[int, int]) -> list[tuple[int, int]]:
    """四象限中心 + 距块边界 4px 的取样点。

    象限中心钉住几何映射（转错方向/轴立刻变色）；边界内侧 4px 的点钉住平移
    （实测 JPEG 振铃只在边角数 px 内、直边 4px 处已 ≤ 2/255），都避开四色角点。
    """
    w, h = size
    mid_w, mid_h = w // 2, h // 2
    return [
        (w // 4, h // 4),
        (3 * w // 4, h // 4),
        (w // 4, 3 * h // 4),
        (3 * w // 4, 3 * h // 4),
        (mid_w - 4, h // 4),
        (mid_w + 4, h // 4),
        (mid_w - 4, 3 * h // 4),
        (mid_w + 4, 3 * h // 4),
        (w // 4, mid_h - 4),
        (w // 4, mid_h + 4),
        (3 * w // 4, mid_h - 4),
        (3 * w // 4, mid_h + 4),
    ]


def _max_sample_diff(a: Image.Image, b: Image.Image, points) -> int:
    a = a.convert("RGB")
    b = b.convert("RGB")
    return max(
        max(abs(x - y) for x, y in zip(a.getpixel(p), b.getpixel(p), strict=True))
        for p in points
    )


def _mapped_box_cw(box: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    """含右下框随顺时针 90°（expand）映射到新坐标系。点 (x,y)→(H-1-y, x)。"""
    l, t, r, b = box
    height = size[1]
    return (height - 1 - b, l, height - 1 - t, r)


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    iw = max(0, min(a[2], b[2]) - max(a[0], b[0]) + 1)
    ih = max(0, min(a[3], b[3]) - max(a[1], b[1]) + 1)
    inter = iw * ih
    area_a = (a[2] - a[0] + 1) * (a[3] - a[1] + 1)
    area_b = (b[2] - b[0] + 1) * (b[3] - b[1] + 1)
    return inter / (area_a + area_b - inter)


def _strip_on_tint(size: tuple[int, int] = (640, 480)) -> bytes:
    """偏暖纯色背景 + 白/灰/黑三联参考条（Ruling 19）。

    背景带强色偏：校色要是裁错区域，增益来自背景而不是灰卡，灰卡就不再中性。
    """
    img = Image.new("RGB", size, (200, 120, 60))
    d = ImageDraw.Draw(img)
    cards = {
        "white": (120, 160, 239, 319),
        "gray": (250, 160, 369, 319),
        "black": (380, 160, 499, 319),
    }
    d.rectangle(cards["white"], fill=(245, 245, 245))
    d.rectangle(cards["gray"], fill=(128, 128, 128))
    d.rectangle(cards["black"], fill=(35, 35, 35))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_rotate_keeps_the_source_in_the_same_size_and_orientation(tmp_path):
    # 核心钉：`_src` 与工作图任何时刻同尺寸同朝向。90° 后两者都应是尺寸对调。
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER, image_data=_jpeg_bytes(size=(600, 400)), original_filename="coat.jpg"
    )
    src = tmp_path / paths["calibration_original_path"]

    rotated = svc.rotate_image(paths["image_path"], "cw")

    working_size = Image.open(tmp_path / rotated["image_path"]).size
    src_size = Image.open(src).size
    assert working_size == (400, 600)  # 600x400 顺时针 90°
    assert src_size == working_size, "校色副本必须和工作图始终同尺寸同朝向"

    rotated_back = svc.rotate_image(rotated["image_path"], "ccw")
    assert Image.open(tmp_path / rotated_back["image_path"]).size == (600, 400)
    assert Image.open(src).size == (600, 400)


@pytest.mark.asyncio
async def test_rotate_transforms_the_source_pixels_exactly(tmp_path):
    # `_src` 像素 = 旋转前 `_src` 做同样 90° 精确旋转。容差只留给 JPEG 重编码。
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER, image_data=_block_image(), original_filename="coat.jpg"
    )
    src = tmp_path / paths["calibration_original_path"]
    expected = Image.open(src).convert("RGB").transpose(Image.Transpose.ROTATE_270)

    svc.rotate_image(paths["image_path"], "cw")

    after = Image.open(src).convert("RGB")
    assert after.size == expected.size
    # 几何映射是逐像素精确的；容差只留给 JPEG 重编码（见 _mean_channel_diff）。
    sample_diff = _max_sample_diff(after, expected, _quadrant_samples(expected.size))
    assert sample_diff <= 2, f"取样点偏差超容差: max channel diff {sample_diff}"
    mean_diff = _mean_channel_diff(after, expected)
    assert mean_diff < 1.0, f"整体重编码损失过大: mean channel diff {mean_diff}"


@pytest.mark.asyncio
async def test_reset_after_rotate_restores_the_rotated_original(tmp_path):
    # 「重置回原图」= 当前朝向下的校色前像素，不得连用户的旋转一起撤销。
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER, image_data=_block_image(), original_filename="coat.jpg"
    )
    src = tmp_path / paths["calibration_original_path"]
    expected = Image.open(src).convert("RGB").transpose(Image.Transpose.ROTATE_270)

    rotated = svc.rotate_image(paths["image_path"], "cw")
    out = svc.reset_calibration(rotated["image_path"], paths["calibration_original_path"])

    restored = Image.open(tmp_path / out["image_path"]).convert("RGB")
    assert restored.size == (400, 600), "重置把用户的旋转意图撤销了"
    assert restored.size == expected.size
    sample_diff = _max_sample_diff(restored, expected, _quadrant_samples(expected.size))
    assert sample_diff <= 2, f"重置后不是旋转后的原图像素: max channel diff {sample_diff}"
    # 点位证明是旋转后的像素，不是碰巧同尺寸：红块（原左上）→顺时针后在右上，
    # 蓝块（原左下）→在左上。
    assert restored.getpixel((350, 50))[0] > 180, "右上应是旋转过来的红块"
    assert restored.getpixel((50, 50))[2] > 180, "左上应是旋转过来的蓝块"


@pytest.mark.asyncio
async def test_detect_boxes_stay_in_one_coordinate_space_across_a_rotate(tmp_path):
    # 端到端：旋转前后 detect 的框映射到同一物理区域；框喂给 calibrate 裁的是
    # 同一块像素（输出该区域中性）。坐标空间分裂在这里出错色，甚至静默。
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER, image_data=_strip_on_tint(), original_filename="coat.jpg"
    )
    before_img = Image.open(tmp_path / paths["image_path"]).convert("RGB")
    ref_before = detect_reference(before_img)
    assert ref_before is not None and ref_before.kind == "gray"

    rotated = svc.rotate_image(paths["image_path"], "cw")
    after_img = Image.open(tmp_path / rotated["image_path"]).convert("RGB")
    ref_after = detect_reference(after_img)
    assert ref_after is not None and ref_after.kind == "gray"

    # 旋转前后两个框映射到同一物理区域
    mapped = _mapped_box_cw(ref_before.box, before_img.size)
    assert _iou(mapped, ref_after.box) > 0.8, f"{mapped} vs {ref_after.box}"

    # detect 框喂给 calibrate：裁到的就是灰卡，输出对应区域中性；输出保持旋转后尺寸
    out = svc.calibrate_image(
        rotated["image_path"], paths["calibration_original_path"], ref_after.box, "gray"
    )
    result = Image.open(tmp_path / out["image_path"]).convert("RGB")
    assert result.size == after_img.size, "校色输出丢了旋转朝向（裁的是未旋转的副本）"
    l, t, r, b = ref_after.box
    region = result.crop((l, t, r + 1, b + 1))
    data = region.convert("RGB").tobytes()
    mean = [sum(data[c::3]) / (len(data) / 3) for c in range(3)]
    assert max(mean) - min(mean) <= 3, f"参考块区域应中性，实际均值 {mean}"


@pytest.mark.asyncio
async def test_rotate_without_a_source_still_rotates_working_image_and_mask(
    tmp_path, monkeypatch
):
    # keep_source=False 的附加图没有 `_src`：rotate 只转工作图 + mask，不报错。
    def _half_opaque_provider():
        class FakeProvider:
            def remove(self, image):
                rgba = image.convert("RGBA")
                alpha = Image.new("L", rgba.size, 0)
                for x in range(rgba.width // 2):
                    for y in range(rgba.height):
                        alpha.putpixel((x, y), 255)
                rgba.putalpha(alpha)
                return rgba

        return FakeProvider()

    monkeypatch.setattr(
        "app.services.background_removal.get_provider", lambda: _half_opaque_provider()
    )
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER,
        image_data=_jpeg_bytes(size=(600, 400)),
        original_filename="detail.jpg",
        keep_source=False,
    )
    assert paths["calibration_original_path"] is None
    out = svc.remove_background(paths["image_path"])

    rotated = svc.rotate_image(out["image_path"], "cw")  # 不抛错

    main = Image.open(tmp_path / rotated["image_path"])
    assert main.size == (400, 600)
    mask = Image.open(tmp_path / out["mask_path"])
    assert mask.size == (400, 600)
    assert main.getchannel("A").tobytes() == mask.tobytes()


@pytest.mark.asyncio
async def test_a_corrupt_source_fails_rotate_loudly_without_touching_the_working_image(
    tmp_path,
):
    # `_src` 转失败必须抛错，不许只转工作图就返回——那正是本 bug 的形态。
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER, image_data=_jpeg_bytes(size=(600, 400)), original_filename="coat.jpg"
    )
    (tmp_path / paths["calibration_original_path"]).write_bytes(b"not a jpeg")
    working_before = (tmp_path / paths["image_path"]).read_bytes()

    with pytest.raises((OSError, ValueError)):
        svc.rotate_image(paths["image_path"], "cw")

    assert (tmp_path / paths["image_path"]).read_bytes() == working_before, (
        "副本旋转失败时工作图不得已经被改写"
    )
    assert list(tmp_path.rglob("*.tmp")) == [], "失败路径不许留下 .tmp 孤儿"


@pytest.mark.asyncio
async def test_a_failed_size_save_leaves_the_source_bytes_untouched(tmp_path, monkeypatch):
    # F1：`_src` 是不可变基线。`_save_all_sizes` 抛错（ENOSPC 等）时它必须**逐字节
    # 不变**——既不能被 write_bytes 先截断毁掉（校色从此永远无法重置），也不能已经
    # 换成旋转后的版本（失败可重试，重试会再转 90°，尺寸回到原样却朝向已错）。
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(
        user_id=USER, image_data=_jpeg_bytes(size=(600, 400)), original_filename="coat.jpg"
    )
    src = tmp_path / paths["calibration_original_path"]
    before = src.read_bytes()

    def _disk_full(*args, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(svc, "_save_all_sizes", _disk_full)
    with pytest.raises(OSError):
        svc.rotate_image(paths["image_path"], "cw")

    assert src.read_bytes() == before, "`_src` 必须原样保留：不截断、不提前换成旋转版"
    assert list(tmp_path.rglob("*.tmp")) == [], "失败路径不许留下 .tmp 孤儿"


def _quadrant_jpeg() -> bytes:
    """400×300，左上 100×100 红块、其余灰：旋转方向错了红块会落在别的角。"""
    img = Image.new("RGB", (400, 300), (128, 128, 128))
    img.paste((220, 30, 30), (0, 0, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _opaque_left_half_provider():
    class FakeProvider:
        def remove(self, image):
            rgba = image.convert("RGBA")
            alpha = Image.new("L", rgba.size, 0)
            alpha.paste(255, (0, 0, rgba.width // 2, rgba.height))
            rgba.putalpha(alpha)
            return rgba

    return FakeProvider()


@pytest.mark.anyio
async def test_rotate_keeps_the_cutout_backup_in_the_working_orientation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.background_removal.get_provider", lambda: _opaque_left_half_provider()
    )
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(USER, _quadrant_jpeg(), "coat.jpg")
    out = svc.remove_background(paths["image_path"])

    svc.rotate_image(out["image_path"], "cw")

    backup = Image.open(tmp_path / out["original_backup_path"]).convert("RGB")
    assert backup.size == (300, 400), "the cutout backup was not rotated"
    # 顺时针 90°：左上红块 → 右上
    r, g, b = backup.getpixel((250, 50))
    assert r > 180 and g < 80, f"backup rotated the wrong way: {(r, g, b)}"

    restored = svc.restore_original(out["image_path"], out["original_backup_path"])
    working = Image.open(tmp_path / restored["image_path"])
    source = Image.open(tmp_path / paths["calibration_original_path"])
    assert working.size == source.size == (300, 400), "restore split working and _src orientation"


@pytest.mark.anyio
async def test_a_corrupt_backup_fails_rotate_without_touching_anything(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.background_removal.get_provider", lambda: _opaque_left_half_provider()
    )
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(USER, _quadrant_jpeg(), "coat.jpg")
    out = svc.remove_background(paths["image_path"])
    (tmp_path / out["original_backup_path"]).write_bytes(b"not an image")

    working_before = (tmp_path / out["image_path"]).read_bytes()
    source_before = (tmp_path / paths["calibration_original_path"]).read_bytes()

    with pytest.raises(Exception):
        svc.rotate_image(out["image_path"], "cw")

    assert (tmp_path / out["image_path"]).read_bytes() == working_before
    assert (tmp_path / paths["calibration_original_path"]).read_bytes() == source_before
    assert not list(tmp_path.rglob("*.tmp")), "staged temp files were left behind"


@pytest.mark.anyio
async def test_a_failed_tmp_write_leaves_no_orphan_and_no_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.background_removal.get_provider", lambda: _opaque_left_half_provider()
    )
    svc = ImageService(storage_path=str(tmp_path))
    paths = await svc.process_and_store(USER, _quadrant_jpeg(), "coat.jpg")
    out = svc.remove_background(paths["image_path"])

    working_before = (tmp_path / out["image_path"]).read_bytes()
    source_before = (tmp_path / paths["calibration_original_path"]).read_bytes()

    real_write_bytes = Path.write_bytes

    def failing_write_bytes(self, data):
        if self.name.endswith(".tmp"):
            real_write_bytes(self, data[: len(data) // 2])
            raise OSError(28, "No space left on device")
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", failing_write_bytes)

    with pytest.raises(OSError):
        svc.rotate_image(out["image_path"], "cw")

    monkeypatch.undo()
    assert not list(tmp_path.rglob("*.tmp")), "a partial .tmp was left behind"
    assert (tmp_path / out["image_path"]).read_bytes() == working_before
    assert (tmp_path / paths["calibration_original_path"]).read_bytes() == source_before
