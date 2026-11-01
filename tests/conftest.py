from io import BytesIO

from PIL import Image
import pytest

from cpa_imagegen.config import Settings


@pytest.fixture(autouse=True)
def isolate_configuration(monkeypatch, tmp_path):
    for name in ("CPA_IMAGEGEN_BASE_URL", "CPA_IMAGEGEN_API_KEY", "CPA_IMAGEGEN_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("cpa_imagegen.config.default_config_path", lambda: tmp_path / "private.toml")


@pytest.fixture
def settings():
    return Settings("https://gateway.invalid/v1", "private-test-credential")


@pytest.fixture
def png():
    stream = BytesIO()
    Image.new("RGB", (24, 16), "coral").save(stream, "PNG")
    return stream.getvalue()
