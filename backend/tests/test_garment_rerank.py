from uuid import uuid4

import pytest
from PIL import Image

from app.services.ai_service import AIService
from app.services.garment_rerank import image_to_b64_jpeg, parse_verdicts, rank_candidates


def test_parse_verdicts_in_order():
    assert parse_verdicts('{"verdicts": ["same", "different", "similar"]}', 3) == ["same", "different", "similar"]


def test_parse_verdicts_tolerates_fences_case_and_short_lists():
    text = 'ok\n```json\n{"verdicts": ["SAME", "maybe"]}\n```'
    assert parse_verdicts(text, 3) == ["same", None, None]


@pytest.mark.parametrize("text", ["sorry", '{"verdicts": "same"}', "[1,2]", ""])
def test_parse_verdicts_garbage_is_all_none(text):
    assert parse_verdicts(text, 2) == [None, None]


def test_parse_verdicts_truncates_long_lists():
    assert parse_verdicts('{"verdicts": ["same","same","same"]}', 2) == ["same", "same"]


def _c(cos, v):
    return (uuid4(), cos, v)


def test_rank_orders_by_verdict_then_cosine():
    a, b, c, d = _c(0.9, "different"), _c(0.5, "same"), _c(0.8, "similar"), _c(0.7, None)
    out = rank_candidates([a, b, c, d], min_out=1, max_out=8)
    assert out == [b, c, d]  # "different" dropped when enough others


def test_rank_pads_with_different_to_reach_min():
    cands = [_c(0.9 - i / 100, "different") for i in range(6)] + [_c(0.1, "same")]
    out = rank_candidates(cands, min_out=5, max_out=8)
    assert len(out) == 5 and out[0][2] == "same"
    assert [x[1] for x in out[1:]] == sorted([x[1] for x in out[1:]], reverse=True)


def test_rank_caps_at_max():
    out = rank_candidates([_c(1 - i / 100, "same") for i in range(12)], min_out=5, max_out=8)
    assert len(out) == 8


def test_rank_without_rerank_is_cosine_order():
    cands = [_c(0.2, None), _c(0.9, None), _c(0.5, None)]
    assert [x[1] for x in rank_candidates(cands)] == [0.9, 0.5, 0.2]


def test_image_to_b64_jpeg_downscales():
    import base64
    import io

    b64 = image_to_b64_jpeg(Image.new("RGB", (1000, 500)), max_side=384)
    with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
        assert im.format == "JPEG" and max(im.size) == 384


@pytest.mark.asyncio
async def test_rerank_call_sends_query_then_candidates(monkeypatch):
    seen = {}

    async def fake_call(self, messages, task_name, **kw):
        seen["messages"], seen["task"] = messages, task_name
        return '{"verdicts": ["same"]}', None, None

    monkeypatch.setattr(AIService, "_call_with_fallback", fake_call)
    out = await AIService(endpoints=[{"name": "x", "url": "http://x/v1", "vision_model": "v",
                                      "text_model": "t", "enabled": True}]).rerank_garment_candidates("Q", ["C1", "C2"])
    assert out == '{"verdicts": ["same"]}'
    assert seen["task"] == "garment_rerank"
    user = seen["messages"][1]["content"]
    urls = [p["image_url"]["url"] for p in user if p["type"] == "image_url"]
    assert urls == ["data:image/jpeg;base64,Q", "data:image/jpeg;base64,C1", "data:image/jpeg;base64,C2"]
    texts = " ".join(p["text"] for p in user if p["type"] == "text")
    assert "2" in texts  # tells the model how many candidates there are
