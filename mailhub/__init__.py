"""Local, MCP-first personal-operations hub."""

from .config import Account, Config, ConfigError, load_config

__version__ = "0.1.4"

__all__ = ["Account", "Config", "ConfigError", "load_config", "__version__"]
