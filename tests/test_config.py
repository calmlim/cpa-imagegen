import os
from pathlib import Path
import tomllib

import pytest

from cpa_imagegen.config import import_codex, load_settings
from cpa_imagegen.errors import ImagegenError


def test_priority_and_no_implicit_codex(tmp_path, monkeypatch):
    cfg = tmp_path / "private.toml"
    cfg.write_text('base_url="https://file.invalid/v1"\napi_key="file-key"\nmodel="file-model"\ntimeout=42\n')
    assert load_settings(path=cfg).timeout == 42
    monkeypatch.setenv("CPA_IMAGEGEN_BASE_URL", "https://env.invalid/v1")
    monkeypatch.setenv("CPA_IMAGEGEN_API_KEY", "env-key")
    monkeypatch.setenv("CPA_IMAGEGEN_MODEL", "env-model")
    settings = load_settings(path=cfg)
    assert settings.base_url == "https://env.invalid/v1"
    assert settings.api_key == "env-key"
    assert settings.model == "env-model"
    settings = load_settings(path=cfg, base_url="https://cli.invalid/v1/", model="custom-image", timeout=10)
    assert (settings.base_url, settings.model, settings.timeout) == ("https://cli.invalid/v1", "custom-image", 10)
    assert "env-key" not in repr(settings)


def test_missing_config_never_uses_openai_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-use")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://wrong.invalid")
    with pytest.raises(ImagegenError, match="No default service"):
        load_settings()


@pytest.mark.parametrize("base", ["", "ftp://host", "https://key:secret@host", "https://host/?key=secret", "https://host/#fragment", "https://host:bad"])
def test_invalid_base_url(base, monkeypatch):
    monkeypatch.setenv("CPA_IMAGEGEN_BASE_URL", base)
    monkeypatch.setenv("CPA_IMAGEGEN_API_KEY", "test-key")
    with pytest.raises(ImagegenError):
        load_settings()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_timeout(timeout, monkeypatch):
    monkeypatch.setenv("CPA_IMAGEGEN_BASE_URL", "https://host/v1")
    monkeypatch.setenv("CPA_IMAGEGEN_API_KEY", "test-key")
    with pytest.raises(ImagegenError, match="timeout"):
        load_settings(timeout=timeout)


def test_import_only_selected_fields_and_prevent_overwrite(tmp_path):
    source = tmp_path / "Codex 私人配置.toml"
    source.write_text('model_provider="custom"\nmodel="text-model"\n[model_providers.custom]\nbase_url="https://gateway.invalid/v1"\nexperimental_bearer_token="test-secret"\nnotify=["private-command"]\n[projects.private]\ntrust_level="trusted"\n', encoding="utf-8")
    target = tmp_path / "private" / "config.toml"
    result = import_codex(source, target)
    assert result["provider"] == "custom"
    data = tomllib.loads(target.read_text(encoding="utf-8"))
    assert data == {"base_url": "https://gateway.invalid/v1", "model": "gpt-image-2", "api_key": "test-secret"}
    assert "test-secret" not in str(result)
    with pytest.raises(ImagegenError, match="already exists"):
        import_codex(source, target)
    import_codex(source, target, overwrite=True)
    if os.name != "nt":
        assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ImagegenError, match="differ"):
        import_codex(source, source, overwrite=True)


def test_import_env_reference_and_explicit_provider(tmp_path, monkeypatch):
    source = tmp_path / "codex.toml"
    source.write_text('[model_providers.alt]\nbase_url="http://localhost:8317/v1"\nenv_key="MY_CPA_KEY"\n')
    target = tmp_path / "out.toml"
    import_codex(source, target, provider="alt")
    assert 'api_key_env = "MY_CPA_KEY"' in target.read_text()
    monkeypatch.setenv("MY_CPA_KEY", "local-test-key")
    assert load_settings(path=target).api_key == "local-test-key"


@pytest.mark.parametrize("content", ["invalid = [", "model_provider='missing'", "[model_providers.x]\nbase_url='https://gateway.invalid'\nrequires_openai_auth=true"])
def test_invalid_import(tmp_path, content):
    source = tmp_path / "source.toml"
    source.write_text(content)
    with pytest.raises(ImagegenError):
        import_codex(source, tmp_path / "target.toml", provider="x")
