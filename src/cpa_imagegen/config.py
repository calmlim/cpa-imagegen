"""Explicit configuration; Codex is consulted only by the import command."""

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import tomllib
from urllib.parse import urlsplit

from platformdirs import user_config_path

from .errors import ImagegenError


def default_config_path() -> Path:
    return user_config_path("cpa-imagegen", appauthor=False) / "config.toml"


def read_toml(path: Path, *, required: bool = False) -> dict:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        if not required:
            return {}
        raise ImagegenError("config", f"Configuration file not found: {path}") from None
    except (OSError, tomllib.TOMLDecodeError):
        raise ImagegenError("config", f"Cannot read valid TOML configuration: {path}") from None


def validate_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                 and not parsed.username and not parsed.password
                 and not parsed.query and not parsed.fragment)
        parsed.port
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ImagegenError("config", "base_url must be an HTTP(S) URL without credentials, query or fragment.")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str = field(repr=False)
    model: str = "gpt-image-2"
    timeout: float = 300.0


def load_settings(*, path: Path | None = None, base_url: str | None = None,
                  model: str | None = None, timeout: float | None = None) -> Settings:
    cfg = read_toml(path or default_config_path(), required=path is not None)
    base = base_url or os.environ.get("CPA_IMAGEGEN_BASE_URL") or cfg.get("base_url")
    key = os.environ.get("CPA_IMAGEGEN_API_KEY") or cfg.get("api_key")
    if not key and cfg.get("api_key_env"):
        key = os.environ.get(cfg["api_key_env"])
    selected = model or os.environ.get("CPA_IMAGEGEN_MODEL") or cfg.get("model", "gpt-image-2")
    seconds = timeout if timeout is not None else cfg.get("timeout", 300.0)
    if not isinstance(base, str) or not base.strip() or not isinstance(key, str) or not key.strip():
        raise ImagegenError("config", "Configure CPA_IMAGEGEN_BASE_URL and CPA_IMAGEGEN_API_KEY, or import a private configuration. No default service is used.")
    if not isinstance(selected, str) or not selected.strip():
        raise ImagegenError("config", "model must be a non-empty string.")
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds <= 0:
        raise ImagegenError("config", "timeout must be a positive finite number of seconds.")
    return Settings(validate_url(base), key, selected.strip(), float(seconds))


def import_codex(source: Path, destination: Path, *, provider: str | None = None,
                 overwrite: bool = False) -> dict:
    cfg = read_toml(source, required=True)
    name = provider or cfg.get("model_provider")
    providers = cfg.get("model_providers", {})
    selected = providers.get(name) if isinstance(providers, dict) else None
    if not isinstance(selected, dict):
        raise ImagegenError("config", "Selected custom provider was not found in Codex configuration.")
    base = selected.get("base_url")
    if not isinstance(base, str):
        raise ImagegenError("config", "Selected provider has no base_url.")
    result = {"base_url": validate_url(base), "model": "gpt-image-2"}
    token = selected.get("experimental_bearer_token")
    env_key = selected.get("env_key")
    if isinstance(token, str) and token:
        result["api_key"] = token
    elif isinstance(env_key, str) and env_key:
        result["api_key_env"] = env_key
    else:
        raise ImagegenError("config", "Provider needs experimental_bearer_token or env_key. OAuth/auth.json credentials are not imported.")
    if destination.resolve() == source.resolve():
        raise ImagegenError("config", "Import destination must differ from the Codex source.")
    if destination.is_symlink():
        raise ImagegenError("config", "Private configuration destination must not be a symbolic link.")
    content = "# Private CPA Imagegen configuration. Do not commit.\n"
    content += "".join(f"{k} = {json.dumps(v, ensure_ascii=False)}\n" for k, v in result.items())
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if overwrite else os.O_EXCL)
        fd = os.open(destination, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError:
        raise ImagegenError("config", "Private configuration already exists; use --overwrite to replace it.") from None
    except OSError:
        raise ImagegenError("config", "Cannot write private configuration.") from None
    return {"config_path": str(destination.resolve()), "provider": name,
            "credential_source": "environment" if "api_key_env" in result else "private_file"}
