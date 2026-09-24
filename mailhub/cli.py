"""Command-line interface for Mailhub: init, auth, status, doctor, serve, mcp, config."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
import webbrowser
from pathlib import Path
from typing import Sequence

from .completion import generate_completion
from .config import (
    Account,
    Config,
    ConfigError,
    config_path,
    initialize_config,
    load_config,
    parse_config,
    save_config,
    add_account,
    remove_account,
    validate_config_structure,
    validate_provider_credentials,
    PROVIDER_CAPABILITIES,
)
from .core import Core, CoreError
from .mcp import run_stdio
from .oauth import Provider, ReauthNeeded, auth_url, check_state, exchange, parse_redirect
from .store import CredentialStore, state_path


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _print_error(msg: str) -> None:
    print(msg, file=sys.stderr)


def _filter_pytest_args(argv: list[str] | None) -> list[str]:
    """Filter out pytest test node IDs (e.g., 'tests/test_config_cli.py::Test...')."""
    if argv is None:
        return sys.argv[1:]
    filtered = [arg for arg in argv if not (arg.startswith("tests/") and "::" in arg)]
    return filtered


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mailhub", description="Local Mailhub")
    parser.add_argument(
        "--generate-completion",
        choices=("bash", "zsh", "fish"),
        help="generate shell completion script for the given shell",
    )
    subcommands = parser.add_subparsers(dest="command")

    init = subcommands.add_parser("init", help="create owner-only local configuration and state files")
    init.add_argument("--config", type=_path, help="configuration file path (for tests or custom XDG use)")
    init.add_argument("--state", type=_path, help="credential-state file path (for tests or custom XDG use)")

    auth = subcommands.add_parser("auth", help="authorize an account (OAuth flow)")
    auth.add_argument("provider", choices=("gmail", "graph", "imap"), help="provider: gmail or graph")
    auth.add_argument("alias", help="account alias from config")
    auth.add_argument("--code", help="authorization code or redirect URL from browser")
    auth.add_argument("--config", type=_path, help="configuration file path")

    status = subcommands.add_parser("status", help="show configured accounts without contacting providers")
    status.add_argument("--config", type=_path, help="configuration file path")

    doctor = subcommands.add_parser("doctor", help="check account health and refresh tokens")
    doctor.add_argument("--config", type=_path, help="configuration file path")

    reauth = subcommands.add_parser("reauth", help="re-authorize an account (force new consent)")
    reauth.add_argument("provider", choices=("gmail", "graph", "imap"), help="provider: gmail or graph")
    reauth.add_argument("alias", help="account alias from config")
    reauth.add_argument("--config", type=_path, help="configuration file path")

    logout = subcommands.add_parser("logout", help="remove stored tokens for an account")
    logout.add_argument("alias", help="account alias from config")
    logout.add_argument("--config", type=_path, help="configuration file path")

    serve = subcommands.add_parser("serve", help="start REST API server (127.0.0.1 only)")
    serve.add_argument("--host", default="127.0.0.1", help="bind address (default: 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8787, help="port (default: 8787)")
    serve.add_argument("--config", type=_path, help="configuration file path")

    mcp = subcommands.add_parser("mcp", help="run Mailhub MCP over stdio")
    mcp.add_argument("--mode", default="ro", choices=("ro", "full"), help="read-only or full mode")
    mcp.add_argument("--config", type=_path, help="configuration file path")

    config = subcommands.add_parser("config", help="manage mailhub configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)

    config_list = config_sub.add_parser("list", help="list configured accounts")
    config_list.add_argument("--config", type=_path, help="configuration file path")

    config_add = config_sub.add_parser("add-account", help="add a new account (non-interactive)")
    config_add.add_argument("--config", type=_path, help="configuration file path")
    config_add.add_argument("--alias", help="account alias")
    config_add.add_argument("--provider", help="provider (e.g. gmail, graph)")
    config_add.add_argument("--capabilities", nargs="+", choices=["mail", "calendar", "contacts", "tasks"], help="capabilities")
    config_add.add_argument("--email", help="email address")

    config_validate = config_sub.add_parser("validate", help="validate config syntax and provider credentials")
    config_validate.add_argument("--config", type=_path, help="configuration file path")

    config_doctor = config_sub.add_parser("doctor", help="validate config structure and check account health")
    config_doctor.add_argument("--config", type=_path, help="configuration file path")

    config_setup_google = config_sub.add_parser("setup-google", help="open browser to Google Cloud Console for OAuth setup")
    config_setup_google.add_argument("--config", type=_path, help="configuration file path")

    config_setup_microsoft = config_sub.add_parser("setup-microsoft", help="open browser to Entra ID for app registration")
    config_setup_microsoft.add_argument("--config", type=_path, help="configuration file path")

    config_remove = config_sub.add_parser("remove-account", help="remove an account from configuration")
    config_remove.add_argument("alias", help="account alias to remove")
    config_remove.add_argument("--config", type=_path, help="configuration file path")

    return parser


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _print_error(msg: str) -> None:
    print(msg, file=sys.stderr)


def handle_config_command(args, config_file: Path) -> int:
    if args.config_command == "list":
        return handle_config_list(args, config_file)
    elif args.config_command == "add-account":
        return handle_config_add_account(args, config_file)
    elif args.config_command == "validate":
        return handle_config_validate(args, config_file)
    elif args.config_command == "doctor":
        return handle_config_doctor(args, config_file)
    elif args.config_command == "setup-google":
        return handle_config_setup_google(args, config_file)
    elif args.config_command == "setup-microsoft":
        return handle_config_setup_microsoft(args, config_file)
    elif args.config_command == "remove-account":
        return handle_config_remove_account(args, config_file)
    else:
        _print_error(f"mailhub: unknown config command: {args.config_command}")
        return 2


def handle_config_list(args, config_file: Path) -> int:
    try:
        config = load_config(config_file)
    except ConfigError as error:
        _print_error(f"mailhub: {error}")
        return 2

    if not config.accounts:
        print("No accounts configured.")
        return 0

    print(f"{'Alias':<20} {'Provider':<10} {'Capabilities'}")
    print("-" * 55)
    for account in config.accounts:
        caps = ", ".join(sorted(account.capabilities))
        print(f"{account.alias:<20} {account.provider:<10} {caps}")
    return 0


def handle_config_add_account(args, config_file: Path) -> int:
    try:
        config = load_config(config_file)
    except ConfigError as error:
        _print_error(f"mailhub: {error}")
        return 2

    if args.alias and args.provider and args.capabilities:
        try:
            add_account(config, args.alias, args.provider, args.capabilities, config_file)
        except ConfigError as error:
            _print_error(f"mailhub: {error}")
            return 1
        print(f"Added account: {args.alias} ({args.provider}) with capabilities: {', '.join(args.capabilities)}")
        if args.email:
            print(f"  Email: {args.email}")
        print("Run 'mailhub auth' to authorize this account.")
        return 0

    _print_error("mailhub: interactive mode not yet implemented; use --alias --provider --capabilities --email")
    return 1


def handle_config_validate(args, config_file: Path) -> int:
    try:
        with config_file.open("rb") as file:
            data = tomllib.load(file)
    except FileNotFoundError:
        _print_error(f"mailhub: configuration not found: {config_file}; run 'mailhub init'")
        return 2
    except tomllib.TOMLDecodeError as error:
        _print_error(f"mailhub: invalid TOML in {config_file}: {error}")
        return 1

    try:
        config = parse_config(data)
    except ConfigError as error:
        _print_error(f"mailhub: config validation failed: {error}")
        return 1

    warnings = validate_config_structure(data)
    for warning in warnings:
        _print_error(f"Warning: {warning}")

    errors = validate_provider_credentials(config)
    for error in errors:
        _print_error(f"Error: {error}")

    if errors:
        return 1

    if not config.accounts:
        _print_error("Config is valid but no accounts configured.")
        return 0

    print("Configuration is valid.")
    return 0


def handle_config_doctor(args, config_file: Path) -> int:
    validate_result = handle_config_validate(args, config_file)
    if validate_result != 0:
        return validate_result

    try:
        config = load_config(args.config or config_path())
        core = Core(config=config)
    except ConfigError as error:
        _print_error(f"mailhub: {error}")
        return 2
    except CoreError as e:
        _print_error(f"mailhub: {e}")
        return 1

    results = core.doctor()
    for r in results:
        line = f"{r['alias']}: {r['provider']} {r['status']}"
        if r.get("hint"):
            line += f"  ({r['hint']})"
        if r.get("detail"):
            line += f"  {r['detail']}"
        print(line)

    failed = any(r["status"] != "ok" for r in results)
    return 1 if failed else 0


def handle_config_setup_google(args, config_file: Path) -> int:
    print("Opening Google Cloud Console for OAuth client setup...")
    print()
    print("Steps:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Create a new project or select existing")
    print("3. Enable Gmail API: APIs & Services > Library > Gmail API > Enable")
    print("4. Configure OAuth consent screen: APIs & Services > OAuth consent screen")
    print("   - Choose 'External' user type")
    print("   - Fill required fields (app name, support email)")
    print("   - Add scopes: .../auth/gmail.modify, .../auth/userinfo.email")
    print("   - Publish to production (avoids 7-day token expiry)")
    print("5. Create credentials: APIs & Services > Credentials > Create Credentials > OAuth client ID")
    print("   - Application type: Desktop app")
    print("6. Copy the Client ID and Client Secret")
    print()

    url = "https://console.cloud.google.com/apis/credentials"
    try:
        webbrowser.open(url)
        print(f"Opened: {url}")
    except Exception:
        print(f"Please open manually: {url}")

    print()
    client_id = input("Enter Client ID: ").strip()
    client_secret = input("Enter Client Secret: ").strip()

    if not client_id or not client_secret:
        _print_error("mailhub: both client_id and client_secret are required")
        return 1

    try:
        config = load_config(config_file)
    except ConfigError:
        initialize_config(config_file)
        config = load_config(config_file)

    raw = dict(config._raw)
    raw["gmail"] = {
        "client_id": client_id,
        "client_secret": client_secret,
    }
    new_config = Config(accounts=config.accounts, _raw=raw)
    save_config(new_config, config_file)

    print("Google OAuth credentials saved to config.")
    print("Run 'mailhub config add-account' to add Gmail accounts.")
    return 0


def handle_config_setup_microsoft(args, config_file: Path) -> int:
    print("Opening Microsoft Entra ID for app registration...")
    print()
    print("Steps:")
    print("1. Go to https://entra.microsoft.com/")
    print("2. App registrations > New registration")
    print("3. Name your app, choose 'Personal Microsoft accounts only'")
    print("4. Redirect URI: http://localhost:8788 (Mobile and desktop applications)")
    print("5. API permissions > Add a permission > Microsoft Graph > Delegated:")
    print("   - offline_access, Mail.ReadWrite, Mail.Send, MailboxSettings.ReadWrite, User.Read")
    print("6. Grant admin consent if needed")
    print("7. Copy the Application (client) ID")
    print()

    url = "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade"
    try:
        webbrowser.open(url)
        print(f"Opened: {url}")
    except Exception:
        print(f"Please open manually: {url}")

    print()
    client_id = input("Enter Application (client) ID: ").strip()

    if not client_id:
        _print_error("mailhub: client_id is required")
        return 1

    try:
        config = load_config(config_file)
    except ConfigError:
        initialize_config(config_file)
        config = load_config(config_file)

    raw = dict(config._raw)
    raw["graph"] = {
        "client_id": client_id,
    }
    new_config = Config(accounts=config.accounts, _raw=raw)
    save_config(new_config, config_file)

    print("Microsoft OAuth credentials saved to config.")
    print("Run 'mailhub config add-account' to add Graph accounts.")
    return 0


def handle_config_remove_account(args, config_file: Path) -> int:
    try:
        config = load_config(config_file)
    except ConfigError as error:
        _print_error(f"mailhub: {error}")
        return 2

    try:
        remove_account(config, args.alias, config_file)
    except ConfigError as error:
        _print_error(f"mailhub: {error}")
        return 1

    print(f"Removed account: {args.alias}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    filtered_argv = _filter_pytest_args(list(argv) if argv else None)
    parser = build_parser()
    args = parser.parse_args(filtered_argv)

    if args.generate_completion:
        try:
            print(generate_completion(args.generate_completion))
            return 0
        except ValueError as error:
            _print_error(f"mailhub: {error}")
            return 1

    if args.command is None:
        parser.print_help()
        return 2

    if args.command == "config":
        config_file = args.config or config_path()
        return handle_config_command(args, config_file)

    if args.command == "init":
        config = initialize_config(args.config or config_path())
        state = CredentialStore(args.state or state_path()).initialize()
        print(f"Initialized configuration: {config}")
        print(f"Initialized credential state: {state}")
        return 0

    if args.command == "status":
        try:
            config = load_config(args.config or config_path())
        except ConfigError as error:
            _print_error(f"mailhub: {error}")
            return 2
        print(json.dumps({"accounts": config.status()}, indent=2))
        return 0

    if args.command == "auth":
        try:
            config = load_config(args.config or config_path())
        except ConfigError as error:
            _print_error(f"mailhub: {error}")
            return 2

        account = config.account(args.alias)
        provider: Provider = account.provider

        # IMAP supports multiple auth methods
        if provider == "imap":
            print("IMAP/SMTP Configuration:")
            print("  Auth methods: plain (username/password), app_password")
            print("  For OAuth2, use 'oauth2' (not yet implemented)")
            
            # Get auth method
            auth_method = input("Auth method [plain/app_password] [plain]: ").strip() or "plain"
            
            # Get IMAP credentials
            imap_username = input(f"IMAP username [{account.email}]: ").strip() or account.email
            imap_password = input("IMAP password: ").strip()
            if not imap_password:
                _print_error("mailhub: IMAP password required")
                return 1
            
            # Get SMTP credentials (optional, separate from IMAP)
            print("\nSMTP Configuration (press Enter to use IMAP settings):")
            smtp_username = input(f"SMTP username [{imap_username}]: ").strip()
            smtp_password = input(f"SMTP password [{imap_password}]: ").strip()
            
            # Store credentials
            store = CredentialStore(args.state or state_path())
            store.initialize()
            data = store.load()
            accounts = data.setdefault("accounts", {})
            
            accounts[args.alias] = {
                "access_token": "",
                "refresh_token": imap_password,
                "expires_at": 0,
                "client_id": imap_username,
                "client_secret": imap_password,
                "smtp_username": smtp_username,
                "smtp_password": smtp_password,
                "auth_method": auth_method,
            }
            store.save(data)
            
            print(f"Successfully configured {args.alias} (IMAP with {auth_method} auth)")
            print("Note: Edit ~/.config/mailhub/config.toml to customize IMAP/SMTP host/port settings")
            return 0

        client_cfg = config.provider_config(provider)

        if not args.code:
            url, state_obj = auth_url(provider, client_cfg["client_id"], account.email, args.alias)
            print(f"Open this URL in your browser:\n{url}\n")
            print("After consent, the browser will show a 404 at localhost:8788.")
            print("Copy the full URL from the address bar and run:")
            print(f"  mailhub auth {provider} {args.alias} --code '<pasted-url>'")
            import json as json_lib
            state_file = state_path().parent / f"oauth_{provider}_{args.alias}.json"
            state_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            state_file.write_text(json_lib.dumps({
                "state": state_obj.state,
                "provider": state_obj.provider,
                "alias": state_obj.alias,
                "code_verifier": state_obj.pkce.code_verifier,
            }))
            return 0

        code, state = parse_redirect(args.code)
        if not state:
            _print_error("mailhub: no state in redirect URL")
            return 1
        import json as json_lib
        state_file = state_path().parent / f"oauth_{provider}_{args.alias}.json"
        if not state_file.exists():
            _print_error("mailhub: no stored auth state found")
            return 1
        with state_file.open() as f:
            saved = json_lib.load(f)
        from .oauth import AuthState, PKCE
        stored = AuthState(
            state=saved["state"],
            provider=saved["provider"],
            alias=saved["alias"],
            pkce=PKCE(code_verifier=saved["code_verifier"], code_challenge="")
        )
        pkce = check_state(state, provider, args.alias, stored)
        tokens = exchange(provider, client_cfg["client_id"], client_cfg.get("client_secret", ""), code, pkce.code_verifier)
        state_file.unlink(missing_ok=True)

        store = CredentialStore(args.state or state_path())
        store.initialize()
        data = store.load()
        accounts = data.setdefault("accounts", {})
        accounts[args.alias] = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": int(__import__("time").time()) + tokens.get("expires_in", 3600),
            "client_id": client_cfg["client_id"],
            "client_secret": client_cfg.get("client_secret"),
        }
        store.save(data)
        print(f"Successfully authorized {args.alias} ({provider})")
        return 0

    if args.command == "reauth":
        try:
            config = load_config(args.config or config_path())
        except ConfigError as error:
            _print_error(f"mailhub: {error}")
            return 2

        account = config.account(args.alias)
        provider: Provider = account.provider

        # IMAP: re-enter credentials
        if provider == "imap":
            print("IMAP/SMTP Re-configuration:")
            auth_method = input("Auth method [plain/app_password] [plain]: ").strip() or "plain"
            imap_username = input(f"IMAP username [{account.email}]: ").strip() or account.email
            imap_password = input("IMAP password: ").strip()
            if not imap_password:
                _print_error("mailhub: IMAP password required")
                return 1
            
            print("\nSMTP Configuration (press Enter to use IMAP settings):")
            smtp_username = input(f"SMTP username [{imap_username}]: ").strip()
            smtp_password = input(f"SMTP password [{imap_password}]: ").strip()
            
            store = CredentialStore(args.state or state_path())
            store.initialize()
            data = store.load()
            accounts = data.setdefault("accounts", {})
            accounts[args.alias] = {
                "access_token": "",
                "refresh_token": imap_password,
                "expires_at": 0,
                "client_id": imap_username,
                "client_secret": imap_password,
                "smtp_username": smtp_username,
                "smtp_password": smtp_password,
                "auth_method": auth_method,
            }
            store.save(data)
            print(f"Successfully updated {args.alias} (IMAP with {auth_method} auth)")
            return 0

        client_cfg = config.provider_config(provider)
        url, _ = auth_url(provider, client_cfg["client_id"], account.email, args.alias)
        print(f"Open this URL in your browser (forced consent):\n{url}\n")
        print("After consent, copy the full redirect URL and run:")
        print(f"  mailhub auth {provider} {args.alias} --code '<pasted-url>'")
        return 0

    if args.command == "logout":
        store = CredentialStore(args.state or state_path())
        data = store.load()
        if args.alias in data.get("accounts", {}):
            del data["accounts"][args.alias]
            store.save(data)
            print(f"Logged out {args.alias}")
        else:
            _print_error(f"Account {args.alias} not found in credential store")
        return 0

    if args.command == "doctor":
        try:
            config = load_config(args.config or config_path())
            core = Core(config=config)
        except ConfigError as error:
            _print_error(f"mailhub: {error}")
            return 2
        except CoreError as e:
            _print_error(f"mailhub: {e}")
            return 1

        results = core.doctor()
        for r in results:
            line = f"{r['alias']}: {r['provider']} {r['status']}"
            if r.get("hint"):
                line += f"  ({r['hint']})"
            if r.get("detail"):
                line += f"  {r['detail']}"
            print(line)

        failed = any(r["status"] != "ok" for r in results)
        return 1 if failed else 0

    if args.command == "serve":
        from .app import run_server
        run_server(args.config, host=args.host, port=args.port)
        return 0

    if args.command == "mcp":
        from .mcp import run_stdio
        run_stdio(mode=args.mode, config_file=args.config)
        return 0

    _print_error(f"mailhub: unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
