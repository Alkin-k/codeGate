"""Configuration management for CodeGate."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass
class ModelConfig:
    """LLM model configuration for each agent role."""

    spec_model: str = "deepseek/deepseek-chat"
    exec_model: str = "deepseek/deepseek-chat"
    review_model: str = "deepseek/deepseek-chat"
    gate_model: str = "deepseek/deepseek-chat"
    eval_model: str = "deepseek/deepseek-chat"


@dataclass
class Config:
    """Global configuration for CodeGate."""

    models: ModelConfig = field(default_factory=ModelConfig)
    store_dir: Path = Path("./artifacts")
    max_clarify_rounds: int = 3
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env_path: str | Path | None = None) -> Config:
        """Load configuration from environment variables / .env file."""
        if env_path:
            load_dotenv(env_path)
        else:
            # Try .env in current directory, then project root
            load_dotenv(".env")

        models = ModelConfig(
            spec_model=os.getenv("CODEGATE_SPEC_MODEL", "deepseek/deepseek-chat"),
            exec_model=os.getenv("CODEGATE_EXEC_MODEL", "deepseek/deepseek-chat"),
            review_model=os.getenv("CODEGATE_REVIEW_MODEL", "deepseek/deepseek-chat"),
            gate_model=os.getenv("CODEGATE_GATE_MODEL", "deepseek/deepseek-chat"),
            eval_model=os.getenv("CODEGATE_EVAL_MODEL", "deepseek/deepseek-chat"),
        )

        store_dir = Path(os.getenv("CODEGATE_STORE_DIR", "./artifacts"))
        max_clarify_rounds = int(os.getenv("CODEGATE_MAX_CLARIFY_ROUNDS", "3"))
        log_level = os.getenv("CODEGATE_LOG_LEVEL", "INFO")

        return cls(
            models=models,
            store_dir=store_dir,
            max_clarify_rounds=max_clarify_rounds,
            log_level=log_level,
        )


# Global config singleton
_config: Config | None = None


def get_config() -> Config:
    """Get or initialize the global configuration."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def init_config(env_path: str | Path | None = None) -> Config:
    """Initialize the global configuration from a specific env file."""
    global _config
    _config = Config.from_env(env_path)
    return _config
