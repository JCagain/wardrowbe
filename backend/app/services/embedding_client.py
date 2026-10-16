"""Image embeddings from a llama.cpp `--embedding --mmproj` server (spec §3.2, fixes #29/#56).

Request shape: `POST {base}/embeddings` with each `input` element a llama.cpp
multimodal prompt `{"prompt_string": ..., "multimodal_data": [base64]}`. The
server rejects OpenAI-style `content` arrays on this endpoint. The prompt string
must carry the server's media marker, which is randomized per server and read
from `GET {root}/props` (`media_marker`); older servers use `<__media__>`.

The prompt is wrapped in the Qwen3-VL-Embedding chat template (instruction as
the system turn, default "Represent the user's input.") ending in
`<|endoftext|>`, whose hidden state `--pooling last` returns. Vectors come back
L2-normalized so cosine similarity is a dot product.
"""

import base64
import io
from collections.abc import Sequence

import httpx
import numpy as np
from PIL import Image

from app.config import get_settings


DEFAULT_MEDIA_MARKER = "<__media__>"
DEFAULT_INSTRUCTION = "Represent the user's input."


def build_prompt(marker: str, instruction: str | None = None) -> str:
    system = instruction or DEFAULT_INSTRUCTION
    return (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{marker}<|im_end|>\n"
        "<|im_start|>assistant\n<|endoftext|>"
    )


class EmbeddingUnavailableError(RuntimeError):
    """Endpoint unreachable, misconfigured, or returned something unusable."""


def image_to_data_uri(img: Image.Image, max_side: int = 512) -> str:
    im = img.convert("RGB")
    im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class EmbeddingClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 120,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._transport = transport

    @classmethod
    def from_settings(cls) -> "EmbeddingClient | None":
        s = get_settings()
        if not s.embedding_configured:
            return None
        return cls(
            base_url=s.ai_embedding_base_url.strip(),
            model=s.ai_embedding_model.strip(),
            api_key=s.ai_embedding_api_key or None,
            timeout=s.ai_embedding_timeout,
        )

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def ping(self, timeout: float = 3.0) -> bool:
        """Cheap reachability check (GET {base}/models). Never raises."""
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
            return resp.status_code == 200
        except (httpx.HTTPError, httpx.InvalidURL, httpx.UnsupportedProtocol):
            return False

    async def _media_marker(self, client: httpx.AsyncClient) -> str:
        root = self.base_url.removesuffix("/v1")
        try:
            resp = await client.get(f"{root}/props", headers=self._headers())
            marker = resp.json().get("media_marker") if resp.status_code == 200 else None
        except (httpx.HTTPError, httpx.InvalidURL, httpx.UnsupportedProtocol, ValueError, AttributeError):
            marker = None
        return marker if isinstance(marker, str) and marker else DEFAULT_MEDIA_MARKER

    async def embed_images(
        self,
        images: Sequence[Image.Image],
        instruction: str | None = None,
        batch_size: int = 8,
    ) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        dim: int | None = None
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            prompt = build_prompt(await self._media_marker(client), instruction)
            for start in range(0, len(images), batch_size):
                batch = images[start : start + batch_size]
                inputs = [
                    {
                        "prompt_string": prompt,
                        "multimodal_data": [image_to_data_uri(img).split(",", 1)[1]],
                    }
                    for img in batch
                ]
                try:
                    resp = await client.post(
                        f"{self.base_url}/embeddings",
                        headers=self._headers(),
                        json={"model": self.model, "input": inputs, "encoding_format": "float"},
                    )
                    resp.raise_for_status()
                    payload = resp.json()
                except (
                    httpx.HTTPError,
                    httpx.InvalidURL,
                    httpx.UnsupportedProtocol,
                    ValueError,
                ) as e:
                    raise EmbeddingUnavailableError(f"embedding request failed: {e}") from e
                vectors = self._parse(payload, len(batch))
                for v in vectors:
                    if dim is None:
                        dim = v.shape[0]
                    elif v.shape[0] != dim:
                        raise EmbeddingUnavailableError("embedding dimension changed mid-run")
                out.extend(vectors)
        return out

    @staticmethod
    def _parse(payload: object, expected: int) -> list[np.ndarray]:
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise EmbeddingUnavailableError(f"unexpected embedding response: {str(payload)[:200]}")
        data = payload["data"]
        if len(data) != expected:
            raise EmbeddingUnavailableError(f"expected {expected} embeddings, got {len(data)}")
        try:
            ordered = sorted(data, key=lambda d: d["index"])
            arrays = [np.asarray(d["embedding"], dtype=np.float32) for d in ordered]
        except (KeyError, TypeError, ValueError) as e:
            raise EmbeddingUnavailableError(f"malformed embedding entry: {e}") from e
        dims = {a.shape for a in arrays}
        if len(dims) != 1 or arrays[0].ndim != 1 or arrays[0].shape[0] == 0:
            raise EmbeddingUnavailableError("embeddings have inconsistent shapes")
        out = []
        for a in arrays:
            norm = float(np.linalg.norm(a))
            if not np.isfinite(norm) or norm == 0.0:
                raise EmbeddingUnavailableError("zero or non-finite embedding")
            out.append(a / norm)
        return out
