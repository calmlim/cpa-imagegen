import base64
import json
from pathlib import Path

import httpx
from PIL import Image
import pytest

from cpa_imagegen.core import ImageJob, ImageService
from cpa_imagegen.errors import ImagegenError


def image_response(png, **extra):
    return httpx.Response(200, json={"created": 1, "data": [{"b64_json": base64.b64encode(png).decode()}], **extra}, headers={"x-request-id": "req-test"})


def test_generate_and_metadata(settings, png, tmp_path):
    requests = []
    def handler(request):
        requests.append(request)
        assert request.url.path == "/v1/images/generations"
        body = json.loads(request.content)
        assert body["model"] == "gpt-image-2"
        assert body["output_format"] == "png" and body["n"] == 1
        assert request.headers["authorization"] == "Bearer " + settings.api_key
        return image_response(png, model="upstream-model", usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3})
    service = ImageService(settings, transport=httpx.MockTransport(handler))
    out = tmp_path / "中文 路径" / "图片.png"
    result = service.run(ImageJob("画一个杯子", out))
    assert len(requests) == 1
    assert result["path"] == str(out.resolve())
    assert (result["width"], result["height"]) == (24, 16)
    assert result["model"] == "upstream-model" and result["model_source"] == "upstream"
    assert result["request_id"] == "req-test"
    assert result["usage"]["total_tokens"] == 3
    assert result["requested_size"] == "1024x1024"
    assert result["size_matches_request"] is False and result["warnings"]
    assert "b64_json" not in json.dumps(result)
    with Image.open(out) as image:
        assert image.format == "PNG"


def test_edit_multipart_multiple_files(settings, png, tmp_path):
    first, second = tmp_path / "输入 1.png", tmp_path / "输入 2.png"
    first.write_bytes(png)
    second.write_bytes(png)
    def handler(request):
        assert request.url.path == "/v1/images/edits"
        assert "multipart/form-data" in request.headers["content-type"]
        assert request.content.count(b'name="image[]"') == 2
        assert png in request.content
        return image_response(png)
    service = ImageService(settings, transport=httpx.MockTransport(handler))
    result = service.run(ImageJob("change background", tmp_path / "edited.png", images=(first, second)), edit=True)
    assert result["model_source"] == "requested"


def test_url_download_and_redirect_never_forward_gateway_auth(settings, png, tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": "https://images.invalid/signed?token=private"}]})
        assert "authorization" not in request.headers
        if request.url.host == "images.invalid":
            return httpx.Response(302, headers={"location": "https://cdn.invalid/result.png"})
        return httpx.Response(200, content=png)
    result = ImageService(settings, transport=httpx.MockTransport(handler)).run(ImageJob("test", tmp_path / "out.png"))
    assert len(calls) == 3 and Path(result["path"]).is_file()
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("status,category", [(401, "authentication"), (403, "authentication"), (429, "rate_limit"), (500, "upstream"), (503, "upstream")])
def test_api_errors_redacted_and_not_retried(settings, tmp_path, status, category):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": f"bad {settings.api_key} https://host.invalid/?token=hidden", "type": "test_error"}}, headers={"x-request-id": "req-error"})
    with pytest.raises(ImagegenError) as error:
        ImageService(settings, transport=httpx.MockTransport(handler)).run(ImageJob("test", tmp_path / "out.png"))
    assert len(calls) == 1
    assert error.value.category == category
    assert error.value.request_id == "req-error"
    assert settings.api_key not in str(error.value) and "hidden" not in str(error.value)


@pytest.mark.parametrize("kind,category", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection")])
def test_transport_errors_not_retried(settings, tmp_path, kind, category):
    calls = []
    def handler(request):
        calls.append(request)
        raise kind("simulated failure", request=request)
    with pytest.raises(ImagegenError) as error:
        ImageService(settings, transport=httpx.MockTransport(handler)).run(ImageJob("test", tmp_path / "out.png"))
    assert error.value.category == category and len(calls) == 1


@pytest.mark.parametrize("data", [[], [None], [{}], [{"b64_json": "not-base64"}], [{"b64_json": "bm90IGFuIGltYWdl"}]])
def test_empty_or_corrupt_response(settings, tmp_path, data):
    service = ImageService(settings, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": data})))
    with pytest.raises(ImagegenError) as error:
        service.run(ImageJob("test", tmp_path / "out.png"))
    assert error.value.category == "response" and not (tmp_path / "out.png").exists()


def test_download_failure_does_not_repeat_generation(settings, tmp_path):
    methods = []
    def handler(request):
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": "https://cdn.invalid/result"}]})
        return httpx.Response(403)
    with pytest.raises(ImagegenError) as error:
        ImageService(settings, transport=httpx.MockTransport(handler)).run(ImageJob("test", tmp_path / "out.png"))
    assert error.value.category == "download" and methods == ["POST", "GET"]


def test_preflight_dry_run_and_overwrite(settings, png, tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return image_response(png)
    service = ImageService(settings, transport=httpx.MockTransport(handler))
    out = tmp_path / "subdir" / "image.png"
    result = service.run(ImageJob("test", out), dry_run=True)
    assert result["dry_run"] and not calls and not out.parent.exists()
    out.parent.mkdir()
    out.write_bytes(b"original")
    with pytest.raises(ImagegenError, match="already exists"):
        service.run(ImageJob("test", out))
    assert not calls and out.read_bytes() == b"original"
    service.run(ImageJob("test", out, overwrite=True))
    assert len(calls) == 1 and out.read_bytes() == png


@pytest.mark.parametrize("case", ["empty_prompt", "bad_size", "bad_format", "bad_image", "missing_image", "same_file"])
def test_invalid_inputs_prevent_request(settings, png, tmp_path, case):
    source = tmp_path / "source.png"
    source.write_bytes(png if case != "bad_image" else b"invalid")
    job = ImageJob("test", tmp_path / "out.png")
    edit = False
    if case == "empty_prompt": job.prompt = " "
    elif case == "bad_size": job.size = "0x12"
    elif case == "bad_format": job.out = tmp_path / "out.jpg"
    elif case == "bad_image": job.images = (source,)
    elif case == "missing_image": edit = True
    elif case == "same_file": job.images, job.out, job.overwrite = (source,), source, True
    def handler(request):
        pytest.fail("Invalid input must not reach the network")
    with pytest.raises(ImagegenError):
        ImageService(settings, transport=httpx.MockTransport(handler)).run(job, edit=edit)


@pytest.mark.parametrize("status", [200, 404, 405])
def test_doctor_does_not_claim_generation(settings, status):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path == "/v1/models"
        return httpx.Response(status, json={"data": [{"id": "gpt-image-2"}]})
    result = ImageService(settings, transport=httpx.MockTransport(handler)).doctor()
    assert result["gateway_reachable"] and not result["image_generation_verified"]
    assert result["model_listed"] is (True if status == 200 else None)
    assert len(calls) == 1


@pytest.mark.parametrize("size,expected", [("24x16", True), ("auto", None)])
def test_dimension_reporting(settings, png, tmp_path, size, expected):
    service = ImageService(settings, transport=httpx.MockTransport(lambda r: image_response(png)))
    result = service.run(ImageJob("test", tmp_path / "out.png", size=size))
    assert result["size_matches_request"] is expected and not result["warnings"]
