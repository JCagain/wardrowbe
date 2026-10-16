import base64
import io
import json

import httpx
import numpy as np
import pytest
from PIL import Image

from app.services.embedding_client import (
    EmbeddingClient,
    EmbeddingUnavailableError,
    image_to_data_uri,
)


def _img(color=(200, 30, 30), size=(900, 600)):
    return Image.new("RGB", size, color)


def _client(handler):
    return EmbeddingClient(
        base_url="http://emb.test/v1", model="m", api_key="k",
        transport=httpx.MockTransport(handler),
    )


def test_data_uri_is_downscaled_jpeg():
    uri = image_to_data_uri(_img(size=(2000, 1000)), max_side=512)
    assert uri.startswith("data:image/jpeg;base64,")
    raw = base64.b64decode(uri.split(",", 1)[1])
    with Image.open(io.BytesIO(raw)) as im:
        assert max(im.size) == 512


@pytest.mark.asyncio
async def test_sends_content_array_and_normalizes():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        body = json.loads(request.content)
        seen["body"] = body
        data = [{"index": i, "embedding": [3.0, 4.0]} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data, "model": "m"})

    vecs = await _client(handler).embed_images([_img(), _img((0, 0, 255))], instruction="find it")
    assert seen["url"] == "http://emb.test/v1/embeddings"
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "m"
    parts = seen["body"]["input"][0]["content"]
    assert parts[0]["type"] == "text" and parts[0]["text"] == "find it"
    assert parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert len(vecs) == 2
    np.testing.assert_allclose(vecs[0], [0.6, 0.8], rtol=1e-6)
    assert vecs[0].dtype == np.float32


@pytest.mark.asyncio
async def test_no_instruction_sends_image_only():
    def handler(request):
        parts = json.loads(request.content)["input"][0]["content"]
        assert [p["type"] for p in parts] == ["image_url"]
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]})

    await _client(handler).embed_images([_img()])


@pytest.mark.asyncio
async def test_batches_and_keeps_order_by_index():
    calls = []

    def handler(request):
        n = len(json.loads(request.content)["input"])
        calls.append(n)
        # reversed index order in the response must not reorder results
        base = sum(calls[:-1])
        data = [{"index": i, "embedding": [float(base + i + 1), 0.0, 1.0]} for i in reversed(range(n))]
        return httpx.Response(200, json={"data": data})

    vecs = await _client(handler).embed_images([_img()] * 5, batch_size=2)
    assert calls == [2, 2, 1]
    firsts = [v[0] / v[2] for v in vecs]  # undo normalization ratio
    assert firsts == pytest.approx([1, 2, 3, 4, 5])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"),
        httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]}),  # count mismatch
        httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [1.0, 0.0]}]}),  # dim mismatch
        httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0, 0.0]}, {"index": 1, "embedding": [1.0, 0.0]}]}),  # zero vector
        httpx.Response(200, json={"error": {"message": "no mmproj"}}),
    ],
)
async def test_bad_responses_raise_unavailable(response):
    with pytest.raises(EmbeddingUnavailableError):
        await _client(lambda r: response).embed_images([_img(), _img()])


@pytest.mark.asyncio
async def test_connection_error_raises_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(EmbeddingUnavailableError):
        await _client(handler).embed_images([_img()])


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [httpx.InvalidURL("bad url"), httpx.UnsupportedProtocol("no scheme")])
async def test_bad_url_errors_raise_unavailable(exc):
    def handler(request):
        raise exc

    with pytest.raises(EmbeddingUnavailableError):
        await _client(handler).embed_images([_img()])


def test_from_settings_none_when_unconfigured(monkeypatch):
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "ai_embedding_base_url", "")
    monkeypatch.setattr(s, "ai_embedding_model", "m")
    assert EmbeddingClient.from_settings() is None
    monkeypatch.setattr(s, "ai_embedding_base_url", "http://x/v1/")
    c = EmbeddingClient.from_settings()
    assert c is not None and c.model == "m"
