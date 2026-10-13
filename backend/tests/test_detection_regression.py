"""真实照片回归钉：衣服旁摆白/18% 灰/黑三卡（根目录 test.jpg 缩到 1200px）。

TRUTH_GRAY 是 2026-10-13 用户看图认可的检出结果在 1200px 下的框（全分辨率
5712×4284 下为 (2326,2647,2810,3264)）。阈值常量拿这张图校准；改常量把它弄丢
会在这里变红，而不是等下次实拍才发现。
"""
from pathlib import Path

import numpy as np
from PIL import Image

from app.services.color_calibration import calibrate, detect_reference

FIXTURE = Path(__file__).parent / "fixtures" / "reference_strip_1200.jpg"
TRUTH_GRAY = (489, 556, 589, 683)  # 含右下


def _iou(a, b) -> float:
    l, t = max(a[0], b[0]), max(a[1], b[1])
    r, bt = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, r - l + 1) * max(0, bt - t + 1)
    area = lambda x: (x[2] - x[0] + 1) * (x[3] - x[1] + 1)  # noqa: E731
    return inter / (area(a) + area(b) - inter)


def _mean(img: Image.Image, box) -> np.ndarray:
    l, t, r, b = box
    return np.asarray(img.crop((l, t, r + 1, b + 1)), dtype=np.float64).reshape(-1, 3).mean(axis=0)


def test_real_photo_detects_the_white_gray_black_strip():
    img = Image.open(FIXTURE).convert("RGB")
    found = detect_reference(img)

    assert found is not None, "the strip in the real photo was not detected"
    assert found.cards is not None, "fell back to a single card instead of the strip"
    assert found.kind == "gray"
    assert _iou(found.box, TRUTH_GRAY) >= 0.8, f"gray card box drifted: {found.box}"
    lum = {k: _mean(img, v).mean() for k, v in found.cards.items()}
    assert lum["white"] > lum["gray"] > lum["black"]


def test_real_photo_calibration_neutralises_the_gray_card():
    img = Image.open(FIXTURE).convert("RGB")
    found = detect_reference(img)
    before = _mean(img, found.box)
    # sanity：这张图本身有色偏（绿偏 ~+10），否则下面的断言空转
    assert before.max() - before.min() >= 8

    after = _mean(calibrate(img, found.box, "gray"), found.box)
    assert after.max() - after.min() <= 1.5, f"gray card still has a cast: {after}"
