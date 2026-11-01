import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig

from cpa_imagegen.cli import main


def test_cli_json_dry_run_and_unicode_prompt(tmp_path, capsys):
    config = tmp_path / "private.toml"
    config.write_text('base_url="https://gateway.invalid/v1"\napi_key="dont-print-this"\n')
    prompt = tmp_path / "提示词 空格.txt"
    prompt.write_text("生成一个杯子", encoding="utf-8-sig")
    out = tmp_path / "输出 图片.png"
    assert main(["generate", "--config", str(config), "--prompt-file", str(prompt), "--out", str(out), "--model", "arbitrary-compatible-model", "--dry-run", "--json"]) == 0
    stdout = capsys.readouterr().out
    result = json.loads(stdout)
    assert result["request"]["prompt"] == "生成一个杯子"
    assert result["request"]["model"] == "arbitrary-compatible-model"
    assert "dont-print-this" not in stdout and not out.exists()


def test_cli_missing_configuration_json(capsys):
    assert main(["doctor", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["category"] == "config"


def test_entrypoints_installed():
    python = subprocess.run([sys.executable, "-m", "cpa_imagegen", "--version"], capture_output=True, text=True)
    assert python.returncode == 0 and python.stdout.strip() == "0.1.0"
    script = Path(sysconfig.get_path("scripts")) / ("cpa-imagegen.exe" if os.name == "nt" else "cpa-imagegen")
    result = subprocess.run([str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "import" not in result.stderr
    assert "generate" in result.stdout and "doctor" in result.stdout


def test_piped_json_is_utf8_even_with_legacy_windows_encoding(tmp_path):
    config = tmp_path / "配置 文件.toml"
    config.write_text('base_url="https://gateway.invalid/v1"\napi_key="test-key"\n')
    out = tmp_path / "图片 中文.png"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "ascii"
    result = subprocess.run([sys.executable, "-m", "cpa_imagegen", "generate", "--config", str(config), "--prompt", "咖啡杯", "--out", str(out), "--dry-run", "--json"], env=env, capture_output=True)
    assert result.returncode == 0
    parsed = json.loads(result.stdout.decode("utf-8"))
    assert parsed["path"] == str(out.resolve()) and parsed["request"]["prompt"] == "咖啡杯"
