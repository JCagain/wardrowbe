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
        base_name = base_filename.rsplit(".", 1)[0]

        user_path = self._get_user_path(user_id)

        # 校色前原图（fixes #6）：整个管线里唯一不可变的文件。校色/抠图/旋转
        # 都只写工作图与三档尺寸，「重置回原图」从这里取。上传原始字节不保留。
        source_path: str | None = None
        if keep_source:
            source_name = f"{base_name}_src.jpg"
            # _resize_image (not a raw JPEG save): an RGBA/P PNG upload must be
            # composited to RGB first, exactly as the working sizes are.
            source_bytes = self._resize_image(image.copy(), SIZES["original"], quality=95)
            (user_path / source_name).write_bytes(source_bytes)
            source_path = f"{user_id}/{source_name}"

        paths = {}

        # Process and save each size
        for size_name, max_size in SIZES.items():
            if size_name == "original":
                suffix = ""
                quality = 95  # Highest quality for original
            elif size_name == "medium":
                suffix = "_medium"
                quality = 90
            else:
                suffix = "_thumb"
                quality = 88  # Good quality for thumbnails

            filename = f"{base_name}{suffix}.jpg"
            file_path = user_path / filename

            # For original, preserve as much quality as possible
            # For others, resize with appropriate quality
            resized_data = self._resize_image(image.copy(), max_size, quality=quality)
            file_path.write_bytes(resized_data)

            # Store relative path
            paths[size_name] = f"{user_id}/{filename}"

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
        base_path = image_path.rsplit(".", 1)[0]
        old_ext = Path(image_path).suffix
        original_path = f"{base_path}{ext}"
        medium_path = f"{base_path}_medium{ext}"
        thumb_path = f"{base_path}_thumb{ext}"

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
            for rel_path in (image_path, f"{base_path}_medium{old_ext}", f"{base_path}_thumb{old_ext}"):
                stale = self.storage_path / rel_path
                if stale.exists():
                    stale.unlink()

        return {
            "image_path": original_path,
            "medium_path": medium_path,
            "thumbnail_path": thumb_path,
        }

    def _mask_path_for(self, image_path: str) -> str:
        """mask 旁挂路径约定：与主图同 base 的 `_mask.png`（remove_background 同款）。"""
        return f"{image_path.rsplit('.', 1)[0]}_mask.png"

    def _clear_mask(self, image_path: str) -> None:
        """删掉 mask 旁挂。校色从 `_src` 重推导像素，旧 mask 必然过期。"""
        mask_full = self.storage_path / self._mask_path_for(image_path)
        if mask_full.exists():
            mask_full.unlink()

    def _save_calibrated(self, image_path: str, image: Image.Image) -> dict[str, str | bool]:
        """校色收尾：写三档、清掉过期 mask，并上报 `mask_cleared`（fixes 过期 mask）。

        校色从 `calibration_original_path`（RGB JPEG）重推导像素，抠图结果必然
        不再对应——留着 mask 就是过期 mask，`update_mask` 会拿它合成垃圾。调用方
        看到 `mask_cleared` 应把 `mask_path` 置 None，并提示用户重新抠图。
        """
        self._clear_mask(image_path)
        paths: dict[str, str | bool] = self._save_all_sizes(image, image_path)
        paths["mask_cleared"] = True
        return paths

    def remove_background(self, image_path: str) -> dict[str, str]:
        """抠图：存 RGBA PNG 主图 + L 模式 mask 旁挂。不合成纯色底（fixes #9）。"""
        base_path = image_path.rsplit(".", 1)[0]
        original_full = self.storage_path / image_path
        if not original_full.exists():
            raise ValueError(f"Image not found: {image_path}")

        backup_path = f"{base_path}_orig.jpg"
        backup_full = self.storage_path / backup_path
        # First removal wins：第二次抠图不得用已处理图覆盖真原图
        if not backup_full.exists():
            shutil.copy2(original_full, backup_full)

        image = Image.open(original_full).convert("RGB")
        result = background_removal.get_provider().remove(image)

        mask = result.getchannel("A")
        mask_path = self._mask_path_for(image_path)
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

        image = Image.open(original_full)
        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        if has_alpha:
            image = image.convert("RGBA")
        elif image.mode != "RGB":
            image = image.convert("RGB")

        rotated = image.rotate(angle, expand=True)

        mask_full = self.storage_path / self._mask_path_for(image_path)
        if mask_full.exists():
            mask = mask_service.load_mask(mask_full)
            mask_service.save_mask(mask.rotate(angle, expand=True), mask_full)

        return self._save_all_sizes(rotated, image_path)

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
