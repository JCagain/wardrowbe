"""记录季节推导（spec §3.1 / §10.1，fixes #32）。

只用于**记录**；衣物季节是 AI 打 + 手改，不走这里。推荐引擎里的
`item_scorer.get_season()` 月份口径不同（6-8 夏），属休眠的推荐代码，不改。
"""
from datetime import date

RECORD_SEASONS: tuple[str, ...] = ("spring", "summer", "fall", "winter")

_SEASON_BY_MONTH = {
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer", 9: "summer",
    10: "fall", 11: "fall",
    12: "winter", 1: "winter", 2: "winter",
}


def season_for_date(d: date) -> str:
    return _SEASON_BY_MONTH[d.month]
