"""校色（spec §1.2 / fixes #1-#7）：参考物检出与白平衡数学。

纯函数、无 I/O、不读词表。检出用 scikit-image —— **不引入 OpenCV**。
"""
from __future__ import annotations

import numpy as np
from PIL import Image

# 参考物是低色度（近中性）的大块区域：灰卡居中等亮度，白纸居高亮度。
CHROMA_MAX = 12.0
LIGHTNESS_BANDS = {"gray": (0.28, 0.72), "white": (0.80, 1.01)}
# 小块当噪声丢掉（fixes #3）：不足整图 1.2%，或最短边不到 40px。
MIN_REGION_AREA_RATIO = 0.012
MIN_REGION_SIDE = 40

_ORDER = ("gray", "white")  # 灰卡优先（fixes #1）


def detect_reference(image: Image.Image) -> tuple[str, tuple[int, int, int, int]] | None:
    """找参考物区域。灰卡优先，找不到再找白纸，都没有返回 None。

    返回的 box 是含右下的像素框，可直接喂 `Image.crop`。
    """
    from skimage.color import rgb2lab
    from skimage.measure import label, regionprops

    # rgb2lab 只对 uint8 自动除以 255；float 输入必须自己归一到 [0,1]。
    lab = rgb2lab(np.asarray(image.convert("RGB"), dtype=np.float64) / 255.0)
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    lightness = lab[..., 0] / 100.0

    height, width = lightness.shape
    min_area = max(int(height * width * MIN_REGION_AREA_RATIO), MIN_REGION_SIDE**2)

    for kind in _ORDER:
        lo, hi = LIGHTNESS_BANDS[kind]
        mask = (chroma < CHROMA_MAX) & (lightness >= lo) & (lightness < hi)
        if not mask.any():
            continue

        best = None
        for region in regionprops(label(mask)):
            top, left, bottom, right = region.bbox  # skimage 右下开区间
            if region.area < min_area:
                continue
            if min(bottom - top, right - left) < MIN_REGION_SIDE:
                continue
            if best is None or region.area > best.area:
                best = region

        if best is not None:
            top, left, bottom, right = best.bbox
            return kind, (left, top, right - 1, bottom - 1)

    return None


# 增益有界（fixes #7）：参考区极暗时 target/mean 趋于无穷，极亮时趋于 0。
# 界外的增益会把整图冲成纯白或压成纯黑。
GAIN_MIN = 0.25
GAIN_MAX = 4.0


def white_balance_gain(mean_rgb: np.ndarray, baseline: str) -> np.ndarray:
    """从参考区平均色算 RGB 增益。

    baseline="gray"：中性灰基准，三通道拉平到均值。
    baseline="white"：纯白基准，拉到 255。
    """
    mean = np.asarray(mean_rgb, dtype=np.float64)
    if baseline == "gray":
        target = float(mean.mean())
    elif baseline == "white":
        target = 255.0
    else:
        raise ValueError(f"unknown baseline: {baseline!r}")
    return np.clip(target / np.maximum(mean, 1.0), GAIN_MIN, GAIN_MAX)


def apply_gains(image: Image.Image, gains: np.ndarray) -> Image.Image:
    arr = np.asarray(image, dtype=np.float64) * np.asarray(gains, dtype=np.float64)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def calibrate(
    image: Image.Image,
    box: tuple[int, int, int, int],
    baseline: str,
) -> Image.Image:
    """以框内像素为基准做白平衡，应用到整图。box=(l,t,r,b) 含右下。"""
    rgb = image.convert("RGB")
    l, t, r, b = box
    # box 是含右下的（detect_reference 契约）；PIL crop 右/下开区间，要 +1
    pixels = np.asarray(rgb.crop((l, t, r + 1, b + 1)), dtype=np.float64).reshape(-1, 3)
    return apply_gains(rgb, white_balance_gain(pixels.mean(axis=0), baseline))
