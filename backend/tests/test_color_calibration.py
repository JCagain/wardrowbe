from PIL import Image, ImageDraw

from app.services.color_calibration import detect_reference


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
