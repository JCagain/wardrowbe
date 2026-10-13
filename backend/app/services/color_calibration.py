"""校色（spec §1.2 / fixes #1-#7）：参考物检出与白平衡数学。

纯函数、无 I/O、不读词表。检出用 scikit-image/scipy —— **不引入 OpenCV**。

检出（Task R19 / Ruling 19）不看绝对亮度带，看**白-灰-黑三卡成条**的结构先验：
相对 L 排序 + 显著间隔是曝光不变量，背景不可能同时满足「三块扁平矩形 +
单调 L 阶梯」。绝对 L 只在兜底（单卡）时用来定 kind。
"""
from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
from PIL import Image

# ---- 平坦掩码（Task R19，拿 test.jpg 校准；勿散落魔数）--------------------
# 局部 L 标准差窗口随图幅缩放：0.72% 长边 ≈ test.jpg 5712px 上的 41px。
FLAT_WINDOW_FRAC = 0.0072
FLAT_WINDOW_MIN = 7
FLAT_WINDOW_MAX = 55
# 平坦阈值：test.jpg 三卡局部 L-std ≈ 0.010–0.014，床单/衣物 ≥ 0.013–0.020
FLAT_STD_MAX = 0.014

# ---- 候选过滤 ------------------------------------------------------------
# 面积在整图 0.05%–30%（下限拒噪声斑块，上限拒背景/整面墙）
MIN_AREA_RATIO = 0.0005
MAX_AREA_RATIO = 0.30
# 旧安全钉保留：噪声斑块不得当参考（最短边）
MIN_REGION_SIDE = 40
# 长宽比不极端：0.25–4（倒数同界，长短边之比 ≤ 4）
ASPECT_MAX = 4.0
# 矩形度：凸包最小外接矩形填充率 > 0.6 —— 旋转不变，容得下约 45° 倾斜。
# （轴对齐 bbox 填充率对 45° 方块恰好 0.5，与「容得下倾斜」自相矛盾，故用最小外接矩形。）
MINRECT_FILL_MIN = 0.6

# ---- 找条（Ruling 19）----------------------------------------------------
# 贴边：bbox 间距 < 图对角线 2%（重叠算 0）
STRIP_GAP_FRAC = 0.02
# 尺寸相近：面积比在 0.5–2
STRIP_AREA_RATIO_LO = 0.5
STRIP_AREA_RATIO_HI = 2.0
# 相邻 L 间隔 > 8% 的整图 L 极差（p98-p2，稳健极差）
L_GAP_FRAC = 0.08
# 复杂度上限（自检 #6）：只取面积最大的若干个中性候选找条。实拍 test.jpg 全部
# 候选只有 18 个；杂乱背景（瓷砖/格子布）可到数百，C(n,3) 会把检出拖到分钟级。
# 超限时卡若不在前列，退回单卡兜底——宁可少一次三联，不可卡住线程。
STRIP_MAX_CANDIDATES = 30

# ---- 兜底（spec §1.2：灰卡优先、白纸 fallback、都不像 → None 不猜）--------
GRAY_L_RANGE = (0.25, 0.65)  # 中亮度带 → 灰卡
SINGLE_WHITE_L = 0.65  # 单块 ≥ 该亮度 → 白纸基准

# ---- 中性闸门（Ruling 24，拿 test.jpg 校准）-------------------------------
# 参考卡（白/灰/黑）是中性反射体，均值色度贴 0（test.jpg 实测 10.5/5.7/3.6）；
# 饱和彩块是 40–115（红 82 / 蓝 44 / 品红 115）。阈值**优先相对**——对照全图
# 色度分位，躲开整体色偏（同一张灰卡暖光下色度能到 47、冷光 11）——再夹进绝对
# 下限/上限：下限挡「整图极中性」误杀淡色偏的卡，上限挡「整图都艳」把彩块放进来。
# test.jpg 实测：全图色度中位数 12.57 → 1.6×=20.1，白卡 10.5 过、床单块 15–17 贴边。
NEUTRAL_CHROMA_FLOOR = 16.0
NEUTRAL_CHROMA_REL = 1.6  # × 全图色度中位数
NEUTRAL_CHROMA_ABS_MAX = 80.0  # 饱和彩块永远进不来；色偏下的卡（≤60）仍放行

Box = tuple[int, int, int, int]


class ReferenceDetection(NamedTuple):
    """`detect_reference` 的结果：主参考 (kind, box) + 三联时的各卡框。

    kind/box 语义与旧契约一致（box 含右下）；cards 只在三联检出时给全，
    否则 None —— 不为单卡编造另两框。
    """

    kind: str  # "gray" | "white" —— 白平衡基准类型
    box: Box  # 主参考框，含右下
    cards: dict[str, Box] | None  # {"white": box, "gray": box, "black": box}


class _Candidate(NamedTuple):
    box: Box
    area: int
    mean_L: float
    std_L: float
    mean_chroma: float


def _neutral_chroma_max(chroma: np.ndarray) -> float:
    """中性闸门阈值：相对全图色度中位数，夹在绝对下限/上限之间。"""
    p50 = float(np.percentile(chroma, 50))
    return min(NEUTRAL_CHROMA_ABS_MAX, max(NEUTRAL_CHROMA_FLOOR, NEUTRAL_CHROMA_REL * p50))


def _local_std(lightness: np.ndarray, w: int) -> np.ndarray:
    """局部 L 标准差（均匀窗）。色度是坏筛子，平坦度才是卡的特征。"""
    from scipy.ndimage import uniform_filter

    mean = uniform_filter(lightness, w)
    mean_sq = uniform_filter(lightness * lightness, w)
    return np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))


def _minrect_fill(points: np.ndarray, area: int) -> float:
    """凸包最小外接矩形填充率（旋转不变的矩形度）。

    skimage 的 orientation 惯性张量对方块退化（各向同性）不可用；
    对凸包顶点做旋转卡壳取最小面积外接矩形。
    """
    from scipy.spatial import ConvexHull

    if len(points) < 3:
        return 0.0
    hull = ConvexHull(points)
    hp = points[hull.vertices].astype(np.float64)
    best = math.inf
    for i in range(len(hp)):
        edge = hp[(i + 1) % len(hp)] - hp[i]
        length = float(np.hypot(edge[0], edge[1]))
        if length == 0.0:
            continue
        u = edge / length
        v = np.array([-u[1], u[0]])
        pu = hp @ u
        pv = hp @ v
        rect = float(pu.max() - pu.min()) * float(pv.max() - pv.min())
        if rect > 0.0:
            best = min(best, rect)
    if not math.isfinite(best):
        return 0.0
    return float(min(1.0, area / best))


def _candidates(lightness: np.ndarray, chroma: np.ndarray) -> list[_Candidate]:
    """平坦连通域 → 过滤后的候选（含右下 box、区域均值亮度/色度）。"""
    from skimage.measure import label, regionprops

    height, width = lightness.shape
    w = int(round(FLAT_WINDOW_FRAC * max(height, width))) | 1  # 奇数窗
    w = max(FLAT_WINDOW_MIN, min(FLAT_WINDOW_MAX, w))

    flat = _local_std(lightness, w) < FLAT_STD_MAX
    if not flat.any():
        return []

    min_area = max(int(height * width * MIN_AREA_RATIO), 1)
    max_area = int(height * width * MAX_AREA_RATIO)
    out: list[_Candidate] = []
    for region in regionprops(label(flat)):
        top, left, bottom, right = region.bbox  # skimage 右下开区间
        side_h, side_w = bottom - top, right - left
        area = int(region.area)
        if area < min_area or area > max_area:
            continue
        if min(side_h, side_w) < MIN_REGION_SIDE:
            continue
        if max(side_h, side_w) > ASPECT_MAX * max(1, min(side_h, side_w)):
            continue

        mask = region.image
        patch = lightness[top:bottom, left:right][mask]
        patch_chroma = chroma[top:bottom, left:right][mask]
        # 边界像素（凸包与实心区域同）—— 大区域免得拿百万点算凸包
        padded = np.pad(mask, 1)
        inner = (
            padded[:-2, 1:-1]
            & padded[2:, 1:-1]
            & padded[1:-1, :-2]
            & padded[1:-1, 2:]
        )
        bys, bxs = np.where(mask & ~inner)
        points = np.column_stack([bxs + left, bys + top])
        if _minrect_fill(points, area) <= MINRECT_FILL_MIN:
            continue

        out.append(
            _Candidate(
                box=(left, top, right - 1, bottom - 1),  # 转含右下
                area=area,
                mean_L=float(patch.mean()),
                std_L=float(patch.std()),
                mean_chroma=float(patch_chroma.mean()),
            )
        )
    return out


def _find_strip(
    cands: list[_Candidate], lightness: np.ndarray, diag: float, chroma_max: float
) -> ReferenceDetection | None:
    """找白-灰-黑三联条：贴边 + 尺寸相近 + 主轴上 L 单调阶梯。按邻接表只枚举「中点 + 两个邻居」，不做全三元组。

    主轴由三块质心 PCA 自求（照片可任意旋转）；中间那块 = 灰卡。
    三块按定义都是中性反射体，各自都得过中性闸门（Ruling 24）。
    """
    cands = [c for c in cands if c.mean_chroma <= chroma_max]
    cands = sorted(cands, key=lambda c: c.area, reverse=True)[:STRIP_MAX_CANDIDATES]
    gap_max = STRIP_GAP_FRAC * diag
    span = float(np.percentile(lightness, 98) - np.percentile(lightness, 2))
    gap_min = L_GAP_FRAC * max(span, 1e-6)

    def adjacent(a: _Candidate, b: _Candidate) -> bool:
        dx = max(a.box[0] - b.box[2], b.box[0] - a.box[2], 0)
        dy = max(a.box[1] - b.box[3], b.box[1] - a.box[3], 0)
        return math.hypot(dx, dy) < gap_max

    def similar(a: _Candidate, b: _Candidate) -> bool:
        ratio = a.area / b.area
        return STRIP_AREA_RATIO_LO <= ratio <= STRIP_AREA_RATIO_HI

    def centroid(c: _Candidate) -> np.ndarray:
        l, t, r, b = c.box
        return np.array([(l + r) / 2.0, (t + b) / 2.0])

    n = len(cands)
    # 邻接表：贴边且尺寸相近（中间那块与两端各自满足的关系）
    linked = [
        [j for j in range(n) if j != i and adjacent(cands[i], cands[j]) and similar(cands[i], cands[j])]
        for i in range(n)
    ]

    best: tuple[int, ReferenceDetection] | None = None
    for m in range(n):
        nbrs = linked[m]
        for x in range(len(nbrs)):
            for y in range(x + 1, len(nbrs)):
                triple = (cands[nbrs[x]], cands[m], cands[nbrs[y]])
                # 主轴 = 质心第一主成分（不假定水平）
                pts = np.stack([centroid(c) for c in triple])
                centered = pts - pts.mean(axis=0)
                _, _, vt = np.linalg.svd(centered, full_matrices=False)
                order = np.argsort(centered @ vt[0])
                first, mid, last = (triple[order[0]], triple[order[1]], triple[order[2]])
                # 每个三联只在其主轴中点处计一次；中点不是 m 的组合由别的 m 负责
                if mid is not cands[m]:
                    continue
                l_first, l_mid, l_last = first.mean_L, mid.mean_L, last.mean_L
                if not (l_first > l_mid > l_last or l_first < l_mid < l_last):
                    continue
                if abs(l_first - l_mid) <= gap_min or abs(l_mid - l_last) <= gap_min:
                    continue
                # L 高的那端是白卡，低的那端是黑卡
                bright, dark = (first, last) if l_first > l_last else (last, first)
                total = first.area + mid.area + last.area
                found = ReferenceDetection(
                    kind="gray",
                    box=mid.box,
                    cards={"white": bright.box, "gray": mid.box, "black": dark.box},
                )
                if best is None or total > best[0]:
                    best = (total, found)
    return best[1] if best is not None else None


def _fallback(cands: list[_Candidate], chroma_max: float) -> ReferenceDetection | None:
    """单卡兜底：中性优先 → 灰卡优先 → 白纸；没有中性候选 → None（不猜白平衡）。"""
    cands = [c for c in cands if c.mean_chroma <= chroma_max]
    if not cands:
        return None
    grayish = [c for c in cands if GRAY_L_RANGE[0] <= c.mean_L < GRAY_L_RANGE[1]]
    whitish = [c for c in cands if c.mean_L >= SINGLE_WHITE_L]
    if grayish:
        pool, kind = grayish, "gray"
    elif whitish:
        pool, kind = whitish, "white"
    else:
        pool, kind = cands, "gray"  # 深中性也当灰卡（等化通道）
    # 同类里取最大（面积/填充/长宽比已把背景巨块和斑点挡在外面）
    best = max(pool, key=lambda c: (c.area, -c.std_L))
    return ReferenceDetection(kind=kind, box=best.box, cards=None)


def detect_reference(image: Image.Image) -> ReferenceDetection | None:
    """找参考物区域（spec §1.2：灰卡优先、白纸 fallback、都没有 → None）。

    三联条（白-灰-黑相邻成条）优先：命中即以中间的灰卡为主参考，三框一起回给 UI。
    不成条时按亮度兜底到单卡。返回的 box 是**含右下**的像素框；PIL 的
    `Image.crop` 右/下是开区间，喂它时要 `(l, t, r + 1, b + 1)`。
    """
    from skimage.color import rgb2lab

    # rgb2lab 只对 uint8 自动除以 255；float 输入必须自己归一到 [0,1]。
    lab = rgb2lab(np.asarray(image.convert("RGB"), dtype=np.float64) / 255.0)
    lightness = lab[..., 0] / 100.0  # 现有约定：L 归一到 0..1
    chroma = np.hypot(lab[..., 1], lab[..., 2])

    cands = _candidates(lightness, chroma)
    chroma_max = _neutral_chroma_max(chroma)
    strip = _find_strip(
        cands, lightness, diag=float(np.hypot(*lightness.shape[::-1])), chroma_max=chroma_max
    )
    return strip if strip is not None else _fallback(cands, chroma_max)


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
    """以框内像素为基准做白平衡，应用到整图。

    box=(l,t,r,b) 是含右下的（同 `detect_reference` 返回值）；内部转成 PIL 的
    开区间 crop，调用方无需转换。
    """
    rgb = image.convert("RGB")
    l, t, r, b = box
    # box 是含右下的（detect_reference 契约）；PIL crop 右/下开区间，要 +1
    pixels = np.asarray(rgb.crop((l, t, r + 1, b + 1)), dtype=np.float64).reshape(-1, 3)
    return apply_gains(rgb, white_balance_gain(pixels.mean(axis=0), baseline))
