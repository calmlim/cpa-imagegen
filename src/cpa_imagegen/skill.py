"""Install a portable skill template bound to this Python environment."""

from importlib.resources import files
import os
from pathlib import Path
import shlex
import sys

from .errors import ImagegenError


def install_skill(destination: Path | None = None) -> dict:
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    destination = (destination or home / "skills" / "cpa-imagegen").expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise ImagegenError("install", "Skill destination already exists. It was not overwritten; choose --dest or remove the old installation explicitly.")
    python = str(Path(sys.executable).absolute())
    if os.name == "nt":
        command = "& '" + python.replace("'", "''") + "' -m cpa_imagegen"
        shell = "PowerShell"
    else:
        command = shlex.quote(python) + " -m cpa_imagegen"
        shell = "POSIX shell"
    source = files("cpa_imagegen").joinpath("data", "skill")
    try:
        destination.mkdir(parents=True, exist_ok=False)
        text = source.joinpath("SKILL.md").read_text(encoding="utf-8")
        text = text.replace("{{CLI_COMMAND}}", command).replace("{{SHELL}}", shell)
        (destination / "SKILL.md").write_text(text, encoding="utf-8", newline="\n")
        (destination / "agents").mkdir()
        metadata = source.joinpath("agents", "openai.yaml").read_text(encoding="utf-8")
        (destination / "agents" / "openai.yaml").write_text(metadata, encoding="utf-8", newline="\n")
    except OSError:
        raise ImagegenError("install", "Cannot install skill. Check destination permissions; a partial installation may need to be removed before retrying.") from None
    return {"skill_path": str(destination), "python": python,
            "agent": "codex", "restart_hint": "Start a new chat; restart Codex if the skill is not discovered."}
