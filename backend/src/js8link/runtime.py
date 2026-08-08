# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
"""Standalone runtime launcher for the packaged JS8Link application."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import sqlite3
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, cast

import uvicorn
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from platformdirs import user_data_dir

from alembic import command

APP_NAME = "JS8Link"
logger = logging.getLogger(APP_NAME)


def resource_root() -> Path:
    """Return the read-only resource directory for source and frozen runs."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[3]


def default_data_dir() -> Path:
    """Return the per-user persistent data directory for a standalone run."""
    return Path(user_data_dir(APP_NAME, APP_NAME))


def configure_environment(
    *, data_dir: Path, host: str, port: int, frontend_dist: Path | None = None
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    if not os.access(data_dir, os.W_OK | os.X_OK):
        raise RuntimeError(f"Data directory is not writable: {data_dir}")
    (data_dir / "logs").mkdir(exist_ok=True)
    (data_dir / "backups").mkdir(exist_ok=True)
    os.environ["JS8LINK_DATA_DIR"] = str(data_dir)
    os.environ["JS8LINK_HOST"] = host
    os.environ["JS8LINK_PORT"] = str(port)
    if frontend_dist is not None:
        os.environ["JS8LINK_FRONTEND_DIST"] = str(frontend_dist)


def configure_logging(data_dir: Path) -> None:
    log_path = data_dir / "logs" / "js8link.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )
    logger.info("Starting %s %s on %s/%s", APP_NAME, _version(), sys.platform, _architecture())
    logger.info("Data directory: %s", data_dir)
    logger.info("Database: %s", data_dir / "js8link.sqlite")


def _version() -> str:
    version_path = resource_root() / "VERSION"
    return version_path.read_text(encoding="utf-8").strip() if version_path.exists() else "unknown"


def _architecture() -> str:
    return os.uname().machine if hasattr(os, "uname") else os.environ.get("PROCESSOR_ARCHITECTURE", "unknown")


def _migration_config() -> tuple[Config, Path]:
    root = resource_root()
    ini_path = root / "alembic.ini"
    migrations_path = root / "alembic"
    if not ini_path.exists() or not migrations_path.exists():
        raise RuntimeError("Bundled Alembic migration resources are missing")
    config = Config(str(ini_path))
    config.set_main_option("script_location", str(migrations_path))
    config.set_main_option("prepend_sys_path", str(root))
    database_path = Path(os.environ["JS8LINK_DATA_DIR"]) / "js8link.sqlite"
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.absolute()}")
    return config, migrations_path


def _migration_revisions(config: Config) -> tuple[str | None, str | None]:
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    database_path = Path(os.environ["JS8LINK_DATA_DIR"]) / "js8link.sqlite"
    if not database_path.exists():
        return None, head
    with sqlite3.connect(database_path) as connection:
        current = MigrationContext.configure(cast(Any, connection)).get_current_revision()
    return current, head


def _backup_database(database_path: Path, backup_dir: Path, old_revision: str | None, new_revision: str | None) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    old = old_revision or "unknown"
    new = new_revision or "unknown"
    destination = backup_dir / f"js8link-{old}-to-{new}-{stamp}.sqlite3"
    if destination.exists():
        raise RuntimeError(f"Refusing to overwrite existing database backup: {destination}")
    source = sqlite3.connect(database_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        target.commit()
        check = target.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise RuntimeError(f"Database backup integrity check failed: {destination}")
    except Exception as error:
        target.close()
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Could not create database backup: {error}") from error
    finally:
        source.close()
        target.close()
    logger.info("Created database backup before migration: %s", destination)
    return destination


def ensure_port_available(host: str, port: int) -> None:
    try:
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, port))
    except OSError as error:
        raise RuntimeError(
            f"JS8Link cannot start because TCP port {port} is already in use or unavailable: {error}"
        ) from error


def run_migrations() -> None:
    config, _ = _migration_config()
    current, head = _migration_revisions(config)
    database_path = Path(os.environ["JS8LINK_DATA_DIR"]) / "js8link.sqlite"
    if database_path.exists() and current != head:
        _backup_database(database_path, Path(os.environ["JS8LINK_DATA_DIR"]) / "backups", current, head)
    logger.info("Alembic migration state: current=%s head=%s", current or "none", head or "none")
    try:
        command.upgrade(config, "head")
    except Exception:
        logger.exception("Alembic migration failed; any backup was retained")
        raise RuntimeError("Database migration failed; see the log and the retained backup") from None


async def serve(host: str, port: int, open_browser: bool) -> None:
    # Import only after environment and data paths have been configured. The
    # application creates its SQLAlchemy engine during module import.
    from js8link.app import app

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    task = asyncio.create_task(_serve_server(server))
    deadline = time.monotonic() + 15
    while not server.started and not task.done():
        if time.monotonic() > deadline:
            server.should_exit = True
            await task
            raise RuntimeError(f"Uvicorn did not start on http://{host}:{port}")
        await asyncio.sleep(0.05)
    if task.done():
        error = task.result()
        if error is not None:
            raise RuntimeError(f"Could not start Uvicorn on http://{host}:{port}: {error}") from error
        raise RuntimeError(f"Uvicorn stopped before starting on http://{host}:{port}")
    if open_browser:
        webbrowser.open(f"http://{host}:{port}")
    await task


async def _serve_server(server: uvicorn.Server) -> BaseException | None:
    try:
        await server.serve()
    except BaseException as error:
        return error
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the JS8Link standalone application")
    parser.add_argument("--data-dir", type=Path, help="Persistent data directory")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address")
    parser.add_argument("--port", type=int, default=8008, help="HTTP port")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the default browser")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise RuntimeError("Port must be between 1 and 65535")
    data_dir = (args.data_dir or default_data_dir()).expanduser().resolve()
    frontend_dist = resource_root() / "frontend" / "dist"
    if not (frontend_dist / "index.html").exists():
        raise RuntimeError(f"Bundled frontend is missing: {frontend_dist / 'index.html'}")
    configure_environment(
        data_dir=data_dir,
        host=args.host,
        port=args.port,
        frontend_dist=frontend_dist,
    )
    configure_logging(data_dir)
    ensure_port_available(args.host, args.port)
    run_migrations()
    asyncio.run(serve(args.host, args.port, not args.no_browser))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        print(f"JS8Link could not start: {error}", file=sys.stderr)
        if sys.stdin.isatty():
            input("Press Enter to close…")
        raise SystemExit(1) from error
