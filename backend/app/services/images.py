import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MIN_SIDE = 320
MAX_STORED_SIDE = 2560


class ImageRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class ProcessedImage:
    data: bytes
    width: int
    height: int
    image: Image.Image


def process_upload(raw: bytes, max_bytes: int) -> ProcessedImage:
    """Validate by content (never by client-declared type), strip metadata (EXIF/GPS) by re-encoding."""
    if not raw:
        raise ImageRejected("empty_file", "The file is empty.")
    if len(raw) > max_bytes:
        raise ImageRejected("file_too_large", f"The photo is larger than {max_bytes // (1024 * 1024)} MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as probe:
                fmt = probe.format
                probe.verify()
            if fmt not in ALLOWED_FORMATS:
                raise ImageRejected("unsupported_image", "Only JPEG, PNG or WebP photos are accepted.")
            img = Image.open(BytesIO(raw))
            img.load()
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise ImageRejected("unsupported_image", "The file is not a valid JPEG, PNG or WebP photo.")
    img = ImageOps.exif_transpose(img).convert("RGB")
    if min(img.size) < MIN_SIDE:
        raise ImageRejected("image_too_small", "The photo resolution is too low.")
    img.thumbnail((MAX_STORED_SIDE, MAX_STORED_SIDE))
    out = BytesIO()
    img.save(out, format="JPEG", quality=90, optimize=True)  # fresh encode: no EXIF is carried over
    return ProcessedImage(out.getvalue(), img.width, img.height, img)
