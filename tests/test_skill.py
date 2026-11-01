from pathlib import Path
import sys

import pytest

from cpa_imagegen.cli import main
from cpa_imagegen.errors import ImagegenError
from cpa_imagegen.skill import install_skill


def test_install_binds_runtime_without_network_or_configuration(tmp_path):
    destination = tmp_path / "技能 空格" / "cpa-imagegen"
    result = install_skill(destination)
    assert result["python"] == str(Path(sys.executable).absolute())
    assert result["skill_path"] == str(destination)
    text = (destination / "SKILL.md").read_text(encoding="utf-8")
    assert str(Path(sys.executable).absolute()).replace("'", "''") in text
    assert "{{CLI_COMMAND}}" not in text and "{{SHELL}}" not in text
    original = (destination / "SKILL.md").read_bytes()
    with pytest.raises(ImagegenError, match="not overwritten"):
        install_skill(destination)
    assert (destination / "SKILL.md").read_bytes() == original
    assert (destination / "agents" / "openai.yaml").is_file()


def test_default_install_uses_explicit_codex_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert Path(install_skill()["skill_path"]) == tmp_path / "skills" / "cpa-imagegen"


def test_installer_cli_json(tmp_path, capsys):
    args = ["install-skill", "--agent", "codex", "--dest", str(tmp_path / "skill"), "--json"]
    assert main(args) == 0
    assert '"agent": "codex"' in capsys.readouterr().out
    assert main(args) == 1
    assert '"category": "install"' in capsys.readouterr().out
