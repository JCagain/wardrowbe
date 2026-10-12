import io
import uuid

import pytest
from PIL import Image

from app.services import mask_service
from app.services.image_service import ImageService

USER = uuid.UUID("00000000-0000-0000-0000-000000000011")


def _half_opaque_provider():
    """Left half opaque (alpha 255), right half transparent (alpha 0)."""

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


@pytest.mark.anyio
async def test_removing_background_stores_transparent_png_and_a_mask_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.background_removal.get_provider", lambda: _half_opaque_provider()
    )

    svc = ImageService(storage_path=str(tmp_path))
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 60, 60)).save(buf, format="JPEG")
    paths = await svc.process_and_store(USER, buf.getvalue(), "coat.jpg")

    out = svc.remove_background(paths["image_path"])

    # 主图三档都必须是透明 PNG：存回 JPG（或把 alpha 压掉）在这里变红
    for key in ("image_path", "medium_path", "thumbnail_path"):
        assert out[key].endswith(".png"), f"{key} is not a PNG: {out[key]}"
        main = Image.open(tmp_path / out[key])
        assert main.mode == "RGBA", f"{key} lost its alpha channel: {main.mode}"
    main = Image.open(tmp_path / out["image_path"])
    assert main.getchannel("A").getextrema() == (0, 255)

    # mask 旁挂：没落盘 / 存成 RGB / 内容跟 alpha 对不上都变红
    mask = Image.open(tmp_path / out["mask_path"])
    assert mask.mode == "L"
    assert mask.size == main.size
    assert mask.getextrema() == (0, 255)
    assert list(mask.getdata()) == list(main.getchannel("A").getdata())


def test_composite_on_white_does_not_write_files(tmp_path, monkeypatch):
    # 把 cwd 指到空目录：任何相对路径落盘都会被发现
    monkeypatch.chdir(tmp_path)

    def _no_write(*args, **kwargs):
        raise AssertionError("composite_on_white must not write files")

    monkeypatch.setattr(Image.Image, "save", _no_write)
    monkeypatch.setattr("pathlib.Path.write_bytes", _no_write)

    rgba = Image.new("RGBA", (10, 10), (255, 0, 0, 0))
    rgba.putpixel((5, 5), (255, 0, 0, 255))
    flat = mask_service.composite_on_white(rgba)
    assert flat.mode == "RGB"
    assert flat.getpixel((5, 5)) == (255, 0, 0)
    assert flat.getpixel((0, 0)) == (255, 255, 255)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.anyio
async def test_rotating_keeps_the_alpha_and_rotates_the_mask(tmp_path, monkeypatch):
    # 旋转是几何变换：抠图 alpha 跟着转，mask 旁挂同角度旋转，不得铺白底丢 alpha
    monkeypatch.setattr(
        "app.services.background_removal.get_provider", lambda: _half_opaque_provider()
    )
    svc = ImageService(storage_path=str(tmp_path))
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 60, 60)).save(buf, format="JPEG")
    paths = await svc.process_and_store(USER, buf.getvalue(), "coat.jpg")
    out = svc.remove_background(paths["image_path"])
    assert Image.open(tmp_path / out["mask_path"]).getpixel((20, 150)) == 255  # 左半不透

    rotated = svc.rotate_image(out["image_path"], "cw")

    main = Image.open(tmp_path / rotated["image_path"])
    assert main.mode == "RGBA", f"rotation flattened the matte: {main.mode}"
    assert main.size == (300, 400)  # 400x300 顺时针 90°
    # 左半不透 → 顺时针后上半不透；右半透 → 下半透。转 90° 后检查上下半。
    mask = Image.open(tmp_path / out["mask_path"])
    assert mask.mode == "L"
    assert mask.size == (300, 400)
    assert mask.getpixel((150, 100)) == 255, "opaque left half must become the top half"
    assert mask.getpixel((150, 300)) == 0, "transparent right half must become the bottom half"
    # 主图 alpha 与旋转后的 mask 仍逐点一致
    alpha = main.getchannel("A")
    assert list(alpha.getdata()) == list(mask.getdata())


@pytest.mark.anyio
@pytest.mark.parametrize("op_name", ["apply", "manual", "reset"])
async def test_calibrating_clears_the_stale_mask(tmp_path, monkeypatch, op_name):
    # 校色从 `_src.jpg` 重推导像素，抠图结果必然不再对应——mask 不清就是过期 mask，
    # 后续 update_mask 会拿它合成垃圾。三处都要清：文件删掉 + 响应报 mask_cleared。
    monkeypatch.setattr(
        "app.services.background_removal.get_provider", lambda: _half_opaque_provider()
    )
    svc = ImageService(storage_path=str(tmp_path))
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 60, 60)).save(buf, format="JPEG")
    paths = await svc.process_and_store(USER, buf.getvalue(), "coat.jpg")
    out = svc.remove_background(paths["image_path"])
    mask_file = tmp_path / out["mask_path"]
    assert mask_file.exists()

    if op_name == "apply":
        result = svc.calibrate_image(
            out["image_path"], paths["calibration_original_path"], (0, 0, 50, 50), "gray"
        )
    elif op_name == "manual":
        result = svc.manual_white_balance(
            out["image_path"], paths["calibration_original_path"], kelvin=6500.0, tint=0.0
        )
    else:
        result = svc.reset_calibration(out["image_path"], paths["calibration_original_path"])

    assert result["mask_cleared"] is True
    assert not mask_file.exists(), "the stale mask sidecar must be deleted"


@pytest.mark.anyio
@pytest.mark.parametrize("op_name", ["apply", "manual", "reset"])
async def test_calibrating_without_a_mask_reports_nothing_cleared(tmp_path, op_name):
    # 从没抠过的图校色完不该弹「请重抠」：mask_cleared 只在真删了 mask 文件时为 True，
    # 没有文件可删就是 False（把「真删才 True」的判断去掉会变红）
    svc = ImageService(storage_path=str(tmp_path))
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 60, 60)).save(buf, format="JPEG")
    paths = await svc.process_and_store(USER, buf.getvalue(), "coat.jpg")

    if op_name == "apply":
        result = svc.calibrate_image(
            paths["image_path"], paths["calibration_original_path"], (0, 0, 50, 50), "gray"
        )
    elif op_name == "manual":
        result = svc.manual_white_balance(
            paths["image_path"], paths["calibration_original_path"], kelvin=6500.0, tint=0.0
        )
    else:
        result = svc.reset_calibration(paths["image_path"], paths["calibration_original_path"])

    assert result["mask_cleared"] is False


def test_flipping_the_format_removes_the_orphaned_variants(tmp_path):
    # 换扩展名写出新档后，旧扩展名的三档是无引用孤儿（磁盘泄漏），必须删掉
    svc = ImageService(storage_path=str(tmp_path))
    (tmp_path / "u").mkdir()

    for name in ("u/item.jpg", "u/item_medium.jpg", "u/item_thumb.jpg"):
        Image.new("RGB", (100, 100), (10, 20, 30)).save(tmp_path / name, format="JPEG")
    paths = svc._save_all_sizes(Image.new("RGBA", (100, 100), (10, 200, 30, 255)), "u/item.jpg")
    assert paths["image_path"] == "u/item.png"
    for name in ("u/item.jpg", "u/item_medium.jpg", "u/item_thumb.jpg"):
        assert not (tmp_path / name).exists(), f"orphan left behind: {name}"
    for name in ("u/item.png", "u/item_medium.png", "u/item_thumb.png"):
        assert (tmp_path / name).exists()

    for name in ("u/two.png", "u/two_medium.png", "u/two_thumb.png"):
        Image.new("RGBA", (100, 100), (1, 2, 3, 255)).save(tmp_path / name, format="PNG")
    paths = svc._save_all_sizes(Image.new("RGB", (100, 100), (9, 9, 9)), "u/two.png")
    assert paths["image_path"] == "u/two.jpg"
    for name in ("u/two.png", "u/two_medium.png", "u/two_thumb.png"):
        assert not (tmp_path / name).exists(), f"orphan left behind: {name}"
    for name in ("u/two.jpg", "u/two_medium.jpg", "u/two_thumb.jpg"):
        assert (tmp_path / name).exists()

    # 同扩展名不删（重生成尺寸不得抹掉正在写的那套）
    before = tmp_path / "u/item.png"
    svc._save_all_sizes(Image.new("RGBA", (80, 80), (1, 2, 3, 255)), "u/item.png")
    assert before.exists()
