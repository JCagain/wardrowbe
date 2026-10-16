from app.services.garment_regions import MAX_REGIONS, clamp_regions, parse_garment_regions


def test_parses_qwen_style_relative_boxes():
    text = '```json\n{"regions": [{"body_part": "tops", "box": [100, 50, 600, 450]}]}\n```'
    regions = parse_garment_regions(text, width=2000, height=1000)
    assert regions == [{"body_part": "tops", "box": {"l": 200, "t": 50, "r": 1199, "b": 449}, "source": "auto"}]


def test_swaps_reversed_clamps_and_drops_bad():
    text = """{"regions": [
      {"body_part": "bottoms", "box": [800, 900, 200, 400]},
      {"body_part": "wings", "box": [0, 0, 500, 500]},
      {"body_part": "footwear", "box": [-50, 950, 1200, 1100]},
      {"body_part": "tops", "box": [10, 10, 11, 11]},
      {"body_part": "tops", "box": "nope"}
    ]}"""
    regions = parse_garment_regions(text, width=1000, height=1000)
    assert [r["body_part"] for r in regions] == ["bottoms", "footwear"]
    assert regions[0]["box"] == {"l": 200, "t": 400, "r": 799, "b": 899}
    assert regions[1]["box"] == {"l": 0, "t": 950, "r": 999, "b": 999}


def test_non_json_returns_empty():
    assert parse_garment_regions("I see a shirt.", 100, 100) == []
    assert parse_garment_regions('{"regions": "x"}', 100, 100) == []


def test_caps_region_count():
    one = '{"body_part": "tops", "box": [0, 0, 500, 500]}'
    text = '{"regions": [' + ",".join([one] * 20) + "]}"
    assert len(parse_garment_regions(text, 100, 100)) == MAX_REGIONS


def test_clamp_regions_for_user_edits():
    regions = [
        {"body_part": "tops", "box": {"l": -5, "t": 3, "r": 5000, "b": 40}, "source": "manual"},
        {"body_part": "tops", "box": {"l": 50, "t": 50, "r": 52, "b": 52}, "source": "manual"},
    ]
    assert clamp_regions(regions, width=100, height=60) == [
        {"body_part": "tops", "box": {"l": 0, "t": 3, "r": 99, "b": 40}, "source": "manual"}
    ]
