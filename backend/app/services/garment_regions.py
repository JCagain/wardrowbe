"""D7: parse and clamp garment boxes on outfit photos (spec §3.2, Ruling 84/85).

Boxes are stored in full-resolution image pixels with inclusive right/bottom,
the same contract as the calibration reference box.
"""

import json
import math
import re

from app.utils import garment_vocabulary

MAX_REGIONS = 12
MIN_SIDE_PX = 8

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _parts() -> set[str]:
    return {p["value"] for p in garment_vocabulary.BODY_PARTS}


def _extract(text: str) -> object:
    match = _JSON_OBJECT.search(text or "")
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _finish(part: str, l: int, t: int, r: int, b: int, width: int, height: int, source: str):
    l, r = sorted((l, r))
    t, b = sorted((t, b))
    l, r = max(0, min(l, width - 1)), max(0, min(r, width - 1))
    t, b = max(0, min(t, height - 1)), max(0, min(b, height - 1))
    if r - l + 1 < MIN_SIDE_PX or b - t + 1 < MIN_SIDE_PX:
        return None
    return {"body_part": part, "box": {"l": l, "t": t, "r": r, "b": b}, "source": source}


def is_parseable(text: str) -> bool:
    """True when the model output is a JSON object whose `regions` is a list (possibly empty)."""
    data = _extract(text)
    return isinstance(data, dict) and isinstance(data.get("regions"), list)


def parse_garment_regions(text: str, width: int, height: int) -> list[dict]:
    data = _extract(text)
    raw = data.get("regions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    parts = _parts()
    out: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict) or entry.get("body_part") not in parts:
            continue
        box = entry.get("box")
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, int | float) for v in box)):
            continue
        x1, y1, x2, y2 = (max(0.0, min(1000.0, float(v))) for v in box)
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        region = _finish(
            entry["body_part"],
            math.floor(x1 * width / 1000),
            math.floor(y1 * height / 1000),
            math.ceil(x2 * width / 1000) - 1,
            math.ceil(y2 * height / 1000) - 1,
            width,
            height,
            "auto",
        )
        if region:
            out.append(region)
        if len(out) == MAX_REGIONS:
            break
    return out


def clamp_regions(regions: list[dict], width: int, height: int) -> list[dict]:
    out = []
    for r in regions[:MAX_REGIONS]:
        b = r["box"]
        region = _finish(
            r["body_part"], int(b["l"]), int(b["t"]), int(b["r"]), int(b["b"]),
            width, height, r.get("source", "manual"),
        )
        if region:
            out.append(region)
    return out
