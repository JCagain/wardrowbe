import numpy as np
import pytest
from PIL import Image

from scripts.embedding_probe import (
    _parse_pairs,
    augment,
    distinctness,
    retrieval_metrics,
    verdict,
)


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


def test_distinctness_reports_most_similar_pair():
    vs = [np.array([1.0, 0.0]), np.array([0.0, 1.0]), np.array([0.0, 1.0])]
    d = distinctness(vs)
    assert d["pair"] == (1, 2) and d["max"] == pytest.approx(1.0)
    assert d["mean"] == pytest.approx(1 / 3)


def test_verdict_exit_codes():
    assert verdict({"max": 0.99, "mean": 0.4}, 0.9) == (0, "PASS")  # near-duplicate alone is not collapse
    assert verdict({"max": 0.5, "mean": 0.4}, 0.5) == (3, "WEAK")
    assert verdict({"max": 1.0, "mean": 0.97}, 0.9)[0] == 1


def test_parse_pairs_validates(tmp_path):
    img = tmp_path / "c.jpg"
    img.write_bytes(b"x")
    uid = "123e4567-e89b-12d3-a456-426614174000"
    assert _parse_pairs([f"{img}:{uid}"])[0][0] == img
    assert isinstance(_parse_pairs([f"{img}:nope"]), str)
    assert isinstance(_parse_pairs([f"{tmp_path}/missing.jpg:{uid}"]), str)
    assert isinstance(_parse_pairs(["noseparator"]), str)
