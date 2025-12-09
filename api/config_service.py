"""Configuration management service for dynamic model switching."""

import os
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Default configuration (can be overridden by environment variable DEFAULT_MODEL_CONFIG)
_DEFAULT_FALLBACK = "glm"
DEFAULT_CONFIG = os.getenv("DEFAULT_MODEL_CONFIG", _DEFAULT_FALLBACK)

@dataclass
class ModelConfig:
    """Configuration for a single model provider."""
    name: str
    description: str
    base_url: str
    auth_token_env: str  # Environment variable name for auth token
    timeout_ms: int = 600000
    model: Optional[str] = None
    small_fast_model: Optional[str] = None
    sonnet_model: Optional[str] = None
    opus_model: Optional[str] = None
    haiku_model: Optional[str] = None
    proxy_env: Optional[str] = None  # Environment variable name for proxy URL
    extra_env: Dict[str, str] = field(default_factory=dict)

    def get_auth_token(self) -> str:
        """Get auth token from environment variable."""
        return os.getenv(self.auth_token_env, "")

    def get_proxy_settings(self) -> Optional[Dict[str, str]]:
        """Get proxy settings from environment variable."""
        if not self.proxy_env:
            return None

        proxy_url = os.getenv(self.proxy_env)
        if not proxy_url:
            return None

        return {
            "https_proxy": proxy_url,
            "http_proxy": proxy_url
        }


# Predefined model configurations - NO SECRETS, only metadata
PREDEFINED_CONFIGS: Dict[str, ModelConfig] = {
    "glm": ModelConfig(
        name="glm",
        description="GLM-4 (智谱清言) 模型",
        base_url="https://open.bigmodel.cn/api/anthropic",
        auth_token_env="GLM_AUTH_TOKEN",
        timeout_ms=3000000,
        proxy_env=None,  # No proxy needed
        extra_env={"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    ),
    "claude-router": ModelConfig(
        name="claude-router",
        description="Claude Code Router (本地代理)",
        base_url="http://127.0.0.1:3456",
        auth_token_env="CLAUDE_ROUTER_AUTH_TOKEN",
        timeout_ms=600000,
        proxy_env="CLAUDE_ROUTER_PROXY",  # Read from environment variable
        extra_env={
            "DISABLE_TELEMETRY": "true",
            "DISABLE_COST_WARNINGS": "true"
        }
    ),
}

# Validate that the default config exists
if DEFAULT_CONFIG not in PREDEFINED_CONFIGS:
    logger.warning(
        f"Invalid DEFAULT_MODEL_CONFIG '{DEFAULT_CONFIG}' specified in environment. "
        f"Available configs: {list(PREDEFINED_CONFIGS.keys())}. "
        f"Falling back to '{_DEFAULT_FALLBACK}'"
    )
    DEFAULT_CONFIG = _DEFAULT_FALLBACK


class ConfigManager:
    """Manages runtime configuration for model providers."""

    _instance = None
    _current_config: str = DEFAULT_CONFIG  # Default from env or fallback

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._detect_current_config()
        logger.info(f"ConfigManager initialized with config: {self._current_config}")

    def _detect_current_config(self):
        """
        Apply the default configuration on initialization.
        This ensures environment variables and proxy settings are set.
        """
        # Apply the default configuration
        success = self.switch_config(self._current_config)
        if not success:
            logger.warning(f"Failed to apply default config {self._current_config}, environment may be incomplete")

    def get_current_config_name(self) -> str:
        """Get the name of the current active configuration."""
        return self._current_config

    def get_current_config(self) -> ModelConfig:
        """Get the current active configuration."""
        return PREDEFINED_CONFIGS.get(self._current_config, PREDEFINED_CONFIGS["claude-router"])

    def get_available_configs(self) -> List[Dict]:
        """Get list of all available configurations."""
        return [
            {
                "name": config.name,
                "description": config.description,
                "base_url": config.base_url,
                "is_active": config.name == self._current_config
            }
            for config in PREDEFINED_CONFIGS.values()
        ]

    def switch_config(self, config_name: str) -> bool:
        """
        Switch to a different configuration.

        This updates the environment variables in the current process.
        Note: For Claude SDK, changes take effect on the next query.
        """
        if config_name not in PREDEFINED_CONFIGS:
            logger.error(f"Unknown config: {config_name}")
            return False

        config = PREDEFINED_CONFIGS[config_name]
        auth_token = config.get_auth_token()

        if not auth_token:
            logger.error(f"Auth token not found for config: {config_name} (env: {config.auth_token_env})")
            return False

        # Update environment variables
        os.environ["ANTHROPIC_BASE_URL"] = config.base_url
        os.environ["ANTHROPIC_AUTH_TOKEN"] = auth_token
        os.environ["ANTHROPIC_API_KEY"] = auth_token  # Use same token for API_KEY
        os.environ["API_TIMEOUT_MS"] = str(config.timeout_ms)

        if config.model:
            os.environ["ANTHROPIC_MODEL"] = config.model
        else:
            os.environ.pop("ANTHROPIC_MODEL", None)

        if config.small_fast_model:
            os.environ["ANTHROPIC_SMALL_FAST_MODEL"] = config.small_fast_model
        else:
            os.environ.pop("ANTHROPIC_SMALL_FAST_MODEL", None)

        if config.sonnet_model:
            os.environ["ANTHROPIC_DEFAULT_SONNET_MODEL"] = config.sonnet_model
        else:
            os.environ.pop("ANTHROPIC_DEFAULT_SONNET_MODEL", None)

        if config.opus_model:
            os.environ["ANTHROPIC_DEFAULT_OPUS_MODEL"] = config.opus_model
        else:
            os.environ.pop("ANTHROPIC_DEFAULT_OPUS_MODEL", None)

        if config.haiku_model:
            os.environ["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = config.haiku_model
        else:
            os.environ.pop("ANTHROPIC_DEFAULT_HAIKU_MODEL", None)

        # Clear all proxy settings first (both lowercase and uppercase)
        proxy_keys = ["https_proxy", "http_proxy", "HTTPS_PROXY", "HTTP_PROXY", "no_proxy", "NO_PROXY"]
        for key in proxy_keys:
            os.environ.pop(key, None)

        # Apply proxy settings if configured (from environment variable)
        proxy_settings = config.get_proxy_settings()
        if proxy_settings:
            for key, value in proxy_settings.items():
                os.environ[key] = value
            logger.info(f"Applied proxy settings from {config.proxy_env}: {list(proxy_settings.keys())}")
        else:
            if config.proxy_env:
                logger.info(f"No proxy configured ({config.proxy_env} not set, using direct connection)")
            else:
                logger.info("No proxy configured (direct connection)")

        # Apply extra environment variables
        for key, value in config.extra_env.items():
            os.environ[key] = value

        self._current_config = config_name
        logger.info(f"Switched to config: {config_name} (base_url: {config.base_url})")
        return True

    def get_current_env_snapshot(self) -> Dict[str, str]:
        """Get a snapshot of the current relevant environment variables."""
        relevant_keys = [
            "ANTHROPIC_BASE_URL",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_SMALL_FAST_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "API_TIMEOUT_MS",
            "https_proxy",
            "http_proxy",
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "NO_PROXY",
            "no_proxy",
            "DISABLE_TELEMETRY",
            "DISABLE_COST_WARNINGS",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        ]
        return {
            key: os.getenv(key, "")
            for key in relevant_keys
            if os.getenv(key)
        }


# Global instance
config_manager = ConfigManager()
