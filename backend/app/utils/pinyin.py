"""Pinyin sort helpers — the vocabulary is ordered by Chinese-name pinyin."""
from pypinyin import lazy_pinyin


def pinyin_sort_key(label: str) -> str:
    return "".join(lazy_pinyin(label))
