import numpy as np
from PIL import Image, ImageDraw

from app.services.color_calibration import (
    GAIN_MAX,
    GAIN_MIN,
    apply_gains,
    calibrate,
    detect_reference,
    white_balance_gain,
)


def test_detects_a_gray_card_before_a_white_patch():
    img = Image.new("RGB", (800, 600), (30, 90, 160))
    d = ImageDraw.Draw(img)
    d.rectangle((80, 80, 260, 220), fill=(245, 245, 245))    # 白纸
    d.rectangle((500, 300, 700, 460), fill=(128, 128, 128))  # 灰卡
    kind, box = detect_reference(img)
    assert kind == "gray"
    l, t, r, b = box
    assert 500 <= l <= 520 and 300 <= t <= 320
    assert 680 <= r <= 700 and 440 <= b <= 460


def test_falls_back_to_white_paper_when_no_gray_card():
    img = Image.new("RGB", (800, 600), (180, 40, 90))
    ImageDraw.Draw(img).rectangle((100, 100, 300, 260), fill=(250, 250, 250))
    kind, _ = detect_reference(img)
    assert kind == "white"


def test_returns_none_when_no_reference_object():
    assert detect_reference(Image.new("RGB", (800, 600), (180, 40, 90))) is None


def test_ignores_small_noise_regions():
    img = Image.new("RGB", (800, 600), (30, 90, 160))
    d = ImageDraw.Draw(img)
    for i in range(6):
        d.rectangle((10 + i * 30, 10, 25 + i * 30, 25), fill=(200, 200, 200))
    assert detect_reference(img) is None


def test_ignores_gray_band_region_below_min_side():
    # 灰带内（128,128,128 → L*≈0.54）、面积 300×20=6000 已过 MIN_REGION_AREA_RATIO
    # (5760)，但最短边 20 < MIN_REGION_SIDE —— 只有最短边分支能拒掉它。
    img = Image.new("RGB", (800, 600), (30, 90, 160))
    ImageDraw.Draw(img).rectangle((100, 100, 399, 119), fill=(128, 128, 128))
    assert detect_reference(img) is None


def test_ignores_gray_band_region_below_min_area():
    # 灰带内、两维度都 ≥ MIN_REGION_SIDE（45×120），但面积 5400 < 5760 ——
    # 只有面积分支能拒掉它。
    img = Image.new("RGB", (800, 600), (30, 90, 160))
    ImageDraw.Draw(img).rectangle((100, 100, 144, 219), fill=(128, 128, 128))
    assert detect_reference(img) is None


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
