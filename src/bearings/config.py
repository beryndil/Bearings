from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Shorthand for the two knobs we expose for extended thinking:
#   - "adaptive": model decides how much to think (recommended default).
#   - "disabled": never emit thinking blocks.
# `None` means "don't pass anything", which falls through to the SDK's
# own default (currently: thinking off unless the model is configured for
# it). We default to "adaptive" so sessions show reasoning in the UI.
ThinkingMode = Literal["adaptive", "disabled"]


def _xdg(var: str, default: Path) -> Path:
    raw = os.environ.get(var)
    return Path(raw) if raw else default


CONFIG_HOME = _xdg("XDG_CONFIG_HOME", Path.home() / ".config") / "bearings"
DATA_HOME = _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / "bearings"


class ServerCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8787


class AuthCfg(BaseModel):
    enabled: bool = False
    token: str | None = None


class AgentCfg(BaseModel):
    working_dir: Path = Field(default_factory=lambda: Path.home())
    model: str = "claude-opus-4-7"
    # Extended-thinking control. "adaptive" lets Claude decide how much
    # to think per turn (minimal on simple prompts, deeper on complex
    # ones); "disabled" turns thinking off entirely; `None` skips the
    # flag so the SDK's own default applies. The Conversation view
    # renders the resulting thinking blocks in a collapsed `<details>`
    # next to each assistant turn.
    thinking: ThinkingMode | None = "adaptive"


class StorageCfg(BaseModel):
    db_path: Path = Field(default_factory=lambda: DATA_HOME / "db.sqlite")


class MetricsCfg(BaseModel):
    enabled: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BEARINGS_", extra="ignore")

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
