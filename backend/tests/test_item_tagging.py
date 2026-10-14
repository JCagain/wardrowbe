"""Tests for the external-agent tagging lifecycle (tagging_status/tagged_by/tagged_at):
create/bulk-create/bulk-analyze gating when vision is off or skip_ai is set, the
pending filter, the write-back guard on PATCH, retag, tag-to-column projection, and
the worker's origin stamping. Includes regressions for two review-caught bugs: the
write-back guard missing emptiness *inside* a nested tags dict, and the worker
reverting a manual origin back to auto when a queued job lands after a write-back.
"""

from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.item import ClothingItem, ItemStatus, TaggedBy, TaggingStatus
from app.schemas.item import ItemCreate, ItemTags, ItemUpdate
from app.services.ai_service import ClothingTags
from app.services.item_service import ItemService
from app.workers import tagging


def _make_test_image_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), (120, 80, 40)).save(buf, format="JPEG")
    return buf.getvalue()


async def _get_item(db_session: AsyncSession, item_id) -> ClothingItem:
    result = await db_session.execute(select(ClothingItem).where(ClothingItem.id == item_id))
    return result.scalar_one()


class TestTaggingDefaults:
    @pytest.mark.asyncio
    async def test_new_item_defaults_to_pending(self, db_session: AsyncSession, test_user):
        service = ItemService(db_session)
        item = await service.create(
            user_id=test_user.id,
            item_data=ItemCreate(type="shirt"),
            image_paths={"image_path": "test/defaults.jpg"},
        )
        assert item.tagging_status == TaggingStatus.pending
        assert item.tagged_by is None
        assert item.tagged_at is None


class TestCreateGating:
    @pytest.mark.asyncio
    async def test_default_does_not_enqueue_and_is_ready_pending(self, client: AsyncClient, auth_headers):
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "job-1"
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items",
                files={"image": ("shirt.jpg", _make_test_image_bytes(), "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["status"] == "ready"
        assert data["tagging_status"] == "pending"
        mock_redis.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_ai_marks_ready_and_pending(self, client: AsyncClient, auth_headers):
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items",
                files={"image": ("shirt.jpg", _make_test_image_bytes(), "image/jpeg")},
                data={"skip_ai": "true"},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["status"] == "ready"
        assert data["tagging_status"] == "pending"
        mock_redis.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_ai_retired_item_is_archived_not_ready(self, client: AsyncClient, auth_headers):
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items",
                files={"image": ("shirt.jpg", _make_test_image_bytes(), "image/jpeg")},
                data={"skip_ai": "true", "lifecycle": "retired"},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["lifecycle"] == "retired"
        assert data["status"] == "archived"
        assert data["tagging_status"] == "pending"
        mock_redis.enqueue_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_vision_disabled_marks_ready_and_pending(
        self, client: AsyncClient, auth_headers, monkeypatch
    ):
        monkeypatch.setattr("app.api.items.settings", Settings(ai_vision_enabled=False))
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            response = await client.post(
                "/api/v1/items",
                files={"image": ("shirt.jpg", _make_test_image_bytes(), "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["status"] == "ready"
        assert data["tagging_status"] == "pending"
        mock_create_pool.assert_not_called()


class TestBulkCreateGating:
    @pytest.mark.asyncio
    async def test_skip_ai_marks_ready_and_pending_without_pool(
        self, client: AsyncClient, auth_headers
    ):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                data={"skip_ai": "true"},
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["results"][0]["item"]["status"] == "ready"
        assert data["results"][0]["item"]["tagging_status"] == "pending"
        mock_create_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_vision_disabled_marks_ready_and_pending_without_pool(
        self, client: AsyncClient, auth_headers, monkeypatch
    ):
        monkeypatch.setattr("app.api.items.settings", Settings(ai_vision_enabled=False))
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["results"][0]["item"]["status"] == "ready"
        assert data["results"][0]["item"]["tagging_status"] == "pending"
        mock_create_pool.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_does_not_queue_and_is_ready_pending(self, client: AsyncClient, auth_headers):
        files = [("images", ("shirt.jpg", _make_test_image_bytes(), "image/jpeg"))]
        with patch("app.api.items.create_pool", new_callable=AsyncMock) as mock_create_pool:
            mock_redis = AsyncMock()
            mock_redis.enqueue_job.return_value.job_id = "job-1"
            mock_create_pool.return_value = mock_redis
            response = await client.post(
                "/api/v1/items/bulk",
                files=files,
                headers=auth_headers,
            )

        assert response.status_code == 201, response.json()
        data = response.json()
        assert data["results"][0]["item"]["status"] == "ready"
        assert data["results"][0]["item"]["tagging_status"] == "pending"
        mock_redis.enqueue_job.assert_not_called()


class TestBulkAnalyzeGating:
    @pytest.mark.asyncio
    async def test_vision_disabled_resets_items_and_reports_zero_queued(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession, monkeypatch
    ):
        monkeypatch.setattr("app.api.items.settings", Settings(ai_vision_enabled=False))

        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/bulk-analyze.jpg",
            status=ItemStatus.ready,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.auto,
            tagged_at=datetime.now(UTC),
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        response = await client.post(
            "/api/v1/items/bulk/analyze",
            json={"item_ids": [str(item.id)]},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["queued"] == 0
        assert data["failed"] == 0

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.tagging_status == TaggingStatus.pending
        assert refreshed.tagged_by is None
        assert refreshed.tagged_at is None


class TestPendingFilter:
    @pytest.mark.asyncio
    async def test_filters_to_pending_only(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        pending_item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/pending.jpg",
            status=ItemStatus.ready,
        )
        tagged_item = ClothingItem(
            user_id=test_user.id,
            type="pants",
            image_path="test/tagged.jpg",
            status=ItemStatus.ready,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.auto,
            tagged_at=datetime.now(UTC),
        )
        db_session.add_all([pending_item, tagged_item])
        await db_session.commit()

        response = await client.get(
            "/api/v1/items", params={"tagging_status": "pending"}, headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        ids = {item["id"] for item in data["items"]}
        assert ids == {str(pending_item.id)}


class TestWriteBack:
    @pytest.mark.asyncio
    async def test_real_tag_content_flips_to_tagged_manual(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/writeback.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"tags": {"colors": ["blue"], "primary_color": "blue"}},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["tagging_status"] == "tagged"
        assert data["tagged_by"] == "manual"
        assert data["tagged_at"] is not None
        # The AI JSON shape (tags.colors / tags.primary_color) projects onto
        # the new color columns at the persistence boundary.
        assert data["primary_colors"] == ["blue"]
        assert data["secondary_colors"] == []

    @pytest.mark.asyncio
    async def test_flat_empty_values_stay_pending(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/writeback-empty.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"colors": []},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["tagging_status"] == "pending"
        assert data["tagged_by"] is None

    @pytest.mark.asyncio
    async def test_empty_nested_tags_dict_stays_pending(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/writeback-nested-empty.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"tags": {"colors": []}},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["tagging_status"] == "pending"
        assert data["tagged_by"] is None

    @pytest.mark.asyncio
    async def test_body_cannot_forge_tagged_by(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/writeback-forge.jpg",
            status=ItemStatus.ready,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"tagged_by": "manual", "tagging_status": "tagged", "name": "Same Name"},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["tagging_status"] == "pending"
        assert data["tagged_by"] is None

    @pytest.mark.asyncio
    async def test_already_tagged_item_not_restamped_by_unrelated_update(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        original_tagged_at = datetime.now(UTC) - timedelta(hours=1)
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/writeback-restamp.jpg",
            status=ItemStatus.ready,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.auto,
            tagged_at=original_tagged_at,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"name": "Renamed Shirt"},
            headers=auth_headers,
        )

        assert response.status_code == 200, response.json()

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.tagging_status == TaggingStatus.tagged
        assert refreshed.tagged_by == TaggedBy.auto
        assert refreshed.tagged_at == original_tagged_at


class TestRetag:
    @pytest.mark.asyncio
    async def test_resets_to_pending_without_touching_status(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/retag.jpg",
            status=ItemStatus.ready,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.manual,
            tagged_at=datetime.now(UTC),
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.post(f"/api/v1/items/{item.id}/retag", headers=auth_headers)

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["status"] == "ready"
        assert data["tagging_status"] == "pending"
        assert data["tagged_by"] is None
        assert data["tagged_at"] is None

    @pytest.mark.asyncio
    async def test_404_for_missing_item(self, client: AsyncClient, auth_headers):
        response = await client.post(f"/api/v1/items/{uuid4()}/retag", headers=auth_headers)
        assert response.status_code == 404


def test_tag_fields_write_color_arrays_straight_to_the_columns():
    fields = tagging.tags_to_item_fields(
        ClothingTags(type="shirt", primary_colors=["black", "white"], secondary_colors=["wine"])
    )
    assert fields["primary_colors"] == ["black", "white"]
    assert fields["secondary_colors"] == ["wine"]
    assert fields["tags"]["primary_colors"] == ["black", "white"]
    assert fields["tags"]["secondary_colors"] == ["wine"]
    assert "colors" not in fields["tags"]
    assert "primary_color" not in fields["tags"]


def test_item_tags_schema_carries_new_color_keys_and_keeps_legacy_ones():
    dumped = ItemTags(primary_colors=["black"], secondary_colors=["white"]).model_dump()
    assert dumped["primary_colors"] == ["black"]
    assert dumped["secondary_colors"] == ["white"]
    legacy = ItemTags(primary_color="red", colors=["red"]).model_dump()
    assert legacy["primary_color"] == "red"
    assert legacy["colors"] == ["red"]


class TestTagsBlobNewColorKeys:
    async def _item(self, db_session, test_user, **kw):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path=f"test/{uuid4().hex}.jpg",
            status=ItemStatus.ready,
            **kw,
        )
        db_session.add(item)
        await db_session.commit()
        return item

    @pytest.mark.asyncio
    async def test_tags_blob_with_new_color_keys_projects_onto_columns(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = await self._item(db_session, test_user)
        resp = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"tags": {"primary_colors": ["black", "chartreuse"], "secondary_colors": ["white"]}},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["primary_colors"] == ["black"]
        assert body["secondary_colors"] == ["white"]

    @pytest.mark.asyncio
    async def test_explicit_color_columns_win_over_the_tags_blob(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = await self._item(db_session, test_user)
        resp = await client.patch(
            f"/api/v1/items/{item.id}",
            json={
                "primary_colors": ["navy"],
                "secondary_colors": [],
                "tags": {"primary_colors": ["black"], "secondary_colors": ["white"]},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["primary_colors"] == ["navy"]
        assert resp.json()["secondary_colors"] == []

    @pytest.mark.asyncio
    async def test_tags_blob_with_empty_new_color_keys_does_not_clear_columns(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession
    ):
        item = await self._item(db_session, test_user, primary_colors=["black"])
        resp = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"tags": {"primary_colors": [], "secondary_colors": []}},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["primary_colors"] == ["black"]

    @pytest.mark.asyncio
    async def test_disabled_vocab_color_is_dropped_from_blob_projection(
        self, client: AsyncClient, auth_headers, test_user, db_session: AsyncSession, vocab_file
    ):
        import json
        import os

        data = json.loads(vocab_file.read_text())
        for c in data["colors"]["values"]:
            if c["value"] == "white":
                c["disabled"] = True
        before = vocab_file.stat().st_mtime_ns
        vocab_file.write_text(json.dumps(data, ensure_ascii=False))
        if vocab_file.stat().st_mtime_ns <= before:
            os.utime(vocab_file, ns=(before + 1_000_000, before + 1_000_000))

        item = await self._item(db_session, test_user)
        resp = await client.patch(
            f"/api/v1/items/{item.id}",
            json={"tags": {"primary_colors": ["black"], "secondary_colors": ["white"]}},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.json()
        assert resp.json()["primary_colors"] == ["black"]
        assert resp.json()["secondary_colors"] == []


class TestTagsToColumnsProjection:
    @pytest.mark.asyncio
    async def test_update_projects_nested_tag_fields_onto_columns(
        self, db_session: AsyncSession, test_user
    ):
        service = ItemService(db_session)
        item = await service.create(
            user_id=test_user.id,
            item_data=ItemCreate(type="unknown"),
            image_paths={"image_path": "test/projection.jpg"},
        )

        updated = await service.update(
            item,
            ItemUpdate(
                tags=ItemTags(
                    colors=["red"],
                    primary_color="red",
                    pattern="striped",
                    material="cotton",
                    style=["casual"],
                    season=["summer"],
                    formality="casual",
                )
            ),
        )

        # tags.colors / tags.primary_color (AI JSON shape) land on the new
        # color columns: primary_color wins primary_colors, colors minus the
        # primary become secondary_colors.
        assert updated.primary_colors == ["red"]
        assert updated.secondary_colors == []
        assert updated.pattern == "striped"
        assert updated.material == "cotton"
        assert updated.style == ["casual"]
        assert updated.season == ["summer"]
        assert updated.formality == "casual"


class TestWorkerTaggingOrigin:
    @pytest.fixture(autouse=True)
    def _storage_with_item_images(self, tmp_path, monkeypatch):
        # The worker resolves its input from the item row under storage_path (Ruling 48).
        from PIL import Image as _Image

        settings = tagging.get_settings().model_copy(update={"storage_path": str(tmp_path)})
        monkeypatch.setattr(tagging, "get_settings", lambda: settings)
        (tmp_path / "test").mkdir()
        for name in ("worker-auto", "worker-retired", "worker-race"):
            _Image.new("RGB", (8, 8)).save(tmp_path / "test" / f"{name}.jpg")

    @pytest.mark.asyncio
    async def test_happy_path_stamps_auto(self, db_session: AsyncSession, test_user, monkeypatch):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/worker-auto.jpg",
            status=ItemStatus.processing,
        )
        db_session.add(item)
        await db_session.commit()

        stub_tags = ClothingTags(
            type="shirt", primary_colors=["blue"], confidence=0.9
        )

        class _StubAI:
            def __init__(self, *args, **kwargs):
                pass

            async def analyze_image(self, path):
                return stub_tags

        monkeypatch.setattr(tagging, "AIService", _StubAI)

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await tagging.tag_item_image({}, str(item.id), __file__)

        assert result["status"] == "success"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.tagging_status == TaggingStatus.tagged
        assert refreshed.tagged_by == TaggedBy.auto
        assert refreshed.tagged_at is not None
        assert refreshed.status == ItemStatus.ready

    @pytest.mark.asyncio
    async def test_retired_item_stays_archived_after_tagging(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        item = ClothingItem(
            user_id=test_user.id,
            type="unknown",
            image_path="test/worker-retired.jpg",
            status=ItemStatus.processing,
            lifecycle="retired",
        )
        db_session.add(item)
        await db_session.commit()

        stub_tags = ClothingTags(
            type="shirt", primary_colors=["blue"], confidence=0.9
        )

        class _StubAI:
            def __init__(self, *args, **kwargs):
                pass

            async def analyze_image(self, path):
                return stub_tags

        monkeypatch.setattr(tagging, "AIService", _StubAI)

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await tagging.tag_item_image({}, str(item.id), __file__)

        assert result["status"] == "success"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.tagging_status == TaggingStatus.tagged
        assert refreshed.status == ItemStatus.archived

    @pytest.mark.asyncio
    async def test_manual_origin_survives_late_worker_completion(
        self, db_session: AsyncSession, test_user, monkeypatch
    ):
        manual_tagged_at = datetime.now(UTC) - timedelta(minutes=5)
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/worker-race.jpg",
            status=ItemStatus.processing,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.manual,
            tagged_at=manual_tagged_at,
        )
        db_session.add(item)
        await db_session.commit()

        stub_tags = ClothingTags(
            type="pants", primary_colors=["black"], confidence=0.7
        )

        class _StubAI:
            def __init__(self, *args, **kwargs):
                pass

            async def analyze_image(self, path):
                return stub_tags

        monkeypatch.setattr(tagging, "AIService", _StubAI)

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            result = await tagging.tag_item_image({}, str(item.id), __file__)

        assert result["status"] == "success"
        refreshed = await _get_item(db_session, item.id)
        assert refreshed.tagging_status == TaggingStatus.tagged
        assert refreshed.tagged_by == TaggedBy.manual
        assert refreshed.tagged_at == manual_tagged_at
        assert refreshed.ai_processed is True
        assert refreshed.status == ItemStatus.ready


class TestMarkItemTaggingSkipped:
    @pytest.mark.asyncio
    async def test_resets_tagging_status_to_pending(self, db_session: AsyncSession, test_user):
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/skip.jpg",
            status=ItemStatus.processing,
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.auto,
        )
        db_session.add(item)
        await db_session.commit()

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await tagging.mark_item_tagging_skipped({}, str(item.id))

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.ready
        assert refreshed.tagging_status == TaggingStatus.pending

    @pytest.mark.asyncio
    async def test_retired_processing_item_skips_to_archived_not_ready(
        self, db_session: AsyncSession, test_user
    ):
        # mark_item_tagging_skipped is a pipeline finisher: it must not
        # resurrect a retired item (spec §10.16 status/lifecycle sync).
        item = ClothingItem(
            user_id=test_user.id,
            type="shirt",
            image_path="test/skip-retired.jpg",
            status=ItemStatus.processing,
            lifecycle="retired",
            tagging_status=TaggingStatus.tagged,
            tagged_by=TaggedBy.auto,
        )
        db_session.add(item)
        await db_session.commit()

        with (
            patch("app.workers.tagging.get_db_session", return_value=db_session),
            patch.object(db_session, "close", new_callable=AsyncMock),
        ):
            await tagging.mark_item_tagging_skipped({}, str(item.id))

        refreshed = await _get_item(db_session, item.id)
        assert refreshed.status == ItemStatus.archived
        assert refreshed.tagging_status == TaggingStatus.pending
