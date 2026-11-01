"""OpenAI Images-compatible adapter, with no service fallback or retries."""

import base64
import binascii
from contextlib import ExitStack
from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

import httpx
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI
from PIL import Image, UnidentifiedImageError

from .config import Settings
from .errors import ImagegenError, redact

MAX_IMAGE_BYTES = 50 * 1024 * 1024


@dataclass
class ImageJob:
    prompt: str
    out: Path
    size: str = "1024x1024"
    quality: str = "medium"
    images: tuple[Path, ...] = ()
    overwrite: bool = False

    def validate(self) -> None:
        if not self.prompt.strip():
            raise ImagegenError("input", "Prompt must not be empty.")
        if not re.fullmatch(r"auto|[1-9]\d*x[1-9]\d*", self.size):
            raise ImagegenError("input", "size must be auto or WIDTHxHEIGHT.")
        if not self.quality.strip():
            raise ImagegenError("input", "quality must not be empty.")
        if self.out.suffix.lower() != ".png":
            raise ImagegenError("input", "This release writes PNG files; --out must end in .png.")
        if self.out.exists() and (not self.overwrite or not self.out.is_file()):
            raise ImagegenError("save", "Output already exists; choose another path or use --overwrite for a file.")
        if self.out.is_symlink():
            raise ImagegenError("save", "Output must not be a symbolic link.")
        for path in self.images:
            if path.resolve() == self.out.resolve():
                raise ImagegenError("input", "Input and output images must have different paths.")
            try:
                if path.stat().st_size > MAX_IMAGE_BYTES:
                    raise ImagegenError("input", "Input image exceeds 50 MiB.")
                with Image.open(path) as image:
                    if image.format not in {"PNG", "JPEG", "WEBP"}:
                        raise ImagegenError("input", "Input images must be PNG, JPEG or WebP.")
                    image.verify()
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
                raise ImagegenError("input", f"Cannot read a valid input image: {path}") from None


def validate_image(data: bytes) -> tuple[int, int]:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ImagegenError("response", "Empty image or image exceeds 50 MiB.")
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
            return image.size
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ImagegenError("response", "Gateway returned invalid image data.") from None


def save_png(data: bytes, path: Path, *, overwrite: bool) -> tuple[int, int]:
    dimensions = validate_image(data)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".png", delete=False) as handle:
            temporary = Path(handle.name)
            with Image.open(BytesIO(data)) as image:
                image.save(handle, format="PNG")
        if overwrite:
            os.replace(temporary, path)
        else:
            # Atomic no-clobber publication: another process cannot win a check/write race.
            os.link(temporary, path)
    except OSError:
        raise ImagegenError("save", "Cannot save image; check output permissions, free space and file collisions.") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return dimensions


class ImageService:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def _client(self) -> OpenAI:
        return OpenAI(base_url=self.settings.base_url, api_key=self.settings.api_key,
                      timeout=self.settings.timeout, max_retries=0,
                      http_client=httpx.Client(transport=self.transport,
                                               timeout=self.settings.timeout))

    def _error(self, exc: APIError) -> ImagegenError:
        category = "upstream"
        if isinstance(exc, APITimeoutError):
            category, message = "timeout", "Request timed out; upstream completion is unknown. It was not retried."
        elif isinstance(exc, APIConnectionError):
            category, message = "connection", "Cannot connect to the gateway. The request was not retried."
        elif isinstance(exc, APIStatusError):
            category = {401: "authentication", 403: "authentication", 429: "rate_limit"}.get(exc.status_code, "upstream")
            message = f"HTTP {exc.status_code}: {redact(str(exc), self.settings.api_key)}"
        else:
            message = "Gateway returned an invalid API response."
        return ImagegenError(category, message, request_id=getattr(exc, "request_id", None))

    def doctor(self) -> dict:
        try:
            with self._client() as client:
                page = client.models.list()
                listed = any(model.id == self.settings.model for model in page.data)
        except APIError as exc:
            if isinstance(exc, APIStatusError) and exc.status_code in {404, 405}:
                return {"configured": True, "gateway_reachable": True,
                        "models_endpoint": "unsupported", "model_listed": None,
                        "model": self.settings.model, "image_generation_verified": False}
            raise self._error(exc) from None
        except (ValueError, TypeError, AttributeError):
            raise ImagegenError("response", "Models endpoint returned an invalid model list.") from None
        return {"configured": True, "gateway_reachable": True,
                "models_endpoint": "available", "model_listed": listed,
                "model": self.settings.model, "image_generation_verified": False}

    def _download(self, url: str) -> bytes:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ImagegenError("response", "Image URL must be HTTP(S) without embedded credentials.")
        try:
            # Separate client, deliberately without the gateway's bearer token.
            with httpx.Client(transport=self.transport, timeout=self.settings.timeout,
                              follow_redirects=True) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    chunks, total = [], 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > MAX_IMAGE_BYTES:
                            raise ImagegenError("download", "Image download exceeds 50 MiB.")
                        chunks.append(chunk)
                    return b"".join(chunks)
        except (httpx.HTTPError, ValueError):
            raise ImagegenError("download", "Cannot download image URL. Generation was not repeated.") from None

    def run(self, job: ImageJob, *, edit: bool = False, dry_run: bool = False) -> dict:
        job.validate()
        if edit and not job.images:
            raise ImagegenError("input", "edit requires at least one --image.")
        path = job.out.expanduser().resolve()
        request = {"model": self.settings.model, "prompt": job.prompt,
                   "size": job.size, "quality": job.quality, "n": 1, "output_format": "png"}
        if dry_run:
            return {"dry_run": True, "operation": "edit" if edit else "generate",
                    "request": request, "images": [str(p.resolve()) for p in job.images],
                    "path": str(path), "image_generation_verified": False}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=path.parent):
                pass
        except OSError:
            raise ImagegenError("save", "Output directory is not writable; no image request was sent.") from None
        try:
            with self._client() as client, ExitStack() as stack:
                if edit:
                    files = [stack.enter_context(p.open("rb")) for p in job.images]
                    response = client.images.edit(image=files, **request)
                else:
                    response = client.images.generate(**request)
        except APIError as exc:
            raise self._error(exc) from None
        except OSError:
            raise ImagegenError("input", "Could not open input image for upload.") from None
        except (ValueError, TypeError):
            raise ImagegenError("response", "Gateway returned an invalid Images API response.") from None
        items = getattr(response, "data", None)
        if not isinstance(items, list) or len(items) != 1:
            raise ImagegenError("response", "Expected exactly one image in the API response.")
        item = items[0]
        encoded = getattr(item, "b64_json", None)
        url = getattr(item, "url", None)
        if encoded:
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError, TypeError):
                raise ImagegenError("response", "Gateway returned invalid Base64 image data.") from None
        elif url:
            data = self._download(url)
        else:
            raise ImagegenError("response", "API response contains neither image data nor an image URL.")
        width, height = save_png(data, path, overwrite=job.overwrite)
        actual_model = getattr(response, "model", None)
        usage = getattr(response, "usage", None)
        return {"path": str(path), "requested_model": self.settings.model,
                "model": actual_model or self.settings.model,
                "model_source": "upstream" if actual_model else "requested",
                "request_id": getattr(response, "_request_id", None),
                "usage": usage.model_dump(mode="json") if hasattr(usage, "model_dump") else usage,
                "width": width, "height": height, "format": "png",
                "image_generation_verified": True}
