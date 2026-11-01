import json
import os
from pathlib import Path
import subprocess
import sys

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
    script = Path(sys.executable).parent / ("cpa-imagegen.exe" if os.name == "nt" else "cpa-imagegen")
    result = subprocess.run([str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "import" not in result.stderr
    assert "generate" in result.stdout and "doctor" in result.stdout
