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


def _rembg_like_provider():
    """像真实 rembg 一样：左半不透明、右半透明，且透明区 RGB 清零。"""

    class FakeProvider:
        def __init__(self):
            self.inputs: list[Image.Image] = []

        def remove(self, image):
            self.inputs.append(image.copy())
            rgba = image.convert("RGBA")
            cleared = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
            keep = Image.new("L", rgba.size, 0)
            keep.paste(255, (0, 0, rgba.width // 2, rgba.height))
            return Image.composite(rgba, cleared, keep)

    return FakeProvider()


async def _cut(tmp_path, monkeypatch, provider=None):
    provider = provider or _rembg_like_provider()
    monkeypatch.setattr("app.services.background_removal.get_provider", lambda: provider)
    svc = ImageService(storage_path=str(tmp_path))
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 60, 60)).save(buf, format="JPEG", quality=95)
    paths = await svc.process_and_store(USER, buf.getvalue(), "coat.jpg")
    return svc, paths, svc.remove_background(paths["image_path"]), provider


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
    assert not (tmp_path / out["original_backup_path"]).exists(), (
        "the cutout backup must be retired with the matte"
    )


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


# ---------------------------------------------------------------- mask 画笔（Task 6）


def _stroke_core_alpha_mean(img: Image.Image, stroke: dict, ref_size: tuple[int, int]) -> float:
    """笔画圆盘**内部**的 alpha 均值（取样框按 derived 尺寸缩放）。

    取样框 = 缩放后的中心 ± 半径的一半，整个框落在圆盘内部。LANCZOS 只在笔画
    边缘插值，进不了内部，所以拿区域均值比阈值、不逐像素取等值——钉子对
    重采样不敏感，且不会把「没重写」误判成通过（crop 出界 PIL 补 0，先夹紧）。
    """
    sx = img.size[0] / ref_size[0]
    sy = img.size[1] / ref_size[1]
    cx = stroke["x"] * sx
    cy = stroke["y"] * sy
    half = stroke["radius"] * min(sx, sy) * 0.5
    box = (
        max(0, int(cx - half)),
        max(0, int(cy - half)),
        min(img.size[0], int(cx + half) + 1),
        min(img.size[1], int(cy + half) + 1),
    )
    region = img.convert("RGBA").getchannel("A").crop(box)
    values = list(region.getdata())
    return sum(values) / len(values)


def test_strokes_add_and_subtract_from_the_mask():
    # add 涂白（补抠）、subtract 涂黑（擦多余）；同一笔画列表内按顺序叠加
    mask = Image.new("L", (100, 100), 0)
    out = mask_service.apply_strokes(mask, [
        {"x": 50, "y": 50, "radius": 10, "mode": "add"},
        {"x": 50, "y": 50, "radius": 4, "mode": "subtract"},
    ])
    assert out.getpixel((50, 50)) == 0      # 中心被减掉
    assert out.getpixel((56, 50)) == 255    # 外圈仍在


def test_later_strokes_override_earlier_ones():
    # R1 契约：后画的笔画覆盖先画的（顺序反了这两种断言都会翻）
    mask = Image.new("L", (100, 100), 0)
    out = mask_service.apply_strokes(mask, [
        {"x": 50, "y": 50, "radius": 10, "mode": "add"},
        {"x": 50, "y": 50, "radius": 10, "mode": "subtract"},
    ])
    assert out.getpixel((50, 50)) == 0

    out = mask_service.apply_strokes(mask, [
        {"x": 50, "y": 50, "radius": 10, "mode": "subtract"},
        {"x": 50, "y": 50, "radius": 10, "mode": "add"},
    ])
    assert out.getpixel((50, 50)) == 255


def test_strokes_land_on_full_resolution_mask_pixels():
    # R1：坐标就是全分辨率 mask 像素，apply_strokes 内不做任何缩放
    # （若把坐标乘个系数，(50,50) 会被画到别处，第一条断言变红）
    mask = Image.new("L", (100, 100), 0)
    out = mask_service.apply_strokes(mask, [
        {"x": 50, "y": 50, "radius": 5, "mode": "add"},
    ])
    assert out.getpixel((50, 50)) == 255
    assert out.getpixel((58, 50)) == 0, "outside the brush radius nothing may change"


@pytest.mark.anyio
async def test_updating_the_mask_regenerates_all_three_sizes(tmp_path, monkeypatch):
    # fixes #13：改 mask 后**三档**必须一起重生成（否则网格缩略图与详情大图
    # 显示不同抠图）。只重写主图、让 medium/thumbnail 持旧像素在下面两档的
    # 内容钉子处变红——存在/扩展名检查抓不住那种实现。
    class FakeProvider:
        def remove(self, image):
            rgba = image.convert("RGBA")
            rgba.putalpha(Image.new("L", rgba.size, 255))
            return rgba

    monkeypatch.setattr("app.services.background_removal.get_provider", lambda: FakeProvider())
    svc = ImageService(storage_path=str(tmp_path))
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 60, 60)).save(buf, format="JPEG")
    paths = await svc.process_and_store(USER, buf.getvalue(), "coat.jpg")
    out = svc.remove_background(paths["image_path"])

    stroke = {"x": 10, "y": 10, "radius": 20, "mode": "subtract"}
    ref_size = Image.open(tmp_path / out["image_path"]).size
    # derived 两档改前的内容快照：钉「改前 → 改后」，不是只看文件存在
    before = {
        key: {
            "bytes": (tmp_path / out[key]).read_bytes(),
            "core_alpha_mean": _stroke_core_alpha_mean(
                Image.open(tmp_path / out[key]), stroke, ref_size
            ),
        }
        for key in ("medium_path", "thumbnail_path")
    }

    updated = svc.update_mask(
        out["image_path"], out["mask_path"], out["original_backup_path"], [stroke]
    )

    for key in ("image_path", "medium_path", "thumbnail_path"):
        assert (tmp_path / updated[key]).exists()
        assert updated[key].endswith(".png")
    main = Image.open(tmp_path / updated["image_path"])
    assert main.getchannel("A").getpixel((10, 10)) == 0
    # R1：坐标不缩放 —— (10,10) 就是 (10,10)
    mask = Image.open(tmp_path / updated["mask_path"])
    assert mask.getpixel((10, 10)) == 0
    assert mask.getpixel((200, 150)) == 255   # 减的是左上角，别处没动

    # #13 的洞：medium/thumbnail 的**内容**必须带上笔画。两断言分工——
    # 字节变了 = 真被重写过（没动过会持旧字节）；圆盘内部均值塌下去 =
    # 内容跟上了笔画（重写了但没合成 alpha 的也过不了）。
    for key in ("medium_path", "thumbnail_path"):
        rel = updated[key]
        snap = before[key]
        assert snap["core_alpha_mean"] > 200, f"{key} pre-edit core was not opaque"
        assert (tmp_path / rel).read_bytes() != snap["bytes"], f"{key} was not rewritten"
        after_mean = _stroke_core_alpha_mean(Image.open(tmp_path / rel), stroke, ref_size)
        assert after_mean < 64, (
            f"{key} does not carry the stroke (core alpha mean {after_mean:.1f})"
        )


@pytest.mark.anyio
async def test_mask_size_mismatch_raises_and_writes_nothing(tmp_path, monkeypatch):
    # R2：mask 与主图尺寸不一致 = 损坏/别的 bug，抛 ValueError 且一个文件都不许动。
    # 静默 resize 会产垃圾，还会把三档重写掉（两条断言都会翻）。
    class FakeProvider:
        def remove(self, image):
            rgba = image.convert("RGBA")
            rgba.putalpha(Image.new("L", rgba.size, 255))
            return rgba

    monkeypatch.setattr("app.services.background_removal.get_provider", lambda: FakeProvider())
    svc = ImageService(storage_path=str(tmp_path))
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 60, 60)).save(buf, format="JPEG")
    paths = await svc.process_and_store(USER, buf.getvalue(), "coat.jpg")
    out = svc.remove_background(paths["image_path"])

    # 旁挂被换成 10×10，和 400×300 的主图对不上
    mask_service.save_mask(Image.new("L", (10, 10), 255), tmp_path / out["mask_path"])

    tracked = [out["image_path"], out["medium_path"], out["thumbnail_path"], out["mask_path"]]
    before = {rel: (tmp_path / rel).read_bytes() for rel in tracked}

    with pytest.raises(ValueError):
        svc.update_mask(
            out["image_path"],
            out["mask_path"],
            out["original_backup_path"],
            [{"x": 5, "y": 5, "radius": 4, "mode": "add"}],
        )

    for rel, data in before.items():
        assert (tmp_path / rel).read_bytes() == data, f"{rel} was rewritten"


@pytest.mark.anyio
async def test_brush_add_restores_the_true_pixels_not_black(tmp_path, monkeypatch):
    svc, _, out, _ = await _cut(tmp_path, monkeypatch)
    stroke = {"x": 300, "y": 150, "radius": 30, "mode": "add"}  # 右半透明区

    updated = svc.update_mask(
        out["image_path"], out["mask_path"], out["original_backup_path"], [stroke]
    )

    main = Image.open(tmp_path / updated["image_path"]).convert("RGBA")
    r, g, b, a = main.getpixel((300, 150))
    assert a == 255
    assert max(abs(r - 200), abs(g - 60), abs(b - 60)) <= 12, (
        f"brush-added pixels must be the original colour, got {(r, g, b)}"
    )


@pytest.mark.anyio
async def test_recutting_feeds_the_provider_the_uncut_pixels(tmp_path, monkeypatch):
    svc, _, out, provider = await _cut(tmp_path, monkeypatch)

    svc.remove_background(out["image_path"])

    second_input = provider.inputs[-1].convert("RGB")
    r, g, b = second_input.getpixel((300, 150))
    assert r > 150, f"re-cut ran on the already-cut (black) image: {(r, g, b)}"


@pytest.mark.anyio
async def test_brush_after_rotate_restores_the_true_pixels(tmp_path, monkeypatch):
    svc, _, out, _ = await _cut(tmp_path, monkeypatch)
    svc.rotate_image(out["image_path"], "cw")  # 400×300 → 300×400，右半透明区转到下半
    stroke = {"x": 150, "y": 300, "radius": 30, "mode": "add"}

    updated = svc.update_mask(
        out["image_path"], out["mask_path"], out["original_backup_path"], [stroke]
    )

    r, g, b, a = Image.open(tmp_path / updated["image_path"]).convert("RGBA").getpixel((150, 300))
    assert a == 255 and r > 150, f"brush after rotate painted {(r, g, b, a)}"


@pytest.mark.anyio
async def test_update_mask_without_a_backup_raises_and_writes_nothing(tmp_path, monkeypatch):
    svc, _, out, _ = await _cut(tmp_path, monkeypatch)
    (tmp_path / out["original_backup_path"]).unlink()
    before = (tmp_path / out["image_path"]).read_bytes()

    with pytest.raises(ValueError, match="Cutout backup not found"):
        svc.update_mask(out["image_path"], out["mask_path"], out["original_backup_path"],
                        [{"x": 1, "y": 1, "radius": 5, "mode": "add"}])

    assert (tmp_path / out["image_path"]).read_bytes() == before


def _make_stale_backup(svc, out):
    """旧版本遗留：工作图 300x400，备份却是旋转前的 400x300。"""
    working = svc.storage_path / out["image_path"]
    backup = svc.storage_path / out["original_backup_path"]
    Image.new("RGBA", (300, 400), (10, 20, 30, 255)).save(working, format="PNG")
    Image.new("RGB", (400, 300), (200, 60, 60)).save(backup, format="JPEG")
    return working, backup


@pytest.mark.anyio
async def test_recut_reseeds_a_stale_backup_instead_of_unrotating(tmp_path, monkeypatch):
    svc, _, out, _ = await _cut(tmp_path, monkeypatch)
    working, backup = _make_stale_backup(svc, out)

    result = svc.remove_background(out["image_path"])

    assert Image.open(tmp_path / result["image_path"]).size == (300, 400)
    assert Image.open(backup).size == (300, 400)


@pytest.mark.anyio
async def test_restore_original_refuses_a_stale_backup(tmp_path, monkeypatch):
    svc, _, out, _ = await _cut(tmp_path, monkeypatch)
    working, backup = _make_stale_backup(svc, out)
    working_bytes, backup_bytes = working.read_bytes(), backup.read_bytes()

    with pytest.raises(ValueError):
        svc.restore_original(out["image_path"], out["original_backup_path"])

    assert working.read_bytes() == working_bytes
    assert backup.read_bytes() == backup_bytes
