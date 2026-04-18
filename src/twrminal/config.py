from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _xdg(var: str, default: Path) -> Path:
    raw = os.environ.get(var)
    return Path(raw) if raw else default


CONFIG_HOME = _xdg("XDG_CONFIG_HOME", Path.home() / ".config") / "twrminal"
DATA_HOME = _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / "twrminal"


class ServerCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8787


class AuthCfg(BaseModel):
    enabled: bool = False


class AgentCfg(BaseModel):
    working_dir: Path = Field(default_factory=lambda: Path.home())
    model: str = "claude-opus-4-7"


class StorageCfg(BaseModel):
    db_path: Path = Field(default_factory=lambda: DATA_HOME / "db.sqlite")


class MetricsCfg(BaseModel):
    enabled: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TWRMINAL_", extra="ignore")

    server: ServerCfg = Field(default_factory=ServerCfg)
    auth: AuthCfg = Field(default_factory=AuthCfg)
    agent: AgentCfg = Field(default_factory=AgentCfg)
    storage: StorageCfg = Field(default_factory=StorageCfg)
    metrics: MetricsCfg = Field(default_factory=MetricsCfg)

    config_file: Path = Field(default_factory=lambda: CONFIG_HOME / "config.toml")

    def ensure_paths(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.storage.db_path.parent.mkdir(parents=True, exist_ok=True)


def load_settings(config_file: Path | None = None) -> Settings:
    path = config_file or CONFIG_HOME / "config.toml"
    data: dict[str, Any] = {}
    if path.exists():
        data = tomllib.loads(path.read_text())
    settings = Settings(**data)
    settings.config_file = path
    return settings
