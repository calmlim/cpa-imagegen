"""Explicit local size adjustment; no credentials or network requests."""

from io import BytesIO
from pathlib import Path
import re

from PIL import Image, ImageOps

from .core import save_png, validate_input_image, validate_output_path
from .errors import ImagegenError


def resize_image(source: Path, out: Path, *, size: str, mode: str, overwrite: bool = False) -> dict:
    source, out = source.expanduser().resolve(), out.expanduser().absolute()
    validate_output_path(out, overwrite=overwrite)
    if source == out.resolve():
        raise ImagegenError("input", "Input and output images must have different paths.")
    if not re.fullmatch(r"[1-9]\d*x[1-9]\d*", size):
        raise ImagegenError("input", "Local resize requires an explicit WIDTHxHEIGHT size.")
    width, height = map(int, size.split("x"))
    if width * height > Image.MAX_IMAGE_PIXELS:
        raise ImagegenError("input", "Output size exceeds Pillow's image pixel safety limit.")
    if mode not in {"pad", "crop"}:
        raise ImagegenError("input", "Local resize mode must be pad or crop.")
    validate_input_image(source)
    try:
        with Image.open(source) as original:
            # Match the displayed orientation of camera/reference images.
            image = ImageOps.exif_transpose(original).convert("RGBA")
        source_width, source_height = image.size
        target = (width, height)
        if mode == "crop":
            result = ImageOps.fit(image, target, method=Image.Resampling.LANCZOS)
        else:
            contained = ImageOps.contain(image, target, method=Image.Resampling.LANCZOS)
            result = Image.new("RGBA", target, (0, 0, 0, 0))
            result.alpha_composite(contained, ((width - contained.width) // 2,
                                              (height - contained.height) // 2))
        data = BytesIO()
        result.save(data, format="PNG")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ImagegenError("input", "Cannot decode or resize the input image.") from None
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ImagegenError("save", "Cannot create output directory.") from None
    save_png(data.getvalue(), out, overwrite=overwrite)
    return {"operation": "resize", "local_processing": True, "mode": mode,
            "source_path": str(source), "source_width": source_width, "source_height": source_height,
            "path": str(out.resolve()), "width": width, "height": height, "format": "png"}
