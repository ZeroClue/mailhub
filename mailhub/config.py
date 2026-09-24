"""Configuration models and XDG-aware TOML loading for Mailhub."""

from __future__ import annotations

import os
import stat
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when Mailhub configuration is missing or invalid."""


PROVIDER_CAPABILITIES: dict[str, frozenset[str]] = {
    "gmail": frozenset({"mail", "calendar", "contacts"}),
    "graph": frozenset({"mail", "calendar", "contacts", "tasks"}),
    "imap": frozenset({"mail"}),
    "caldav": frozenset({"calendar", "tasks"}),
    "carddav": frozenset({"contacts"}),
}


@dataclass(frozen=True)
class Account:
    """A named provider account and the capabilities it exposes."""

    alias: str
    provider: str
    capabilities: frozenset[str]


@dataclass(frozen=True)
class Config:
    """Validated account registry."""

    accounts: tuple[Account, ...]
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def account(self, alias: str) -> Account:
        for account in self.accounts:
            if account.alias == alias:
                return account
        raise ConfigError(f"unknown account alias: {alias}")

    def provider_config(self, provider: str, alias: str | None = None) -> dict[str, str]:
        """Get client_id and client_secret for a provider (optionally for a specific account)."""
        # First check account-level config if alias provided
        if alias:
            account_raw = self._raw.get("accounts", {}).get(alias, {})
            if account_raw.get("client_id") or account_raw.get("client_secret"):
                return {
                    "client_id": account_raw.get("client_id", ""),
                    "client_secret": account_raw.get("client_secret", ""),
                }
        
        # Fall back to provider-level config
        raw_provider = self._raw.get(provider, {})
        return {
            "client_id": raw_provider.get("client_id", ""),
            "client_secret": raw_provider.get("client_secret", ""),
        }

    def status(self) -> list[dict[str, object]]:
        return [
            {
                "alias": account.alias,
                "provider": account.provider,
                "capabilities": sorted(account.capabilities),
            }
            for account in self.accounts
        ]


def config_path(base: Path | None = None) -> Path:
    """Return the default configuration path, optionally rooted at *base*."""
    if base is not None:
        return base / "mailhub" / "config.toml"
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "mailhub" / "config.toml"


def _require_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")
    return value


def parse_config(data: dict[str, Any]) -> Config:
    """Validate decoded TOML data and return its account registry."""
    raw_accounts = data.get("accounts", {})
    if not isinstance(raw_accounts, dict):
        raise ConfigError("accounts must be a TOML table")

    accounts: list[Account] = []
    aliases: set[str] = set()
    for alias, raw_account in raw_accounts.items():
        if not isinstance(alias, str) or not alias.strip():
            raise ConfigError("account aliases must be non-empty strings")
        if alias in aliases:
            raise ConfigError(f"duplicate account alias: {alias}")
        aliases.add(alias)
        if not isinstance(raw_account, dict):
            raise ConfigError(f"account {alias} must be a TOML table")
        provider = _require_string(raw_account.get("provider"), f"account {alias}.provider")
        if provider not in PROVIDER_CAPABILITIES:
            supported = ", ".join(sorted(PROVIDER_CAPABILITIES))
            raise ConfigError(f"account {alias} uses unsupported provider {provider!r}; supported: {supported}")
        raw_capabilities = raw_account.get("capabilities")
        if not isinstance(raw_capabilities, list) or not raw_capabilities:
            raise ConfigError(f"account {alias}.capabilities must be a non-empty array")
        if not all(isinstance(item, str) for item in raw_capabilities):
            raise ConfigError(f"account {alias}.capabilities must contain strings")
        capabilities = frozenset(raw_capabilities)
        unsupported = capabilities - PROVIDER_CAPABILITIES[provider]
        if unsupported:
            items = ", ".join(sorted(unsupported))
            raise ConfigError(f"account {alias} provider {provider!r} does not support: {items}")
        accounts.append(Account(alias=alias, provider=provider, capabilities=capabilities))
    
    # Create config with raw data
    config = Config(accounts=tuple(accounts), _raw=data)
    return config


def load_config(path: Path | None = None) -> Config:
    """Load and validate a configuration file without exposing any secrets."""
    selected = path or config_path()
    try:
        with selected.open("rb") as file:
            data = tomllib.load(file)
    except FileNotFoundError as error:
        raise ConfigError(f"configuration not found: {selected}; run 'mailhub init'") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"invalid TOML in {selected}: {error}") from error
    if not isinstance(data, dict):  # defensive; tomllib currently guarantees this
        raise ConfigError("configuration root must be a TOML table")
    return parse_config(data)


CONFIG_TEMPLATE = """# Mailhub account registry.
#
# [accounts.personal]
# provider = "gmail"
# capabilities = ["mail", "calendar", "contacts"]
# client_id = "personal-gcp-project-id"
# client_secret = "personal-gcp-secret"
#
# [accounts.work]
# provider = "graph"
# capabilities = ["mail", "calendar", "contacts", "tasks"]
# client_id = "work-entra-app-id"
# client_secret = "work-entra-secret"
#
# [accounts.imap_mail]
# provider = "imap"
# capabilities = ["mail"]
# email = "user@example.com"
# client_id = "user@example.com"
# client_secret = "app-password"
#
# [gmail]
# client_id = "shared-gcp-project-id"
# client_secret = "shared-gcp-secret"
#
# [graph]
# client_id = "shared-entra-app-id"
# client_secret = "shared-entra-secret"
#
# [imap]
# host = "imap.example.com"
# port = 993
# smtp_host = "smtp.example.com"
# smtp_port = 587
# use_ssl = true
# use_starttls = false
"""


def initialize_config(path: Path | None = None) -> Path:
    """Create an empty, owner-only configuration template without overwriting one."""
    selected = path or config_path()
    selected.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(selected.parent, stat.S_IRWXU)
    try:
        descriptor = os.open(selected, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        os.chmod(selected, stat.S_IRUSR | stat.S_IWUSR)
        return selected
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(CONFIG_TEMPLATE)
    return selected


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically with owner-only permissions."""
    # Only create/chmod parent directory if it doesn't exist or is our mailhub config dir
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Only chmod if we created it (best effort)
        os.chmod(path.parent, stat.S_IRWXU)
    except (PermissionError, OSError):
        # Ignore permission errors for parent dirs we don't own (e.g., /tmp in tests)
        pass
    
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=".config.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp_path, path)


def _serialize_account(account: Account) -> dict[str, Any]:
    """Serialize an Account to a TOML-compatible dict."""
    return {
        "provider": account.provider,
        "capabilities": sorted(account.capabilities),
    }


def save_config(config: Config, path: Path | None = None) -> Path:
    """Save a Config object to a TOML file atomically with owner-only permissions."""
    selected = path or config_path()
    
    # Build the TOML structure preserving non-account sections
    raw = dict(config._raw)
    raw_accounts = {}
    for account in config.accounts:
        raw_accounts[account.alias] = _serialize_account(account)
    raw["accounts"] = raw_accounts
    
    # Generate TOML content
    lines = []
    # Write provider sections first (gmail, graph, etc.)
    for provider in ("gmail", "graph", "imap", "caldav", "carddav"):
        if provider in raw and isinstance(raw[provider], dict):
            provider_data = raw[provider]
            if provider_data:
                lines.append(f"[{provider}]")
                for key, value in provider_data.items():
                    if isinstance(value, str):
                        lines.append(f'{key} = "{value}"')
                    else:
                        lines.append(f"{key} = {value}")
                lines.append("")
    
    # Write accounts
    lines.append("[accounts]")
    for alias, account_data in raw_accounts.items():
        lines.append(f"  [accounts.{alias}]")
        lines.append(f'  provider = "{account_data["provider"]}"')
        caps = ", ".join(f'"{c}"' for c in account_data["capabilities"])
        lines.append(f"  capabilities = [{caps}]")
        lines.append("")
    
    content = "\n".join(lines)
    _atomic_write(selected, content)
    return selected


def add_account(
    config: Config,
    alias: str,
    provider: str,
    capabilities: list[str],
    path: Path | None = None,
) -> Config:
    """Add a new account to the configuration and save it."""
    if provider not in PROVIDER_CAPABILITIES:
        supported = ", ".join(sorted(PROVIDER_CAPABILITIES))
        raise ConfigError(f"unsupported provider {provider!r}; supported: {supported}")
    
    # Check for duplicate alias
    for account in config.accounts:
        if account.alias == alias:
            raise ConfigError(f"duplicate account alias: {alias}")
    
    # Validate capabilities
    if not capabilities:
        raise ConfigError("capabilities must be a non-empty array")
    caps_set = frozenset(capabilities)
    unsupported = caps_set - PROVIDER_CAPABILITIES[provider]
    if unsupported:
        items = ", ".join(sorted(unsupported))
        raise ConfigError(f"provider {provider!r} does not support: {items}")
    
    # Create new account
    new_account = Account(alias=alias, provider=provider, capabilities=caps_set)
    new_accounts = config.accounts + (new_account,)
    
    # Create new config with updated accounts
    new_config = Config(accounts=new_accounts, _raw=config._raw)
    save_config(new_config, path)
    return new_config


def remove_account(config: Config, alias: str, path: Path | None = None) -> Config:
    """Remove an account from the configuration and save it."""
    new_accounts = tuple(a for a in config.accounts if a.alias != alias)
    if len(new_accounts) == len(config.accounts):
        raise ConfigError(f"account {alias} not found")
    
    new_config = Config(accounts=new_accounts, _raw=config._raw)
    save_config(new_config, path)
    return new_config


def validate_config_structure(data: dict[str, Any]) -> list[str]:
    """Validate config structure and return list of warnings (non-fatal)."""
    warnings = []
    
    # Check for provider sections
    for provider in ("gmail", "graph"):
        if provider in data:
            provider_data = data[provider]
            if isinstance(provider_data, dict):
                if not provider_data.get("client_id"):
                    warnings.append(f"provider {provider} missing client_id")
                if provider == "gmail" and not provider_data.get("client_secret"):
                    warnings.append(f"provider gmail missing client_secret")
    
    return warnings


def validate_provider_credentials(config: Config) -> list[str]:
    """Validate that required provider credentials exist. Returns list of errors."""
    errors = []
    providers_seen = set()
    
    for account in config.accounts:
        providers_seen.add(account.provider)
    
    for provider in providers_seen:
        provider_cfg = config.provider_config(provider)
        if not provider_cfg.get("client_id"):
            errors.append(f"provider {provider} missing client_id")
        if provider == "gmail" and not provider_cfg.get("client_secret"):
            errors.append(f"provider gmail missing client_secret")
    
    return errors
