import hashlib
import json

import pytest
from PIL import Image

from cpa_imagegen.cli import main
from cpa_imagegen.errors import ImagegenError
from cpa_imagegen.processing import resize_image


def test_padding_preserves_content_and_original(tmp_path):
    source = tmp_path / "原始 图片.png"
    Image.new("RGB", (12, 6), "red").save(source)
    before = hashlib.sha256(source.read_bytes()).digest()
    out = tmp_path / "子目录" / "正方形.png"
    result = resize_image(source, out, size="12x12", mode="pad")
    assert (result["source_width"], result["source_height"]) == (12, 6)
    assert result["local_processing"] and result["path"] == str(out.resolve())
    with Image.open(out) as image:
        assert image.size == (12, 12)
        assert image.getpixel((6, 0))[3] == 0
        assert image.getpixel((6, 3)) == (255, 0, 0, 255)
        assert image.getpixel((6, 8)) == (255, 0, 0, 255)
        assert image.getpixel((6, 9))[3] == 0
    assert hashlib.sha256(source.read_bytes()).digest() == before


def test_crop_centers_and_removes_only_edges(tmp_path):
    source = tmp_path / "source.png"
    image = Image.new("RGB", (12, 6), "red")
    image.paste("green", (3, 0, 9, 6))
    image.save(source)
    out = tmp_path / "cropped.png"
    resize_image(source, out, size="6x6", mode="crop")
    with Image.open(out) as image:
        assert image.size == (6, 6)
        assert {image.getpixel((x, y)) for x in range(6) for y in range(6)} == {(0, 128, 0, 255)}


def test_resize_cli_works_without_config_or_network(tmp_path, monkeypatch, capsys):
    import httpx
    def no_network(*args, **kwargs):
        pytest.fail("Local resize must never make an HTTP request")
    monkeypatch.setattr(httpx.Client, "send", no_network)
    source, out = tmp_path / "original.png", tmp_path / "adjusted.png"
    Image.new("RGBA", (8, 4), (0, 255, 0, 128)).save(source)
    assert main(["resize", "--image", str(source), "--out", str(out),
                 "--size", "16x16", "--mode", "pad", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["local_processing"] and result["operation"] == "resize"
    with Image.open(out) as image:
        assert image.size == (16, 16) and image.getpixel((8, 8))[3] == 128


@pytest.mark.parametrize("case", ["same_file", "existing", "auto", "huge", "invalid_image", "bad_mode", "bad_format"])
def test_resize_rejects_invalid_inputs_without_changing_files(tmp_path, case):
    source, out = tmp_path / "source.png", tmp_path / "out.png"
    Image.new("RGB", (8, 4), "blue").save(source)
    original = source.read_bytes()
    size, mode, overwrite = "16x16", "pad", False
    if case == "same_file": out, overwrite = source, True
    elif case == "existing": out.write_bytes(b"keep this")
    elif case == "auto": size = "auto"
    elif case == "huge": size = "999999x999999"
    elif case == "invalid_image": source.write_bytes(b"invalid")
    elif case == "bad_mode": mode = "stretch"
    elif case == "bad_format": out = tmp_path / "out.jpg"
    with pytest.raises(ImagegenError):
        resize_image(source, out, size=size, mode=mode, overwrite=overwrite)
    if case != "invalid_image": assert source.read_bytes() == original
    if case == "existing": assert out.read_bytes() == b"keep this"
    elif case != "same_file": assert not out.exists()


def test_resize_explicit_overwrite(tmp_path):
    source, out = tmp_path / "source.png", tmp_path / "out.png"
    Image.new("RGB", (8, 4), "blue").save(source)
    out.write_bytes(b"old")
    resize_image(source, out, size="4x4", mode="crop", overwrite=True)
    with Image.open(out) as image:
        assert image.size == (4, 4)


def test_resize_uses_displayed_exif_orientation(tmp_path):
    source, out = tmp_path / "camera.jpg", tmp_path / "out.png"
    image = Image.new("RGB", (8, 4), "red")
    exif = image.getexif()
    exif[274] = 6  # Display rotated 90 degrees clockwise.
    image.save(source, exif=exif)
    result = resize_image(source, out, size="8x8", mode="pad")
    assert (result["source_width"], result["source_height"]) == (4, 8)
    with Image.open(out) as image:
        assert image.getpixel((0, 4))[3] == 0
        assert image.getpixel((4, 0))[3] == 255
