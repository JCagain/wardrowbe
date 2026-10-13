"""校色检出与白平衡数学（Task R19：白-灰-黑三联条）。

检出钉住 Ruling 19 的结构先验：三卡成条、相对 L 排序与间隔（曝光不变量）。
数学与安全钉（box 含右下、增益夹限、小噪声不当参考）原样保留。
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw
from skimage.color import rgb2lab

from app.services.color_calibration import (
    GAIN_MAX,
    GAIN_MIN,
    apply_gains,
    calibrate,
    detect_reference,
    white_balance_gain,
)

# ---------------------------------------------------------------- 合成场景


def _textured_scene(size=(800, 600), seed=1) -> Image.Image:
    """带噪声纹理的照片背景。

    纹理的局部 L-std 实测 0.05–0.085（0.5×–1.5× 曝光），远高于平坦阈值，
    不会被误当参考卡；纯色背景则会整片平坦、靠面积上限拒掉。
    """
    rng = np.random.default_rng(seed)
    noise = rng.integers(-35, 36, (size[1], size[0], 3), dtype=np.int16)
    arr = np.clip(np.int16((110, 110, 110)) + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def _strip_scene(size=(800, 600), seed=1) -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    """白/灰/黑三卡横排（Ruling 19：成条摆放），返回图与含右下的真值框。"""
    img = _textured_scene(size, seed)
    d = ImageDraw.Draw(img)
    cards = {
        "white": (160, 210, 319, 389),
        "gray": (330, 210, 489, 389),
        "black": (500, 210, 659, 389),
    }
    d.rectangle(cards["white"], fill=(245, 245, 245))
    d.rectangle(cards["gray"], fill=(128, 128, 128))
    d.rectangle(cards["black"], fill=(35, 35, 35))
    return img, cards


def _exposure(img: Image.Image, factor: float) -> Image.Image:
    """整体曝光（显示域乘 factor，两端截断）。"""
    arr = np.clip(np.asarray(img, dtype=np.float64) * factor, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def _L_stats(img: Image.Image, box: tuple[int, int, int, int] | None = None) -> tuple[float, float]:
    """box 含右下（同 detect_reference 契约）；None = 整图。返回 (mean_L, std_L)。"""
    crop = img if box is None else img.crop((box[0], box[1], box[2] + 1, box[3] + 1))
    lab = rgb2lab(np.asarray(crop.convert("RGB"), dtype=np.float64) / 255.0)
    lightness = lab[..., 0] / 100.0
    return float(lightness.mean()), float(lightness.std())


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """含右下框的 IoU。"""
    iw = max(0, min(a[2], b[2]) - max(a[0], b[0]) + 1)
    ih = max(0, min(a[3], b[3]) - max(a[1], b[1]) + 1)
    inter = iw * ih
    area_a = (a[2] - a[0] + 1) * (a[3] - a[1] + 1)
    area_b = (b[2] - b[0] + 1) * (b[3] - b[1] + 1)
    return inter / (area_a + area_b - inter)


# ---------------------------------------------------------------- 三联条检出


def test_strip_hits_the_gray_card_with_all_three_boxes():
    """横排白/灰/黑：命中灰卡，三框齐，沿条方向 L 单调递减。"""
    img, cards = _strip_scene()
    ref = detect_reference(img)
    assert ref is not None
    assert ref.kind == "gray"
    assert _iou(ref.box, cards["gray"]) > 0.9
    # 主参考 = 中间那块（灰卡优先）
    assert ref.box == ref.cards["gray"]
    assert set(ref.cards) == {"white", "gray", "black"}
    for name, key in (("white", "white"), ("gray", "gray"), ("black", "black")):
        assert _iou(ref.cards[key], cards[name]) > 0.9, name
    means = {k: _L_stats(img, ref.cards[k])[0] for k in ("white", "gray", "black")}
    assert means["white"] > means["gray"] > means["black"]


def test_strip_is_found_at_any_orientation():
    """旋转 30° 仍命中灰卡：主轴由三块质心自求，不假定水平。"""
    img, cards = _strip_scene()
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.rectangle(cards["white"], fill=1)
    d.rectangle(cards["gray"], fill=2)
    d.rectangle(cards["black"], fill=3)
    angle = 30.0
    rot = img.rotate(angle, resample=Image.BICUBIC, expand=True)
    rot_mask = np.asarray(mask.rotate(angle, resample=Image.NEAREST, expand=True))
    # 旋转后的真值从掩码取（PIL 旋转约定不影响结论）
    ys, xs = np.where(rot_mask == 2)
    gt_gray = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))

    ref = detect_reference(rot)
    assert ref is not None
    assert ref.kind == "gray"
    assert _iou(ref.box, gt_gray) > 0.5
    assert ref.cards is not None
    means = {k: _L_stats(rot, ref.cards[k])[0] for k in ("white", "gray", "black")}
    assert means["white"] > means["gray"] > means["black"]


def test_detection_survives_half_exposure():
    """整体压暗 0.5×：与 1.0× 命中同一个框（曝光不变量）。

    平坦阈值边界会随局部 std 数值挪 1px（纹理与卡相接处 L 相近像素的泄漏），
    故容 2px 而非逐字节相等；实测 0.5× 与 1.0× 只差 1px、IoU≈0.98。
    """
    img, _ = _strip_scene()
    base = detect_reference(img)
    dark = detect_reference(_exposure(img, 0.5))
    assert base is not None and dark is not None
    assert dark.kind == "gray"
    assert max(abs(a - b) for a, b in zip(dark.box, base.box)) <= 2


def test_detection_survives_one_point_five_exposure():
    """整体提亮 1.5×：与 1.0× 命中同一个框（曝光不变量，容差同 0.5×）。"""
    img, _ = _strip_scene()
    base = detect_reference(img)
    bright = detect_reference(_exposure(img, 1.5))
    assert base is not None and bright is not None
    assert bright.kind == "gray"
    assert max(abs(a - b) for a, b in zip(bright.box, base.box)) <= 2


def test_occluded_card_still_hits():
    """衣服压住灰卡一角：矩形度放宽后仍命中，条仍完整。"""
    img, cards = _strip_scene()
    gray_l, gray_t, _, _ = cards["gray"]
    patch = img.crop((0, 0, 60, 60))  # 有纹理的“衣服”块
    img.paste(patch, (gray_l, gray_t))

    ref = detect_reference(img)
    assert ref is not None
    assert ref.kind == "gray"
    # 压角不改 bbox 极值，只是矩形度下降 → 框仍近似原灰卡
    assert _iou(ref.box, cards["gray"]) > 0.5
    assert ref.cards is not None


def test_misordered_strip_is_not_trusted_as_a_strip():
    """白-黑-灰 不是合法三联条（验序：L 必须单调阶梯）。

    放弃当条找后走单卡兜底：拿真正的灰卡，不把投影中点（黑卡）当灰卡，
    也不编造三框。
    """
    img = _textured_scene()
    d = ImageDraw.Draw(img)
    d.rectangle((160, 210, 319, 389), fill=(245, 245, 245))   # 白
    d.rectangle((330, 210, 489, 389), fill=(35, 35, 35))     # 黑
    gray_card = (500, 210, 659, 389)
    d.rectangle(gray_card, fill=(128, 128, 128))             # 灰（在末端）

    ref = detect_reference(img)
    assert ref is not None
    assert ref.kind == "gray"
    assert ref.cards is None
    assert _iou(ref.box, gray_card) > 0.9


# ---------------------------------------------------------------- 单卡 / 兜底


def test_single_gray_card_hits():
    """只有一块灰卡：命中它。"""
    img = _textured_scene()
    card = (300, 200, 499, 359)
    ImageDraw.Draw(img).rectangle(card, fill=(128, 128, 128))
    ref = detect_reference(img)
    assert ref is not None
    assert ref.kind == "gray"
    assert ref.cards is None  # 不成条 → 不编造另两框
    assert _iou(ref.box, card) > 0.9


def test_single_white_paper_is_typed_white():
    """只有一张白纸：按白纸基准（拉到 255），kind=white。"""
    img = _textured_scene()
    card = (300, 200, 499, 359)
    ImageDraw.Draw(img).rectangle(card, fill=(245, 245, 245))
    ref = detect_reference(img)
    assert ref is not None
    assert ref.kind == "white"
    assert ref.cards is None
    assert _iou(ref.box, card) > 0.9


def test_pure_texture_returns_none():
    """纯纹理噪声、无卡：返回 None = 跳过自动校色（不猜白平衡）。"""
    assert detect_reference(_textured_scene()) is None


def test_saturated_flat_block_is_not_a_reference():
    """扁平饱和彩色块（红袋/蓝文件夹）不得当灰卡（Ruling 24）。

    占整图 6.3%（在 5–20% 区间），扁平、矩形、长宽比正常 —— 只有中性闸门能拒它。
    无中性候选存活 → None = 跳过自动校色，不猜白平衡。
    """
    img = _textured_scene()
    ImageDraw.Draw(img).rectangle((200, 150, 399, 299), fill=(220, 30, 40))  # 色度 ≈ 82
    assert detect_reference(img) is None


def test_chromatic_strip_is_not_trusted():
    """三块彩色卡摆成条：各自都不是中性 → 不得当三联条，也不得把中间那块当灰卡。"""
    img = _textured_scene()
    d = ImageDraw.Draw(img)
    d.rectangle((140, 230, 299, 369), fill=(255, 130, 40))   # L 高、色度 ~70
    d.rectangle((310, 230, 469, 369), fill=(190, 25, 50))    # L 中
    d.rectangle((480, 230, 639, 369), fill=(15, 35, 140))    # L 低
    assert detect_reference(img) is None


def test_gray_card_wins_beside_a_saturated_block():
    """闸门只杀彩块，不误杀卡：旁边有更大的彩块时仍命中中性灰卡。"""
    img = _textured_scene()
    card = (300, 200, 499, 359)
    d = ImageDraw.Draw(img)
    d.rectangle(card, fill=(128, 128, 128))
    d.rectangle((500, 380, 719, 579), fill=(220, 30, 40))  # 更大的彩块
    ref = detect_reference(img)
    assert ref is not None
    assert ref.kind == "gray"
    assert ref.cards is None
    assert _iou(ref.box, card) > 0.9


# ---------------------------------------------------------------- 真图回归

# test.jpg 在项目根，已 gitignore 不入库。容器里跑测时把图 cp 到 /tmp/test.jpg
# （或 /test.jpg）即可命中；文件缺失 → skip 干净。
_TEST_JPG_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "test.jpg",  # 仓库根（宿主机跑法）
    Path("/tmp/test.jpg"),  # docker cp wardrobe-backend 的落点
    Path("/test.jpg"),
)
TEST_JPG = next((p for p in _TEST_JPG_CANDIDATES if p.exists()), _TEST_JPG_CANDIDATES[0])

# 灰卡真值框（含右下）：打开 test.jpg 目视三卡簇（白-菱形/灰/黑扇形排列，
# 簇心约 (2500, 2950)），按 1:1 网格读出灰卡四角：上角 y≈2620、左角 x≈2285
# （与白卡交界）、右角 x≈2845（黑卡上角处）、下缘 y≈3295（压在黑卡下）。
# 与检出框（2326,2647,2810,3264）的 IoU≈0.79。
GT_GRAY_BOX = (2285, 2620, 2845, 3295)


@pytest.mark.skipif(not TEST_JPG.exists(), reason="test.jpg not present (gitignored)")
def test_real_photo_hits_the_gray_card():
    img = Image.open(TEST_JPG).convert("RGB")
    width, height = img.size
    ref = detect_reference(img)
    assert ref is not None

    # 命中框与 GT 的 IoU > 0.5，且不是整图
    assert _iou(ref.box, GT_GRAY_BOX) > 0.5
    box_area = (ref.box[2] - ref.box[0] + 1) * (ref.box[3] - ref.box[1] + 1)
    assert box_area < 0.15 * width * height

    # 框内 L-std 显著低于全图（扁平）。灰卡约 45° 倾斜，轴对齐框的四角含
    # 白卡/黑卡/床单，故量内接中心半幅而非整框；实测 0.020 ≪ 全图 0.216。
    l, t, r, b = ref.box
    center = (
        l + (r - l) // 4,
        t + (b - t) // 4,
        r - (r - l) // 4,
        b - (b - t) // 4,
    )
    _, box_std = _L_stats(img, center)
    _, img_std = _L_stats(img)
    assert box_std < img_std / 5

    if ref.cards is not None:
        # 三框贴边（间距 < 图对角线 2%）且 L 单调
        diag = float(np.hypot(width, height))
        boxes = list(ref.cards.values())
        for a, b in zip(boxes, boxes[1:]):
            dx = max(a[0] - b[2], b[0] - a[2], 0)
            dy = max(a[1] - b[3], b[1] - a[3], 0)
            assert float(np.hypot(dx, dy)) < 0.02 * diag
        means = {k: _L_stats(img, ref.cards[k])[0] for k in ref.cards}
        assert means["white"] > means["gray"] > means["black"]


# ---------------------------------------------------------------- 旧算法的尺寸钉

def test_detects_a_gray_card_before_a_white_patch():
    """灰卡优先（spec §1.2 / fixes #1）：白纸与灰卡都在时用灰卡。"""
    img = Image.new("RGB", (800, 600), (30, 90, 160))
    d = ImageDraw.Draw(img)
    d.rectangle((80, 80, 260, 220), fill=(245, 245, 245))    # 白纸
    d.rectangle((500, 300, 700, 460), fill=(128, 128, 128))  # 灰卡
    ref = detect_reference(img)
    assert ref.kind == "gray"
    l, t, r, b = ref.box
    assert 500 <= l <= 520 and 300 <= t <= 320
    assert 680 <= r <= 700 and 440 <= b <= 460


def test_falls_back_to_white_paper_when_no_gray_card():
    img = Image.new("RGB", (800, 600), (180, 40, 90))
    ImageDraw.Draw(img).rectangle((100, 100, 300, 260), fill=(250, 250, 250))
    ref = detect_reference(img)
    assert ref.kind == "white"


def test_returns_none_when_no_reference_object():
    assert detect_reference(Image.new("RGB", (800, 600), (180, 40, 90))) is None


def test_ignores_small_noise_regions():
    # 16×16 噪声斑块：最短边 < MIN_REGION_SIDE，不得当参考卡
    img = Image.new("RGB", (800, 600), (30, 90, 160))
    d = ImageDraw.Draw(img)
    for i in range(6):
        d.rectangle((10 + i * 30, 10, 25 + i * 30, 25), fill=(200, 200, 200))
    assert detect_reference(img) is None


def test_ignores_gray_band_region_below_min_side():
    # 灰带内（128,128,128 → L≈0.54）的 300×20 细条：最短边 20 < MIN_REGION_SIDE
    img = Image.new("RGB", (800, 600), (30, 90, 160))
    ImageDraw.Draw(img).rectangle((100, 100, 399, 119), fill=(128, 128, 128))
    assert detect_reference(img) is None


def test_ignores_gray_band_region_below_min_area():
    """面积下限：整图 0.05%（Task R19，旧 1.2% 阈值已作废）。

    3200×2400 上画 70×70 灰块：平坦掩码被窗口腐蚀到约 48×48 = 2304px
    = 整图 0.03%，低于 0.05%（3840px）；其最短边 48 ≥ MIN_REGION_SIDE，
    只有面积分支能拒掉它。
    """
    img = Image.new("RGB", (3200, 2400), (30, 90, 160))
    ImageDraw.Draw(img).rectangle((300, 300, 369, 369), fill=(128, 128, 128))
    assert detect_reference(img) is None


# ---------------------------------------------------------------- 白平衡数学

def test_gray_baseline_equalizes_channels():
    mean = np.array([200.0, 100.0, 50.0])
    corrected = mean * white_balance_gain(mean, "gray")
    assert np.allclose(corrected, corrected[0], atol=1e-6)


def test_white_baseline_drives_channels_to_white():
    mean = np.array([180.0, 190.0, 170.0])
    assert np.allclose(mean * white_balance_gain(mean, "white"), 255.0, atol=1e-6)


def test_gain_is_clamped_for_a_near_black_reference():
    # fixes #7：框选在极暗区域，增益不得炸到无穷
    gains = white_balance_gain(np.array([1.0, 1.0, 1.0]), "white")
    assert gains.max() <= GAIN_MAX and gains.min() >= GAIN_MIN


def test_gain_lower_bound_clamps_an_out_of_range_mean():
    # 合成越界均值（uint8 派生的均值到不了这里，是防御性下界）：255/2000 = 0.1275 < GAIN_MIN
    gains = white_balance_gain(np.array([2000.0, 2000.0, 2000.0]), "white")
    assert gains.min() == GAIN_MIN
    assert gains.min() >= GAIN_MIN


def test_near_white_reference_stays_untouched():
    # 过曝附近的参考区：增益应贴近 1（不被夹到边界）
    gains = white_balance_gain(np.array([254.0, 255.0, 253.0]), "gray")
    assert np.allclose(gains, 1.0, atol=0.01)


def test_apply_gains_never_overflows_a_channel():
    out = apply_gains(Image.new("RGB", (8, 8), (250, 10, 10)), np.array([2.0, 2.0, 2.0]))
    arr = np.asarray(out)
    assert arr.max() == 255 and arr.min() >= 0


def test_calibrate_uses_the_box_not_the_whole_image():
    img = Image.new("RGB", (100, 100), (30, 30, 200))
    # 参考区不均匀、不中性：内部偏暖，含右下的最后一行/一列偏冷 ——
    # 均匀中性色块会让「漏 +1」和「no-op」都测不出来。
    for x in range(10, 40):
        for y in range(10, 40):
            img.putpixel((x, y), (200, 100, 50))
    for x in range(10, 40):
        img.putpixel((x, 39), (50, 150, 100))
    for y in range(10, 39):
        img.putpixel((39, y), (50, 150, 100))

    box = (10, 10, 39, 39)
    region = np.asarray(img, dtype=np.float64)[10:40, 10:40]  # 含右下
    mean = region.reshape(-1, 3).mean(axis=0)
    gains = white_balance_gain(mean, "gray")
    out = np.asarray(calibrate(img, box, "gray"), dtype=np.float64)[10:40, 10:40]

    # no-op 会红：输出通道被拉平，且不同于输入的通道均值
    assert np.allclose(out[..., 0].mean(), out[..., 2].mean(), atol=1.0)
    assert not np.allclose(out.mean(axis=(0, 1)), mean, atol=1.0)
    # 漏 +1 会红：输出须等于按「含右下整块」均值算出的预期
    assert np.allclose(out, np.clip(region * gains, 0, 255), atol=1.5)
