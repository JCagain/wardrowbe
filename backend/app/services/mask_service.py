"""mask 持久化与合成（fixes #10-#13）。mask 是 L 模式 PNG 旁挂文件。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image


def save_mask(mask: Image.Image, path: Path) -> None:
    if mask.mode != "L":
        mask = mask.convert("L")
    mask.save(path, format="PNG", optimize=True)


def load_mask(path: Path) -> Image.Image:
    return Image.open(path).convert("L")


def composite_on_white(rgba: Image.Image) -> Image.Image:
    """抠图结果合成白底，只用于打标判色与展示，**不落盘**（fixes #9）。"""
    base = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(base, rgba.convert("RGBA")).convert("RGB")
