import shutil
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image, ImageOps

from app.config import get_settings
from app.services import background_removal
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
        base_path = image_path.rsplit(".", 1)[0]
        medium_path = f"{base_path}_medium.jpg"
        thumb_path = f"{base_path}_thumb.jpg"

        for size_name, max_size in SIZES.items():
            if size_name == "original":
                file_path = self.storage_path / image_path
                quality = 95
            elif size_name == "medium":
                file_path = self.storage_path / medium_path
                quality = 90
            else:
                file_path = self.storage_path / thumb_path
                quality = 88

            img_copy = image.copy()
            img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)

            output = BytesIO()
            img_copy.save(output, format="JPEG", quality=quality, optimize=True)
            file_path.write_bytes(output.getvalue())

        return {
            "image_path": image_path,
            "medium_path": medium_path,
            "thumbnail_path": thumb_path,
        }

    def remove_background(
        self,
        image_path: str,
        bg_color: tuple[int, int, int] = (255, 255, 255),
    ) -> dict[str, str]:
        base_path = image_path.rsplit(".", 1)[0]
        original_full = self.storage_path / image_path

        if not original_full.exists():
            raise ValueError(f"Image not found: {image_path}")

        backup_path = f"{base_path}_orig.jpg"
        backup_full = self.storage_path / backup_path
        # First removal wins: a second removal must not overwrite the true
        # original with an already-processed image
        if not backup_full.exists():
            shutil.copy2(original_full, backup_full)

        image = Image.open(original_full).convert("RGB")
        provider = background_removal.get_provider()
        result = provider.remove(image)

        # Composite onto solid color background
        background = Image.new("RGBA", result.size, (*bg_color, 255))
        background.paste(result, mask=result.split()[3])
        final = background.convert("RGB")

        paths = self._save_all_sizes(final, image_path)
        paths["original_backup_path"] = backup_path
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

        Args:
            image_path: Relative path to the original image (e.g., "user_id/filename.jpg")
            direction: "cw" for clockwise 90°, "ccw" for counter-clockwise 90°

        Returns:
            dict with updated paths (same as input since we overwrite)
        """
        original_full = self.storage_path / image_path

        if not original_full.exists():
            raise ValueError(f"Image not found: {image_path}")

        angle = -90 if direction == "cw" else 90  # PIL rotates counter-clockwise by default

        image = Image.open(original_full)

        if image.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        rotated = image.rotate(angle, expand=True)

        return self._save_all_sizes(rotated, image_path)

    def calibrate_image(
        self,
        image_path: str,
        calibration_original_path: str,
        box: tuple[int, int, int, int],
        baseline: str,
    ) -> dict[str, str]:
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
        result = calibrate(base, box, baseline)
        return self._save_all_sizes(result, image_path)

    def manual_white_balance(
        self,
        image_path: str,
        calibration_original_path: str,
        kelvin: float,
        tint: float,
    ) -> dict[str, str]:
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
        return self._save_all_sizes(apply_gains(base, gains), image_path)

    def reset_calibration(
        self, image_path: str, calibration_original_path: str
    ) -> dict[str, str]:
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
        paths = self._save_all_sizes(base, image_path)
        # original 档必须是副本字节本身（原样还原，不接受重编码漂移）
        (self.storage_path / image_path).write_bytes(pristine)
        return paths
