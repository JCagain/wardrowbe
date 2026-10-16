"""Validate an embedding endpoint for AI-suggested linking before wiring it in.

Usage (inside the backend container):
    python -m scripts.embedding_probe --user-email you@example.com [--limit 40]
        [--instruction "Find the catalogue photo of this garment"]
        [--pair /data/wardrobe/crops/shirt.jpg:<item-uuid> ...]

Pass: augmented self-retrieval recall@5 >= 0.8 and vectors not collapsed (mean
cross-item cosine <= 0.95; a high max alone only prints the offending pair as a
warning, since near-duplicate items are legitimate). These are self-consistency checks on augmented copies of the same item, not real
outfit-photo crop recall: passing is necessary, not sufficient. --pair runs real
crops as a reference (no hard threshold).
Exit codes: 0 PASS, 1 collapsed vectors, 2 endpoint unavailable, 3 WEAK (recall@5 < 0.8,\nnot collapsed), 4 bad input (unknown --user-email, bad --pair path or UUID).
"""

import argparse
import asyncio
import random
import sys
from pathlib import Path
from uuid import UUID

import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session_maker
from app.models.item import ClothingItem, ItemStatus
from app.models.user import User
from app.services.embedding_client import EmbeddingClient, EmbeddingUnavailableError
from app.services.embedding_recall import top_k
from app.services.embedding_store import embedding_input_image, source_fingerprint

GRAY = (128, 128, 128)
COLLAPSE_MEAN = 0.95
NEAR_DUP_MAX = 0.98
RECALL_PASS = 0.8


def augment(img: Image.Image, seed: int) -> Image.Image:
    rng = random.Random(seed)
    im = img.convert("RGB")
    w, h = im.size
    frac = rng.uniform(0.7, 0.9) ** 0.5
    cw, ch = max(1, int(w * frac)), max(1, int(h * frac))
    x0, y0 = rng.randint(0, w - cw), rng.randint(0, h - ch)
    im = im.crop((x0, y0, x0 + cw, y0 + ch))
    im = im.rotate(rng.uniform(-8, 8), expand=True, fillcolor=GRAY)
    im = ImageEnhance.Brightness(im).enhance(rng.uniform(0.85, 1.15))
    canvas = Image.new("RGB", (int(im.width * 1.3), int(im.height * 1.3)), GRAY)
    canvas.paste(im, ((canvas.width - im.width) // 2, (canvas.height - im.height) // 2))
    return canvas


def retrieval_metrics(ranks: list[int | None], ks=(1, 5, 10)) -> dict[str, float]:
    n = len(ranks) or 1
    out = {f"recall@{k}": sum(1 for r in ranks if r is not None and r <= k) / n for k in ks}
    out["mrr"] = sum(1 / r for r in ranks if r) / n
    return out


def distinctness(vectors: list[np.ndarray]) -> dict:
    if len(vectors) < 2:
        return {"max": 0.0, "mean": 0.0, "pair": None}
    m = np.stack([v / np.linalg.norm(v) for v in vectors])
    sims = m @ m.T
    iu = np.triu_indices(len(vectors), k=1)
    vals = sims[iu]
    k = int(vals.argmax())
    return {
        "max": float(vals[k]),
        "mean": float(vals.mean()),
        "pair": (int(iu[0][k]), int(iu[1][k])),
    }


def verdict(d: dict, recall5: float) -> tuple[int, str]:
    """Exit code and label: collapse is judged on the mean, never the max alone."""
    if d["mean"] > COLLAPSE_MEAN:
        return 1, "FAIL"
    return (0, "PASS") if recall5 >= RECALL_PASS else (3, "WEAK")


def _bad_input(msg: str) -> int:
    print(f"error: {msg}")
    return 4


def _parse_pairs(specs: list[str]) -> list[tuple[Path, UUID]] | str:
    out = []
    for spec in specs:
        path, sep, item_id = spec.rpartition(":")
        if not sep or not path:
            return f"--pair {spec!r} must look like PATH:ITEM_UUID"
        try:
            uid = UUID(item_id)
        except ValueError:
            return f"--pair {spec!r}: {item_id!r} is not a valid UUID"
        if not Path(path).is_file():
            return f"--pair {spec!r}: no such file {path}"
        out.append((Path(path), uid))
    return out


async def _run(args) -> int:
    s = get_settings()
    client = EmbeddingClient(
        base_url=args.base_url or s.ai_embedding_base_url,
        model=args.model or s.ai_embedding_model,
        api_key=args.api_key or s.ai_embedding_api_key,
        timeout=s.ai_embedding_timeout,
    )
    if not client.base_url or not client.model:
        print("embedding endpoint not configured (--base-url/--model or AI_EMBEDDING_*)")
        return 2
    pairs = _parse_pairs(args.pair)
    if isinstance(pairs, str):
        return _bad_input(pairs)
    storage = Path(s.storage_path)
    async with async_session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == args.user_email))
        ).scalar_one_or_none()
        if user is None:
            return _bad_input(f"no user with email {args.user_email!r}")
        items = (
            (
                await db.execute(
                    select(ClothingItem)
                    .where(ClothingItem.user_id == user.id, ClothingItem.status == ItemStatus.ready)
                    .order_by(ClothingItem.created_at)
                )
            )
            .scalars()
            .all()
        )
    items = [i for i in items if source_fingerprint(i, storage)][: args.limit]
    if len(items) < 2:
        print(f"need at least 2 ready items with images, found {len(items)}")
        return 2
    try:
        lib_imgs = [embedding_input_image(i, storage) for i in items]
        lib_vecs = await client.embed_images(lib_imgs)
        queries = [augment(img, seed=n) for n, img in enumerate(lib_imgs)]
        q_vecs = await client.embed_images(queries, instruction=args.instruction)
        pair_vecs = []
        for path, item_id in pairs:
            try:
                with Image.open(path) as im:
                    crop = ImageOps.exif_transpose(im).convert("RGB")
            except OSError as e:
                return _bad_input(f"--pair image {path} unreadable: {e}")
            vec = (await client.embed_images([crop], instruction=args.instruction))[0]
            pair_vecs.append((item_id, vec))
    except EmbeddingUnavailableError as e:
        print(f"endpoint unavailable: {e}")
        return 2

    library = [(i.id, list(v)) for i, v in zip(items, lib_vecs, strict=True)]
    ranks = []
    for item, q in zip(items, q_vecs, strict=True):
        ranked = [cid for cid, _ in top_k(q, library, k=len(library))]
        ranks.append(ranked.index(item.id) + 1 if item.id in ranked else None)
    d = distinctness(lib_vecs)
    m = retrieval_metrics(ranks)
    print(
        f"endpoint={client.base_url} model={client.model} "
        f"dim={lib_vecs[0].shape[0]} items={len(items)}"
    )
    print(f"instruction={args.instruction!r}")
    print(f"distinctness max={d['max']:.4f} mean={d['mean']:.4f}")
    print("  ".join(f"{k}={v:.3f}" for k, v in m.items()))
    names = {i.id: (i.name or i.type) for i in items}
    for target, vec in pair_vecs:
        ranked = top_k(vec, library, k=len(library))
        ids = [cid for cid, _ in ranked]
        rank = ids.index(target) + 1 if target in ids else None
        top5 = ", ".join(f"{names.get(cid, cid)}:{score:.3f}" for cid, score in ranked[:5])
        print(f"pair {target}: rank={rank}  top5: {top5}")
    code, label = verdict(d, m["recall@5"])
    if d["max"] > NEAR_DUP_MAX and d["pair"]:
        i, j = d["pair"]
        print(
            f"warning: most similar pair cos={d['max']:.4f}: "
            f"{items[i].id} ({names[items[i].id]}) / {items[j].id} ({names[items[j].id]}) "
            "- near-duplicate items? fine if the mean is normal"
        )
    if code == 1:
        print(
            f"FAIL: vectors collapsed (mean cosine {d['mean']:.4f} > {COLLAPSE_MEAN}) "
            "- check --pooling last and that --mmproj is loaded"
        )
    else:
        print(f"{label}: augmented recall@5={m['recall@5']:.3f} (pass >= {RECALL_PASS})")
    return code


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--user-email", required=True)
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--instruction", default=None)
    p.add_argument("--base-url", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--api-key", default=None)
    p.add_argument("--pair", action="append", default=[])
    sys.exit(asyncio.run(_run(p.parse_args())))


if __name__ == "__main__":
    main()
