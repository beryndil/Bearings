from __future__ import annotations

import argparse
from collections.abc import Sequence

from twrminal import __version__
from twrminal.config import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="twrminal")
    parser.add_argument("--version", action="version", version=f"twrminal {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Run the FastAPI server")
    sub.add_parser("init", help="Initialize config + database on disk")

    send = sub.add_parser("send", help="Send a one-shot prompt to an agent session")
    send.add_argument("--session", required=True, help="Session id")
    send.add_argument("message", help="Prompt text")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "serve":
        import uvicorn

        cfg = load_settings()
        uvicorn.run(
            "twrminal.server:create_app",
            factory=True,
            host=cfg.server.host,
            port=cfg.server.port,
            log_level="info",
        )
        return 0

    if args.command == "init":
        cfg = load_settings()
        cfg.ensure_paths()
        print(f"config ready at {cfg.config_file}")
        print(f"database path {cfg.storage.db_path}")
        return 0

    if args.command == "send":
        raise SystemExit("send is not implemented in v0.1.0 — see TODO.md")

    return 1
