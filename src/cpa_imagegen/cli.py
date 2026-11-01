"""Human and machine-facing command line interface."""

import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__
from .config import default_config_path, import_codex, load_settings
from .core import ImageJob, ImageService
from .errors import ImagegenError, redact


def common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, help="Private TOML configuration path")
    parser.add_argument("--json", action="store_true", help="Emit JSON on stdout, including errors")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cpa-imagegen", description="Generate and edit images through an explicitly configured gateway.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    for action in ("generate", "edit", "doctor"):
        command = commands.add_parser(action)
        common(command)
        command.add_argument("--base-url")
        command.add_argument("--model")
        command.add_argument("--timeout", type=float)
        if action != "doctor":
            prompt = command.add_mutually_exclusive_group(required=True)
            prompt.add_argument("--prompt")
            prompt.add_argument("--prompt-file", type=Path)
            command.add_argument("--size", default="1024x1024")
            command.add_argument("--quality", default="medium")
            command.add_argument("--out", type=Path, required=True)
            command.add_argument("--overwrite", action="store_true")
            command.add_argument("--dry-run", action="store_true")
            if action == "edit":
                command.add_argument("--image", type=Path, action="append", required=True)
    config = commands.add_parser("config")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    importer = config_commands.add_parser("import-codex")
    common(importer)
    importer.add_argument("--codex-config", type=Path)
    importer.add_argument("--provider")
    importer.add_argument("--overwrite", action="store_true")
    installer = commands.add_parser("install-skill")
    common(installer)
    installer.add_argument("--agent", choices=["codex"], required=True)
    installer.add_argument("--dest", type=Path, help="Skill folder; must not already exist")
    return root


def emit(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    elif "path" in result and not result.get("dry_run"):
        print(f"Saved: {result['path']}")
        for warning in result.get("warnings", []):
            print(f"Warning: {warning}", file=sys.stderr)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    # Windows pipes may otherwise use the legacy system code page, corrupting
    # JSON paths consumed by an agent. Console output also accepts UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    secret = os.environ.get("CPA_IMAGEGEN_API_KEY", "")
    try:
        if args.command == "config":
            codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
            result = import_codex(args.codex_config or codex_home / "config.toml",
                                  args.config or default_config_path(), provider=args.provider,
                                  overwrite=args.overwrite)
        elif args.command == "install-skill":
            from .skill import install_skill
            result = install_skill(args.dest)
        else:
            settings = load_settings(path=args.config, base_url=args.base_url,
                                     model=args.model, timeout=args.timeout)
            secret = settings.api_key
            service = ImageService(settings)
            if args.command == "doctor":
                result = service.doctor()
            else:
                try:
                    prompt = args.prompt if args.prompt is not None else args.prompt_file.read_text(encoding="utf-8-sig")
                except (OSError, UnicodeError):
                    raise ImagegenError("input", "Cannot read UTF-8 prompt file.") from None
                job = ImageJob(prompt, args.out.expanduser(), args.size, args.quality,
                               tuple(p.expanduser() for p in getattr(args, "image", [])), args.overwrite)
                result = service.run(job, edit=args.command == "edit", dry_run=args.dry_run)
        emit(result, args.json)
        return 0
    except ImagegenError as exc:
        result = {"error": {"category": exc.category, "message": redact(str(exc), secret),
                            "request_id": redact(exc.request_id, secret) if exc.request_id else None}}
        if args.json:
            emit(result, True)
        else:
            print(f"{exc.category}: {result['error']['message']}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, AttributeError):
        message = {"error": {"category": "runtime", "message": "Invalid configuration, response or local filesystem operation. No automatic retry was performed."}}
        if args.json:
            emit(message, True)
        else:
            print(message["error"]["message"], file=sys.stderr)
        return 1
