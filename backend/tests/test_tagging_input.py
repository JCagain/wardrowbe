import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import ClothingItem, ItemStatus
from app.services.ai_service import AIService, ClothingTags
from app.workers import tagging as tagging_module
from app.workers.tagging import analysis_input, resolve_analysis_path, tag_item_image


class _Item:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _near(a, b, tol=8):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def _cutout(tmp_path):
    rgba = Image.new("RGBA", (40, 40), (200, 0, 0, 0))
    rgba.paste((200, 0, 0, 255), (10, 10, 30, 30))
    work = tmp_path / "w.png"
    rgba.save(work)
    rgba.getchannel("A").save(tmp_path / "w_mask.png")
    return work


def test_uses_the_working_image_when_there_is_no_mask(tmp_path):
    work = tmp_path / "w.png"
    Image.new("RGB", (20, 20), (10, 20, 30)).save(work)
    item = _Item(image_path="w.png", mask_path=None, calibration_original_path=None)
    assert resolve_analysis_path(item, tmp_path) == work


def test_composites_the_matte_on_white_for_color_judgment(tmp_path):
    # fixes #16: with a mask, judge colour on the cut-out over white
    work = _cutout(tmp_path)
    item = _Item(image_path="w.png", mask_path="w_mask.png", calibration_original_path=None)
    resolved = resolve_analysis_path(item, tmp_path)
    try:
        assert resolved != work
        out = Image.open(resolved).convert("RGB")
        assert _near(out.getpixel((20, 20)), (200, 0, 0))  # garment keeps its colour
        assert _near(out.getpixel((0, 0)), (255, 255, 255))  # background goes white
    finally:
        resolved.unlink(missing_ok=True)


def test_composite_never_lands_in_storage_and_is_cleaned_up(tmp_path):
    # Ruling 47
    _cutout(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    item = _Item(image_path="w.png", mask_path="w_mask.png")
    with analysis_input(item, tmp_path) as path:
        assert path.exists()
        assert path.parent != tmp_path
    assert not path.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_analysis_input_cleans_up_when_the_body_raises(tmp_path):
    _cutout(tmp_path)
    item = _Item(image_path="w.png", mask_path="w_mask.png")
    with pytest.raises(RuntimeError):
        with analysis_input(item, tmp_path) as path:
            raise RuntimeError("boom")
    assert not path.exists()


def test_tag_completion_never_resurrects_a_retired_item():
    # Review Focus #5
    from app.models.item import ItemStatus
    from app.utils.item_lifecycle import terminal_status

    assert terminal_status("retired", ItemStatus.ready) == ItemStatus.archived
    assert terminal_status("active", ItemStatus.ready) == ItemStatus.ready
    assert terminal_status("idle", ItemStatus.ready) == ItemStatus.ready


@pytest.mark.asyncio
async def test_worker_analyzes_the_db_row_cutout_not_the_stale_arg(
    db_session: AsyncSession, test_user, tmp_path, monkeypatch
):
    # Ruling 48: enqueued arg is the old .jpg; the row's primary is now the .png cut-out
    settings = tagging_module.get_settings().model_copy(update={"storage_path": str(tmp_path)})
    monkeypatch.setattr(tagging_module, "get_settings", lambda: settings)
    _cutout(tmp_path)
    item = ClothingItem(
        user_id=test_user.id,
        type="unknown",
        image_path="w.png",
        mask_path="w_mask.png",
        status=ItemStatus.processing,
    )
    db_session.add(item)
    await db_session.commit()
    before = sorted(p.name for p in tmp_path.iterdir())

    seen = {}

    async def fake_analyze(self, path):
        seen["path"] = Path(path)
        seen["pixel"] = Image.open(path).convert("RGB").getpixel((0, 0))
        seen["center"] = Image.open(path).convert("RGB").getpixel((20, 20))
        return ClothingTags(type="shirt", primary_colors=["red"], confidence=0.9)

    with (
        patch("app.workers.tagging.get_db_session", return_value=db_session),
        patch.object(db_session, "close", new_callable=AsyncMock),
        patch.object(AIService, "analyze_image", fake_analyze),
    ):
        result = await tag_item_image({"job_try": 1}, str(item.id), str(tmp_path / "stale.jpg"))

    assert result["status"] == "success"
    assert _near(seen["pixel"], (255, 255, 255))
    assert _near(seen["center"], (200, 0, 0))
    assert not seen["path"].exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert Path(tempfile.gettempdir()) == seen["path"].parent
