# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import os
import sys
from functools import lru_cache
from pathlib import Path

from platformdirs import user_data_dir
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "JS8Link"


def _default_data_dir() -> Path:
    configured = os.environ.get("JS8LINK_DATA_DIR")
    if configured:
        return Path(configured).expanduser()
    if getattr(sys, "frozen", False):
        return Path(user_data_dir(APP_NAME, APP_NAME))
    return Path(__file__).resolve().parents[3] / "data"


def _default_frontend_dist() -> Path:
    configured = os.environ.get("JS8LINK_FRONTEND_DIST")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[3] / "frontend" / "dist"


class Settings(BaseSettings):
    data_dir: Path = _default_data_dir()
    host: str = "127.0.0.1"
    port: int = 8008
    js8_host: str = "127.0.0.1"
    js8_port: int = 2442
    session_secret: str = "change-me-in-production"
    frontend_dist: Path = _default_frontend_dist()

    model_config = SettingsConfigDict(env_file=".env", env_prefix="JS8LINK_", extra="ignore")

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{(self.data_dir / 'js8link.sqlite').absolute()}"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
