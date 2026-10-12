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
