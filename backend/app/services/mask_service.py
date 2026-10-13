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


def apply_strokes(mask: Image.Image, strokes: list[dict]) -> Image.Image:
    """把画笔笔画应用到 mask。add 涂白（补抠），subtract 涂黑（擦多余）。

    stroke = {"x": int, "y": int, "radius": int, "mode": "add"|"subtract"}
    x/y/radius 一律是 **全分辨率 mask 像素**。调用方负责把显示坐标换算过来。
    后画的笔画覆盖先画的。
    """
    from PIL import ImageDraw

    out = mask.convert("L").copy()
    draw = ImageDraw.Draw(out)
    for stroke in strokes:
        radius = max(1, int(stroke["radius"]))
        x, y = int(stroke["x"]), int(stroke["y"])
        fill = 255 if stroke["mode"] == "add" else 0
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)
    return out
