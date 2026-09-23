# Mailhub

Mailhub is a local, MCP-first personal-operations hub for AI assistants and their humans.

## Features

- **Mail** — Gmail, Microsoft Graph (Outlook.com), IMAP/SMTP
- **Calendar** — Google Calendar, Microsoft Graph, CalDAV
- **Contacts** — Google People, Microsoft Graph, CardDAV
- **Tasks** — Microsoft To Do (Graph), CalDAV VTODO
- **MCP-first** — stdio MCP server for AI agents (read-only + full modes)
- **REST API** — localhost-only HTTP server for scripts/CLI
- **CLI** — `mailhub` (admin) and `mail` (user) commands

## Quick Start

```bash
# Install
uv tool install --editable .

# Initialize config & state
mailhub init

# Configure OAuth clients (one-time)
mailhub config setup-google    # Opens Google Cloud Console, guides OAuth setup
mailhub config setup-microsoft # Opens Entra ID, guides app registration

# Add accounts
mailhub config add-account --alias me --provider gmail --capabilities mail --email me@gmail.com
mailhub config add-account --alias work --provider graph --capabilities mail --email me@outlook.com

# Authorize accounts (opens browser, paste redirect URL)
mailhub auth gmail me --code '<pasted-redirect-url>'
mailhub auth graph work --code '<pasted-redirect-url>'

# Verify health
mailhub doctor

# Start REST server (localhost only)
mailhub serve

# Or run MCP server (read-only by default)
mailhub mcp --mode ro
# Or full mode for mutations
mailhub mcp --mode full
```

## Using the `mail` CLI

The `mail` command is a thin HTTP client to the REST API (requires `mailhub serve` running):

```bash
# List accounts
mail accounts

# List folders
mail folders me

# Search messages
mail search me "from:github.com newer_than:7d"
mail search work "hasAttachments:true"

# Get message
mail get me <message-id>

# Send (requires --confirm)
mail send me --to someone@example.com --subject "Hello" --body "Test" --confirm

# Create draft
mail draft me --to someone@example.com --subject "Draft" --body "Content"
```

## Systemd Service (Auto-start)

```bash
# Install service files
mkdir -p ~/.config/systemd/user
cp deploy/*.service deploy/*.timer ~/.config/systemd/user/

# Enable and start
systemctl --user daemon-reload
systemctl --user enable --now mailhub.service mailhub-doctor.timer
loginctl enable-linger  # keeps user services alive after logout
```

## Configuration

Config lives at `~/.config/mailhub/config.toml`:

```toml
[server]
host = "127.0.0.1"
port = 8787

[auth]
ro_token = "..."      # read-only token
full_token = "..."    # full-access token

[send]
allowlist = ["*@example.com"]  # glob patterns
# allow_anywhere = true        # disable allowlist

[gmail]
client_id = "..."
client_secret = "..."

[graph]
client_id = "..."

[accounts.personal]
provider = "gmail"
capabilities = ["mail", "calendar", "contacts"]

[accounts.work]
provider = "graph"
capabilities = ["mail", "calendar", "contacts", "tasks"]
```

## Security

- REST server binds **only to 127.0.0.1** (never 0.0.0.0)
- No hard-delete — only trash/cancel
- Mutations require `confirm=true` + recipient allowlist
- Audit log (`~/.local/state/mailhub/audit.jsonl`) never records tokens/bodies
- Credentials stored with 0600 permissions, atomic writes, fcntl lock
- OAuth PKCE with random state
- Message bodies treated as untrusted input

## Development

```bash
uv sync --extra dev
uv run pytest
uv run mailhub init
uv run mailhub status
uv run mailhub mcp --mode ro
```

## Architecture

```
mailhub/
├── config.py      # TOML config, validation, provider capabilities
├── store.py       # Credential store (atomic, 0600, fcntl lock)
├── oauth.py       # PKCE OAuth for Google/Microsoft
├── core.py        # Policy engine, allowlist, audit, retry, adapters
├── util.py        # HTML→text, MIME, address parsing
├── gmail.py       # Gmail API adapter
├── graph.py       # Microsoft Graph adapter
├── gcal.py        # Google Calendar adapter
├── gcal_graph.py  # Graph Calendar adapter
├── caldav.py      # CalDAV adapter (read)
├── people.py      # Google People adapter
├── people_graph.py # Graph People adapter
├── carddav.py     # CardDAV adapter (read)
├── tasks.py       # Tasks domain
├── tasks_graph.py # Graph Tasks adapter
├── tasks_caldav.py # CalDAV VTODO adapter (read)
├── app.py         # FastAPI REST server (127.0.0.1 only)
├── cli.py         # mailhub admin CLI
├── mail_cli.py    # mail user CLI (thin REST client)
├── mcp.py         # MCP server (ro + full modes)
├── backup.py      # Backup/restore utilities
└── deploy/        # systemd user units
```

## License

MIT

## Man Pages

Install man pages system-wide:

```bash
sudo cp docs/man/mailhub.1 /usr/local/share/man/man1/
sudo cp docs/man/mail.1 /usr/local/share/man/man1/
sudo mandb
```

Then view with:

```bash
man mailhub
man mail
```

Or view locally without installing:

```bash
man -l docs/man/mailhub.1
man -l docs/man/mail.1
```

## Shell Completions

Generate completion scripts for your shell:

```bash
mailhub --generate-completion bash  > ~/.local/share/bash-completion/completions/mailhub
mailhub --generate-completion zsh   > ${fpath[1]}/_mailhub
mailhub --generate-completion fish  > ~/.config/fish/completions/mailhub.fish
```

The completion script also covers the `mail` command (same stub).
