"""Stage-two vision rerank for AI-suggested linking (spec §3.2)."""

import base64
import io
import json
import re
from typing import Literal
from uuid import UUID

from PIL import Image

Verdict = Literal["same", "similar", "different"]
_VALID = {"same", "similar", "different"}
_RANK = {"same": 0, "similar": 1, None: 2, "different": 3}


def image_to_b64_jpeg(img: Image.Image, max_side: int = 384) -> str:
    im = img.convert("RGB")
    im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _extract(text: str) -> object:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def parse_verdicts(text: str, n: int) -> list[Verdict | None]:
    data = _extract(text)
    raw = data.get("verdicts") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return [None] * n
    out: list[Verdict | None] = []
    for v in raw[:n]:
        s = v.strip().lower() if isinstance(v, str) else None
        out.append(s if s in _VALID else None)  # type: ignore[arg-type]
    return out + [None] * (n - len(out))


def rank_candidates(
    cands: list[tuple[UUID, float, Verdict | None]], min_out: int = 5, max_out: int = 8
) -> list[tuple[UUID, float, Verdict | None]]:
    """Verdict first (same > similar > unknown > different), cosine second.

    "different" only appears when needed to reach min_out (spec: 5–8 candidates).
    """
    ordered = sorted(cands, key=lambda c: (_RANK[c[2]], -c[1]))
    kept = [c for c in ordered if c[2] != "different"]
    if len(kept) < min_out:
        kept += [c for c in ordered if c[2] == "different"][: min_out - len(kept)]
    return kept[:max_out]
