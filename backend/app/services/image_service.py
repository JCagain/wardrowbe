import os
import shutil
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image, ImageOps

from app.config import get_settings
from app.services import background_removal, mask_service
from app.services.color_calibration import GAIN_MAX, GAIN_MIN, apply_gains, calibrate
from app.services.image_files import ImageFiles

settings = get_settings()

# Image size configurations
# Thumbnail: Used in cards/grids. 400px supports ~200px display on retina
# Medium: Used in detail views and outfit displays
# Original: Full resolution for zoom/download
SIZES = {
    "thumbnail": (400, 400),
    "medium": (800, 800),
    "original": (2400, 2400),
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


class ImageTooLargeError(ValueError):
    def __init__(self, pixels: int, limit_pixels: int):
        self.pixels = pixels
        self.limit_pixels = limit_pixels
        super().__init__(
            f"Image is {pixels / 1_000_000:.1f}MP, above the {limit_pixels / 1_000_000:.1f}MP limit"
        )


class ImageService:
    def __init__(self, storage_path: str | None = None):
        self.storage_path = Path(storage_path or settings.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _get_user_path(self, user_id: uuid.UUID) -> Path:
        user_path = self.storage_path / str(user_id)
        user_path.mkdir(parents=True, exist_ok=True)
        return user_path

    def _generate_filename(self, extension: str = ".jpg") -> str:
        """Generate a unique filename."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        return f"{timestamp}_{unique_id}{extension}"

    def _convert_heic(self, image_data: bytes) -> Image.Image:
        """Convert HEIC/HEIF to PIL Image."""
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except ImportError:
            pass

        return Image.open(BytesIO(image_data))

    def _open_bounded(self, image_data: bytes, ext: str) -> Image.Image:
        """Open an upload without ever allocating a full-resolution buffer for it.

        Image.open parses only the header, and draft() picks a JPEG DCT scaling
        factor, so both run before any pixel decode. draft never scales below the
        requested box, so the variants generated afterwards are unaffected. It is
        a no-op for formats that cannot scale during decode, which is why the
        ceiling is checked on the post-draft size.
        """
        if ext in (".heic", ".heif"):
            image = self._convert_heic(image_data)
        else:
            image = Image.open(BytesIO(image_data))

        image.draft("RGB", SIZES["original"])

        pixels = image.size[0] * image.size[1]
        limit_pixels = int(settings.max_image_megapixels * 1_000_000)
        if pixels > limit_pixels:
            raise ImageTooLargeError(pixels, limit_pixels)

        return image

    def _resize_image(
        self,
        image: Image.Image,
        max_size: tuple[int, int],
        quality: int = 92,
    ) -> bytes:
        """Resize image maintaining aspect ratio."""
        # Convert to RGB if necessary (handles RGBA, P mode, etc.)
        if image.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Resize maintaining aspect ratio
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Save to bytes
        output = BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()

    async def process_and_store(
        self,
        user_id: uuid.UUID,
        image_data: bytes,
        original_filename: str,
        keep_source: bool = True,
    ) -> dict[str, str | None]:
        """
        Process an uploaded image and store all sizes.

        Returns dict with paths for each size:
        {
            "original": "user_id/20240116_123456_abc123.jpg",
            "medium": "user_id/20240116_123456_abc123_medium.jpg",
            "thumbnail": "user_id/20240116_123456_abc123_thumb.jpg",
            "calibration_original_path": "user_id/20240116_123456_abc123_src.jpg",
        }

        keep_source=False skips the immutable pre-calibration copy (calibration
        source is only useful for main images; additional images neither
        calibrate nor matte) and reports calibration_original_path as None.
        """
        # Validate file extension
        ext = Path(original_filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        image = self._open_bounded(image_data, ext)

        # iPhones (and some Android cameras) store a raw sensor image plus an EXIF
        # orientation tag instead of rotating pixels, so portrait photos must be
        # transposed here or they end up sideways in storage and in AI tagging.
        image = ImageOps.exif_transpose(image)

        base_filename = self._generate_filename(".jpg")
        self._get_user_path(user_id)  # 确保用户目录存在
        files = ImageFiles.of(f"{user_id}/{base_filename}")

        # 校色前原图（fixes #6）：不得被后续处理产物替换（校色/抠图只写工作图
        # 与三档，永远不把处理结果写回这里），「重置回原图」从这里取。上传原始
        # 字节不保留。唯一允许的改动是旋转的几何同步（fix-spec #7a）：它必须和
        # 工作图始终同尺寸同朝向，否则 detect 的框会裁到错误区域。
        source_path: str | None = None
        if keep_source:
            # _resize_image (not a raw JPEG save): an RGBA/P PNG upload must be
            # composited to RGB first, exactly as the working sizes are.
            source_bytes = self._resize_image(image.copy(), SIZES["original"], quality=95)
            (self.storage_path / files.source).write_bytes(source_bytes)
            source_path = files.source

        targets = files.sizes(".jpg")
        size_keys = {"original": "image_path", "medium": "medium_path", "thumbnail": "thumbnail_path"}
        qualities = {"original": 95, "medium": 90, "thumbnail": 88}
        paths = {}
        for size_name, max_size in SIZES.items():
            rel_path = targets[size_keys[size_name]]
            resized_data = self._resize_image(image.copy(), max_size, quality=qualities[size_name])
            (self.storage_path / rel_path).write_bytes(resized_data)
            paths[size_name] = rel_path

        image_hash = self._phash_of(image)

        return {
            "image_path": paths["original"],
            "medium_path": paths["medium"],
            "thumbnail_path": paths["thumbnail"],
            "calibration_original_path": source_path,
            "image_hash": image_hash,
        }

    def get_image_path(self, relative_path: str) -> Path:
        """Get full path for an image."""
        return self.storage_path / relative_path

    def delete_images(self, paths: dict[str, str | None]) -> None:
        """Delete all image files for an item."""
        for path in paths.values():
            if path:
                full_path = self.storage_path / path
                if full_path.exists():
                    full_path.unlink()

    def validate_image(self, image_data: bytes, content_type: str) -> bool:
        """Validate image data and content type."""
        # Check content type
        if content_type not in ALLOWED_MIME_TYPES:
            return False

        # Check file size (max 20MB)
        if len(image_data) > 20 * 1024 * 1024:
            return False

        # Try to open as image
        try:
            if content_type in ("image/heic", "image/heif"):
                self._convert_heic(image_data)
            else:
                Image.open(BytesIO(image_data))
            return True
        except Exception:
            return False

    def compute_phash(self, image_data: bytes, original_filename: str) -> str:
        """
        Compute perceptual hash (pHash) for an image.

        Returns a 16-character hex string representing the 64-bit hash.
        """
        image = self._open_bounded(image_data, Path(original_filename).suffix.lower())
        return self._phash_of(ImageOps.exif_transpose(image))

    def _phash_of(self, image: Image.Image) -> str:
        if image.mode != "RGB":
            image = image.convert("RGB")
        return str(imagehash.phash(image))

    def compute_phash_from_path(self, image_path: Path) -> str:
        """Compute pHash from a file path."""
        image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        phash = imagehash.phash(image)
        return str(phash)

    @staticmethod
    def hash_distance(hash1: str, hash2: str) -> int:
        """
        Compute Hamming distance between two hashes.

        Lower distance = more similar images.
        Distance 0 = identical/near-identical images.
        Distance < 10 = very similar images.
        """
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        return h1 - h2

    @staticmethod
    def is_duplicate(hash1: str, hash2: str, threshold: int = 8) -> bool:
        """
        Check if two images are duplicates based on hash distance.

        Default threshold of 8 catches near-identical images while allowing
        for minor differences in lighting/compression.
        """
        return ImageService.hash_distance(hash1, hash2) <= threshold

    def _save_all_sizes(self, image: Image.Image, image_path: str) -> dict[str, str]:
        # fixes #8：带 alpha 存 RGBA PNG；无 alpha 仍写 JPEG，存量图不强制迁移。
        # 返回的是真实写出的路径——扩展名跟着格式走，调用方必须把返回值写回。
        has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
        fmt = "PNG" if has_alpha else "JPEG"
        ext = ".png" if has_alpha else ".jpg"
        files = ImageFiles.of(image_path)
        old_ext = Path(image_path).suffix
        new = files.sizes(ext)
        original_path, medium_path, thumb_path = (
            new["image_path"], new["medium_path"], new["thumbnail_path"],
        )

        targets = {
            "original": (original_path, 95),
            "medium": (medium_path, 90),
            "thumbnail": (thumb_path, 88),
        }
        for size_name, max_size in SIZES.items():
            rel_path, quality = targets[size_name]
            img_copy = image.copy()
            img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)
            output = BytesIO()
            if fmt == "PNG":
                img_copy.save(output, format="PNG", optimize=True)
            else:
                img_copy.save(output, format="JPEG", quality=quality, optimize=True)
            (self.storage_path / rel_path).write_bytes(output.getvalue())

        if old_ext and old_ext != ext:
            # 换扩展名后旧三档是无引用孤儿（磁盘泄漏）。先写新档再删旧档：
            # 中途失败最多多占几个文件，不会两头都缺。
            for rel_path in files.sizes(old_ext).values():
                stale = self.storage_path / rel_path
                if stale.exists():
                    stale.unlink()

        return {
            "image_path": original_path,
            "medium_path": medium_path,
            "thumbnail_path": thumb_path,
        }

    def _clear_mask(self, image_path: str) -> bool:
        """删掉 mask 旁挂，返回是否真的删了。校色从 `_src` 重推导像素，旧 mask 必然过期。"""
        mask_full = self.storage_path / ImageFiles.of(image_path).mask
        if mask_full.exists():
            mask_full.unlink()
            return True
        return False

    def _save_calibrated(self, image_path: str, image: Image.Image) -> dict[str, str | bool]:
        """校色收尾：写三档、清掉过期 mask，并上报 `mask_cleared`（fixes 过期 mask）。

        校色从 `calibration_original_path`（RGB JPEG）重推导像素，抠图结果必然
        不再对应——留着 mask 就是过期 mask，`update_mask` 会拿它合成垃圾。调用方
        看到 `mask_cleared` 应把 `mask_path` 置 None，并提示用户重新抠图。

        `mask_cleared` **只在真的删掉了 mask 文件时为 True**：没抠过的图校色完
        不该弹「请重抠」。列 `mask_path` 由调用方只要校色跑过就清，与此标志无关。
        """
        cleared = self._clear_mask(image_path)
        paths: dict[str, str | bool] = self._save_all_sizes(image, image_path)
        paths["mask_cleared"] = cleared
        return paths

    def remove_background(self, image_path: str) -> dict[str, str]:
        """抠图：存 RGBA PNG 主图 + L 模式 mask 旁挂。不合成纯色底（fixes #9）。"""
        original_full = self.storage_path / image_path
        if not original_full.exists():
            raise ValueError(f"Image not found: {image_path}")

        files = ImageFiles.of(image_path)
        backup_path = files.backup
        backup_full = self.storage_path / backup_path
        # First removal wins：第二次抠图不得用已处理图覆盖真原图
        if not backup_full.exists():
            shutil.copy2(original_full, backup_full)

        image = Image.open(original_full).convert("RGB")
        result = background_removal.get_provider().remove(image)

        mask = result.getchannel("A")
        mask_path = files.mask
        mask_service.save_mask(mask, self.storage_path / mask_path)

        paths = self._save_all_sizes(result, image_path)
        paths["original_backup_path"] = backup_path
        paths["mask_path"] = mask_path
        return paths

    def restore_original(self, image_path: str, backup_path: str) -> dict[str, str]:
        backup_full = self.storage_path / backup_path
        if not backup_full.exists():
            raise ValueError(f"Backup not found: {backup_path}")

        image = Image.open(backup_full).convert("RGB")
        paths = self._save_all_sizes(image, image_path)
        backup_full.unlink()
        return paths

    def rotate_image(self, image_path: str, direction: str = "cw") -> dict[str, str]:
        """
        Rotate an image and regenerate all sizes.

        旋转是几何变换：RGBA 主图带着 alpha 一起转（**不**铺白底压成 RGB），
        mask 旁挂用同一角度转，两者继续逐点对应。

        校色前原图副本（`{base}_src.jpg`）与抠图前备份（`{base}_orig.jpg`）同步同角度旋转
        （fix-spec #7a 的几何同步）：detect 在工作图坐标系给框，calibrate / manual / reset 都从副本
        取像素，两边不一致就是坐标空间分裂——白平衡静默取错区域、重置把未旋转
        的副本写回工作图连用户的旋转一起撤销。「重置回原图」= **当前朝向下**的
        校色前像素。副本缺失（keep_source=False 的附加图）则跳过；副本旋转失败
        必须抛错，不许只转工作图就返回。

        Args:
            image_path: Relative path to the original image (e.g., "user_id/filename.jpg")
            direction: "cw" for clockwise 90°, "ccw" for counter-clockwise 90°

        Returns:
            dict with the paths actually written (the extension follows the alpha)
        """
        original_full = self.storage_path / image_path

        if not original_full.exists():
            raise ValueError(f"Image not found: {image_path}")

        angle = -90 if direction == "cw" else 90  # PIL rotates counter-clockwise by default

        # 与工作图同坐标空间的 JPEG 伴随文件：校色前原图副本（fix-spec #7a）与
        # 抠图前备份（还原重抠 / 画笔补抠 / 重抠的像素来源）。两者都必须跟工作图
        # 同朝向，否则「还原原图」或画笔会把未旋转的像素写回旋转后的坐标系。
        #
        # 解码 + 旋转先在内存里做完：任一伴随文件损坏就在这里炸掉，工作图一个
        # 字节都不该被改写。落盘走 tmp + os.replace，绝不 truncate 基线本身——
        # `write_bytes` 是 open('wb') 先截断，ENOSPC 落在写 `_src` 上就是把不可变
        # 基线整个毁掉。失败可重试：基线没被换掉，重试只会转一次。
        files = ImageFiles.of(image_path)
        companions = [self.storage_path / files.source, self.storage_path / files.backup]
        staged: list[tuple[Path, Path]] = []
        try:
            for full in companions:
                if not full.exists():
                    continue
                companion = Image.open(full)
                if companion.mode != "RGB":
                    companion = companion.convert("RGB")
                # 90° 用 rotate(angle, expand=True)：对 90/270 是逐像素精确映射。
                # 重编码一次，quality=95（与首次写入同款），把代际损失压到不可见。
                output = BytesIO()
                companion.rotate(angle, expand=True).save(
                    output, format="JPEG", quality=95, optimize=True
                )
                tmp = full.with_name(full.name + ".tmp")
                tmp.write_bytes(output.getvalue())
                staged.append((tmp, full))

            image = Image.open(original_full)
            has_alpha = image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            )
            if has_alpha:
                image = image.convert("RGBA")
            elif image.mode != "RGB":
                image = image.convert("RGB")

            rotated = image.rotate(angle, expand=True)

            mask_full = self.storage_path / files.mask
            if mask_full.exists():
                mask = mask_service.load_mask(mask_full)
                mask_service.save_mask(mask.rotate(angle, expand=True), mask_full)

            paths = self._save_all_sizes(rotated, image_path)
            # 最后才换基线：上面任何一步失败，伴随文件仍是原样（tmp 由 finally 清掉）。
            for tmp, full in staged:
                os.replace(tmp, full)
            return paths
        finally:
            for tmp, _ in staged:
                tmp.unlink(missing_ok=True)

    def calibrate_image(
        self,
        image_path: str,
        calibration_original_path: str,
        box: tuple[int, int, int, int],
        baseline: str,
    ) -> dict[str, str | bool]:
        """以框内像素做白平衡，写回工作图与三档。原图副本不动。

        box=(l,t,r,b) 含右下（同 `detect_reference` 返回值），原样下传给
        `calibrate`，这里不做坐标转换。每次都从原图副本起算，避免多次校色
        叠加漂移。
        """
        working = self.storage_path / image_path
        if not working.exists():
            raise ValueError(f"Image not found: {image_path}")
        source = self.storage_path / calibration_original_path
        if not source.exists():
            raise ValueError(f"Calibration source not found: {calibration_original_path}")

        base = Image.open(source).convert("RGB")
        l, t, r, b = box
        width, height = base.size
        # box 含右下。越界裁剪会被 PIL 黑边填充地接受（参考均值被带偏成错误
        # 颜色），超大 box 还会先按 box 面积分配内存——在裁剪之前就拒掉。
        if not (0 <= l <= r < width and 0 <= t <= b < height):
            raise ValueError(
                f"Calibration box {tuple(box)} is outside the {width}x{height} image"
            )
        result = calibrate(base, box, baseline)
        return self._save_calibrated(image_path, result)

    def manual_white_balance(
        self,
        image_path: str,
        calibration_original_path: str,
        kelvin: float,
        tint: float,
    ) -> dict[str, str | bool]:
        """色温/色调滑块的手动白平衡。滑块在 UI 上无界，这里把增益夹住。

        6500K 为中性；每 1000K 约 6% 通道偏移。tint 是绿-品红轴。
        """
        source = self.storage_path / calibration_original_path
        if not source.exists():
            raise ValueError(f"Calibration source not found: {calibration_original_path}")
        base = Image.open(source).convert("RGB")

        t = (kelvin - 6500.0) / 1000.0
        gains = np.array([1.0 + 0.06 * t, 1.0 + 0.01 * tint / 100.0, 1.0 - 0.06 * t])
        gains = np.clip(gains, GAIN_MIN, GAIN_MAX)
        return self._save_calibrated(image_path, apply_gains(base, gains))

    def reset_calibration(
        self, image_path: str, calibration_original_path: str
    ) -> dict[str, str | bool]:
        """重置回原图：副本字节原样写回工作图，再重生成三档。

        fixes #6：不对副本做任何像素变换。重置后工作图与副本逐字节一致——
        `_save_all_sizes` 的 JPEG 重编码不保字节，所以 original 档用副本字节
        本身覆盖。
        """
        source = self.storage_path / calibration_original_path
        if not source.exists():
            raise ValueError(f"Calibration source not found: {calibration_original_path}")

        pristine = source.read_bytes()
        base = Image.open(BytesIO(pristine)).convert("RGB")
        paths = self._save_calibrated(image_path, base)
        # original 档必须是副本字节本身（原样还原，不接受重编码漂移）。
        # 写到返回的真实路径上：工作图若是 PNG（抠图产物），`_save_all_sizes`
        # 按无 alpha 会把扩展名换回 .jpg，写入参路径会把 JPEG 字节塞进 .png。
        (self.storage_path / str(paths["image_path"])).write_bytes(pristine)
        return paths

    def update_mask(
        self, image_path: str, mask_path: str, strokes: list[dict]
    ) -> dict[str, str]:
        """改 mask，把 alpha 写回主图并重生成三档（fixes #13）。"""
        main_full = self.storage_path / image_path
        mask_full = self.storage_path / mask_path
        if not main_full.exists():
            raise ValueError(f"Image not found: {image_path}")
        if not mask_full.exists():
            raise ValueError(f"Mask not found: {mask_path}")

        rgba = Image.open(main_full).convert("RGBA")
        new_mask = mask_service.apply_strokes(mask_service.load_mask(mask_full), strokes)
        if new_mask.size != rgba.size:
            # 没有合法路径会造成不一致：remove_background 同数组写两边、rotate
            # 同步旋转、校色直接清 mask。不一致 = 损坏，静默 resize 是产垃圾。
            raise ValueError(
                f"Mask size {new_mask.size} does not match image size {rgba.size}"
            )
        rgba.putalpha(new_mask)
        mask_service.save_mask(new_mask, mask_full)

        paths = self._save_all_sizes(rgba, image_path)
        paths["mask_path"] = mask_path
        return paths
