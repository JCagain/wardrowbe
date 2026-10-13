"""一件衣物主图的文件集命名约定 —— 全仓库唯一出处。

主图在存储里是一组同 base 的文件：

    {base}{ext}          工作图（original 档）
    {base}_medium{ext}   medium 档
    {base}_thumb{ext}    thumbnail 档
    {base}_src.jpg       校色前原图副本（fixes #6；旋转时同步，fixes #7a）
    {base}_orig.jpg      抠图前像素备份（还原重抠、画笔补抠、重抠的像素来源）
    {base}_mask.png      mask 旁挂，L 模式（fixes #11）

`ext` 跟着有无 alpha 在 .jpg / .png 间翻转，`base` 永远不变——所以一切派生路径
都从 base 推，不要在别处再拼 `_src` / `_orig` / `_mask` 字符串。
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

SIZE_KEYS = ("image_path", "medium_path", "thumbnail_path")


@dataclass(frozen=True)
class ImageFiles:
    base: str

    @classmethod
    def of(cls, image_path: str) -> ImageFiles:
        return cls(image_path.rsplit(".", 1)[0])

    @property
    def source(self) -> str:
        return f"{self.base}_src.jpg"

    @property
    def backup(self) -> str:
        return f"{self.base}_orig.jpg"

    @property
    def mask(self) -> str:
        return f"{self.base}_mask.png"

    def sizes(self, ext: str) -> dict[str, str]:
        return {
            "image_path": f"{self.base}{ext}",
            "medium_path": f"{self.base}_medium{ext}",
            "thumbnail_path": f"{self.base}_thumb{ext}",
        }


def assign_size_paths(target: object, paths: Mapping[str, object]) -> None:
    """把一次图像改写真实写出的三档路径写回目标（ORM 物品）。

    `_save_all_sizes` 可能翻转扩展名，所以任何改写主图的操作之后都必须写回。
    """
    for key in SIZE_KEYS:
        setattr(target, key, paths[key])
