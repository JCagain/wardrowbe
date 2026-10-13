"""主图文件集命名约定：一切派生路径从 base 推，扩展名翻转不改 base。"""
import uuid
from types import SimpleNamespace

import pytest
from PIL import Image

from app.services.image_files import ImageFiles, assign_size_paths
from app.services.image_service import ImageService

USER = uuid.UUID("00000000-0000-0000-0000-000000000021")


def test_derived_paths_share_the_base_across_an_extension_flip():
    jpg = ImageFiles.of("u/20240116_abc.jpg")
    png = ImageFiles.of("u/20240116_abc.png")
    assert jpg == png
    assert jpg.base == "u/20240116_abc"
    assert jpg.source == "u/20240116_abc_src.jpg"
    assert jpg.backup == "u/20240116_abc_orig.jpg"
    assert jpg.mask == "u/20240116_abc_mask.png"
    assert jpg.sizes(".png") == {
        "image_path": "u/20240116_abc.png",
        "medium_path": "u/20240116_abc_medium.png",
        "thumbnail_path": "u/20240116_abc_thumb.png",
    }


@pytest.mark.anyio
async def test_stored_upload_paths_follow_the_convention(tmp_path):
    import io

    svc = ImageService(storage_path=str(tmp_path))
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 20, 30)).save(buf, format="JPEG")
    paths = await svc.process_and_store(USER, buf.getvalue(), "coat.jpg")

    files = ImageFiles.of(paths["image_path"])
    assert {k: paths[k] for k in ("image_path", "medium_path", "thumbnail_path")} == files.sizes(".jpg")
    assert paths["calibration_original_path"] == files.source


def test_assign_size_paths_writes_exactly_the_three_size_columns():
    item = SimpleNamespace(image_path="a.jpg", medium_path="a_medium.jpg",
                           thumbnail_path="a_thumb.jpg", mask_path="a_mask.png")
    assign_size_paths(item, {
        "image_path": "a.png", "medium_path": "a_medium.png",
        "thumbnail_path": "a_thumb.png", "mask_path": "IGNORED", "mask_cleared": True,
    })
    assert (item.image_path, item.medium_path, item.thumbnail_path) == (
        "a.png", "a_medium.png", "a_thumb.png")
    assert item.mask_path == "a_mask.png"
