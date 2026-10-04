"""Runtime vocabulary: read the whole vocab; add/rename/disable soft entries.

Every write lands in the JSON *and* in docs/specs/vocabulary.md at the same
position (see app.utils.vocabulary_md), so the two faces never drift and
`compile_vocabulary.py --check` stays green.
"""
from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.utils.auth import get_current_user
from app.utils.garment_vocabulary import VOCABULARY_PATH
from app.utils.vocabulary_md import (
    MD_PATH,
    entry_sort_key,
    ensure_family_section,
    mark_disabled,
    sync_row,
    unmark_disabled,
)

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])

BODY_PART_VALUES = {"dresses", "accessories", "tops", "jewelry", "outerwear", "bottoms", "footwear"}
# Must match scripts/compile_vocabulary.FALLBACK_META — pinned by test so a
# recompile of a runtime-added type keeps its role/wash_interval.
RUNTIME_TYPE_FALLBACK = ("accessory", 3)


class StyleIn(BaseModel):
    value: str = Field(pattern=r"^[a-z0-9-]+$")
    label: str


class ColorValueIn(BaseModel):
    value: str = Field(pattern=r"^[a-z0-9-]+$")
    label: str
    family: str
    hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class TypeIn(BaseModel):
    value: str = Field(pattern=r"^[a-z0-9-]+$")
    label: str
    body_part: str


class PatchIn(BaseModel):
    label: str | None = None
    disabled: bool | None = None


def _load() -> dict:
    return json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    # Same rendering as scripts/compile_vocabulary.main — byte-identical faces.
    VOCABULARY_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _insert_entry(entries: list[dict], entry: dict, kind: str, family: str | None) -> None:
    key = entry_sort_key(kind, entry["value"], entry["label"], family, entry.get("hex"))
    idx = next(
        (
            i
            for i, e in enumerate(entries)
            if entry_sort_key(kind, e["value"], e["label"], family, e.get("hex")) > key
        ),
        len(entries),
    )
    entries.insert(idx, entry)


def _splice_family_block(values: list[dict], family: str, block: list[dict]) -> list[dict]:
    """Replace one family's rows in place — the JSON mirrors the markdown's
    section order, so the block must not migrate to the end. A family with no
    rows yet appends its block at the end, matching a new markdown section."""
    out: list[dict] = []
    done = False
    for c in values:
        if c["family"] != family:
            out.append(c)
        elif not done:
            out.extend(block)
            done = True
    if not done:
        out.extend(block)
    return out


def _md_args(kind: str, entry: dict) -> tuple[str, str | None]:
    if kind == "colors":
        return "colors", entry.get("family")
    if kind == "types":
        return "types", entry.get("body_part")
    return "styles", None


@router.get("")
async def get_vocabulary(current_user: Annotated[object, Depends(get_current_user)]) -> dict:
    return _load()


@router.post("/styles", status_code=201)
async def add_style(
    body: StyleIn, current_user: Annotated[object, Depends(get_current_user)]
) -> dict:
    data = _load()
    if any(s["value"] == body.value for s in data["styles"]):
        raise HTTPException(status_code=409, detail="slug exists")
    entry = {"value": body.value, "label": body.label}
    _insert_entry(data["styles"], entry, "styles", None)
    _save(data)
    sync_row(MD_PATH, "styles", entry)
    return entry


@router.post("/colors/values", status_code=201)
async def add_color_value(
    body: ColorValueIn, current_user: Annotated[object, Depends(get_current_user)]
) -> dict:
    data = _load()
    if any(c["value"] == body.value for c in data["colors"]["values"]):
        raise HTTPException(status_code=409, detail="slug exists")
    if not any(f["value"] == body.family for f in data["colors"]["families"]):
        raise HTTPException(status_code=422, detail="unknown family")
    entry = {
        "value": body.value,
        "label": body.label,
        "family": body.family,
        "hex": body.hex.lower(),
    }
    block = [c for c in data["colors"]["values"] if c["family"] == body.family]
    _insert_entry(block, entry, "colors", body.family)
    data["colors"]["values"] = _splice_family_block(
        data["colors"]["values"], body.family, block
    )
    _save(data)
    sync_row(MD_PATH, "colors", entry, family=body.family)
    return entry


@router.post("/colors/families", status_code=201)
async def add_color_family(
    body: StyleIn, current_user: Annotated[object, Depends(get_current_user)]
) -> dict:
    data = _load()
    if any(f["value"] == body.value for f in data["colors"]["families"]):
        raise HTTPException(status_code=409, detail="slug exists")
    entry = {"value": body.value, "label": body.label}
    data["colors"]["families"].append(entry)
    _save(data)
    ensure_family_section(MD_PATH, body.value, body.label)
    return entry


@router.post("/types", status_code=201)
async def add_type(
    body: TypeIn, current_user: Annotated[object, Depends(get_current_user)]
) -> dict:
    data = _load()
    if body.body_part not in BODY_PART_VALUES:
        raise HTTPException(status_code=422, detail="unknown body_part")
    if any(t["value"] == body.value for t in data["types"]):
        raise HTTPException(status_code=409, detail="slug exists")
    role, wash_interval = RUNTIME_TYPE_FALLBACK
    entry = {
        "value": body.value,
        "label": body.label,
        "body_part": body.body_part,
        "role": role,
        "wash_interval": wash_interval,
    }
    block = [t for t in data["types"] if t["body_part"] == body.body_part]
    _insert_entry(block, entry, "types", body.body_part)
    out: list[dict] = []
    done = False
    for t in data["types"]:
        if t["body_part"] != body.body_part:
            out.append(t)
        elif not done:
            out.extend(block)
            done = True
    if not done:
        out.extend(block)
    data["types"] = out
    _save(data)
    sync_row(MD_PATH, "types", entry, family=body.body_part)
    return entry


@router.patch("/{kind}/{value}")
async def patch_entry(
    kind: Literal["styles", "types", "colors"],
    value: str,
    body: PatchIn,
    current_user: Annotated[object, Depends(get_current_user)],
) -> dict:
    data = _load()
    bucket = (
        data["styles"]
        if kind == "styles"
        else (data["types"] if kind == "types" else data["colors"]["values"])
    )
    entry = next((e for e in bucket if e["value"] == value), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="unknown entry")
    md_kind, family = _md_args(kind, entry)
    if body.label is not None:
        entry["label"] = body.label
        sync_row(MD_PATH, md_kind, entry, family=family)
    if body.disabled is not None:
        if body.disabled:
            entry["disabled"] = True
            mark_disabled(MD_PATH, md_kind, value, family=family)
        else:
            # The key is present only while disabled so recompiles match byte-for-byte.
            entry.pop("disabled", None)
            unmark_disabled(MD_PATH, md_kind, value, family=family)
    _save(data)
    return entry
