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


## Installation Options

### Permanent Install (Recommended for Daily Use)

```bash
# Install via uv (fast, isolated)
uv tool install zc-mailhub

# Or via pip
pip install zc-mailhub

# Or via pipx
pipx install zc-mailhub
```

### Ephemeral / One-off Use (uvx)

```bash
# Run without installing (downloads + caches automatically)
uvx --from zc-mailhub mailhub init
uvx --from zc-mailhub mailhub mcp --mode full
uvx --from zc-mailhub mailhub doctor

# Use specific version
uvx --from zc-mailhub@0.1.2 mailhub mcp --mode full

# Force update to latest
uvx --from zc-mailhub@latest mailhub mcp --mode full
```

### Docker

```bash
# Pull and run
docker pull ghcr.io/zeroclue/zc-mailhub:v0.1.2
docker run -p 8787:8787 ghcr.io/zeroclue/zc-mailhub:v0.1.2 serve

# Or use docker-compose (see docker-compose.yml)
docker compose up -d
```

### Development Install

```bash
git clone https://github.com/ZeroClue/mailhub
cd mailhub
uv sync --extra dev
uv run mailhub init
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

## Docker Usage

Mailhub provides official Docker images via GitHub Container Registry:

```bash
# Quick start with docker-compose
docker compose up -d

# View logs
docker compose logs -f mailhub

# Run MCP server only
docker compose run --rm mailhub-mcp

# Build locally
docker build -t zc-mailhub .
docker run -p 8787:8787 zc-mailhub serve
```

### docker-compose.yml

The provided `docker-compose.yml` runs two services:

| Service | Description | Port |
|---------|-------------|------|
| `mailhub` | REST API server | 8787 |
| `mailhub-mcp` | MCP server (full mode) | stdio |

Configuration and state are persisted via Docker volumes:

```yaml
volumes:
  mailhub-config:
  mailhub-state:
```

### Building Locally

```bash
# Build image
docker build -t zc-mailhub .

# Run REST API
docker run -p 8787:8787 zc-mailhub serve

# Run MCP server
docker run -it zc-mailhub mcp --mode full
```

### Security

The Docker image follows security best practices:

- **Multi-stage build** — builder stage for dependencies, minimal runtime image
- **Non-root user** — runs as `mailhub` user (UID/GID 999)
- **No secrets in image** — configuration and credentials mounted as volumes
- **Read-only root filesystem** (when deployed with `read_only: true`)
- **Dropped capabilities** — `cap_drop: ["ALL"]`, `no-new-privileges:true`

### Volumes

Configuration and state are persisted via Docker volumes:

```yaml
volumes:
  mailhub-config:
  mailhub-state:
```

These correspond to `~/.config/mailhub/` and `~/.local/state/mailhub/` on the host.

## MCP Configuration

Mailhub's MCP server runs over stdio and works with all major AI clients. Configure it in your client's MCP settings:

### Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `~/.config/claude/claude_desktop_config.json` on Linux)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "mailhub",
      "args": ["mcp", "--mode", "full"],
      "env": {
        "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
      }
    }
  }
}
```

### Cursor (`.cursor/mcp.json` in project root)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "mailhub",
      "args": ["mcp", "--mode", "full"],
      "env": {
        "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
      }
    }
  }
}
```

### VS Code / GitHub Copilot (`.vscode/mcp.json` in project root)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "mailhub",
      "args": ["mcp", "--mode", "full"],
      "env": {
        "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
      }
    }
  }
}
```

### Windsurf (`~/.config/windsurf/mcp.json`)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "mailhub",
      "args": ["mcp", "--mode", "full"],
      "env": {
        "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
      }
    }
  }
}
```

### Continue.dev (`~/.continue/config.json`)

```json
{
  "mcpServers": [
    {
      "name": "mailhub",
      "command": "mailhub",
      "args": ["mcp", "--mode", "full"],
      "env": {
        "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
      }
    }
  ]
}
```

### Zed (`~/.config/zed/settings.json`)

```json
{
  "mcp": {
    "servers": {
      "mailhub": {
        "command": "mailhub",
        "args": ["mcp", "--mode", "full"],
        "env": {
          "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
        }
      }
    }
  }
}
```


### Using uvx (No Install Required)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "uvx",
      "args": ["--from", "zc-mailhub", "mailhub", "mcp", "--mode", "full"],
      "env": {
        "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
      }
    }
  }
}
```

### Using pipx (Permanent Install)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "pipx",
      "args": ["run", "--spec", "zc-mailhub", "mailhub", "mcp", "--mode", "full"],
      "env": {
        "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
      }
    }
  }
}
```

### Using Docker

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "docker",
      "args": ["run", "-i", "--rm", 
        "-v", "mailhub-config:/home/mailhub/.config/mailhub",
        "-v", "mailhub-state:/home/mailhub/.local/state/mailhub",
        "ghcr.io/zeroclue/zc-mailhub:v0.1.2",
        "mcp", "--mode", "full"],
      "env": {}
    }
  }
}
```

### Sourcegraph Cody (`.cody/mcp.json` in project root)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "mailhub",
      "args": ["mcp", "--mode", "full"],
      "env": {
        "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
      }
    }
  }
}
```

### Using Docker (Local)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "zc-mailhub", "mcp", "--mode", "full"],
      "env": {
        "MAILHUB_CONFIG": "/home/mailhub/.config/mailhub/config.toml"
      }
    }
  }
}
```

### Using SSH (Remote VPS)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "ssh",
      "args": ["user@your-vps", "mailhub", "mcp", "--mode", "full"],
      "env": {}
    }
  }
}
```

### Using SSH + Docker (Remote VPS with Docker)

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "ssh",
      "args": ["user@your-vps", "docker", "run", "--rm", "-i", "zc-mailhub", "mcp", "--mode", "full"],
      "env": {}
    }
  }
}
```

### Read-Only Mode

For read-only access (no mutations), change `--mode full` to `--mode ro`:

```json
{
  "mcpServers": {
    "mailhub": {
      "command": "mailhub",
      "args": ["mcp", "--mode", "ro"],
      "env": {
        "MAILHUB_CONFIG": "/home/youruser/.config/mailhub/config.toml"
      }
    }
  }
}
```

### MCP Server Capabilities

The MCP server exposes the following capabilities in its initialize response:

- **Tools**: All mail operations (search, get, send, draft, move, trash, folders) + status
- **Resources**: Not implemented (mail data accessed via tools)
- **Prompts**: Not implemented
- **Logging**: Supported

Server info returned on initialize:
- `server_name`: "mailhub"
- `server_version`: "0.1.1" (current package version)
- `instructions`: Description of the server and usage hints

