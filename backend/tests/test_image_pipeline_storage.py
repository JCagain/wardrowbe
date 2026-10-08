import io
import uuid

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem
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
