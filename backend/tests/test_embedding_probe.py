import numpy as np
import pytest
from PIL import Image

from scripts.embedding_probe import augment, distinctness, retrieval_metrics


def test_augment_is_deterministic_and_gray_padded():
    img = Image.new("RGB", (200, 100), (250, 0, 0))
    a, b = augment(img, seed=3), augment(img, seed=3)
    assert a.tobytes() == b.tobytes()
    assert a.getpixel((0, 0)) == (128, 128, 128)
    assert augment(img, seed=4).tobytes() != a.tobytes()


def test_retrieval_metrics():
    m = retrieval_metrics([1, 3, None, 7])
    assert m["recall@1"] == pytest.approx(0.25)
    assert m["recall@5"] == pytest.approx(0.5)
    assert m["recall@10"] == pytest.approx(0.75)
    assert m["mrr"] == pytest.approx((1 + 1 / 3 + 0 + 1 / 7) / 4)


def test_distinctness_flags_collapsed_vectors():
    same = [np.array([1.0, 0.0])] * 3
    assert distinctness(same)["max"] == pytest.approx(1.0)
    spread = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    assert distinctness(spread)["max"] == pytest.approx(0.0)
