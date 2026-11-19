# GoMami MCP

<!-- mcp-name: io.github.Guoqiang1006/gomami-mcp -->

[![Test](https://github.com/Guoqiang1006/gomami-mcp/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/Guoqiang1006/gomami-mcp/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/Guoqiang1006/gomami-mcp?include_prereleases)](https://github.com/Guoqiang1006/gomami-mcp/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://github.com/Guoqiang1006/gomami-mcp/blob/main/pyproject.toml)
[![License: MIT](https://img.shields.io/github/license/Guoqiang1006/gomami-mcp)](https://github.com/Guoqiang1006/gomami-mcp/blob/main/LICENSE)

[简体中文](https://github.com/Guoqiang1006/gomami-mcp/blob/main/README.zh-CN.md)

Manage your GoMami servers from any AI agent that supports the [Model Context Protocol](https://modelcontextprotocol.io), including Claude Code, Codex, Cursor and VS Code. It also works with other VPS hosts whose control panel runs VirtFusion, such as GreenCloud. See [Other VirtFusion panels](#other-virtfusion-panels).

- **Read-only by default.** Changing a server has to be turned on explicitly.
- **Runs on your computer.** There is nothing to host, and your token goes only to GoMami.
- **No third-party Python dependencies.** It covers all 29 operations in the GoMami API reference.

> **Not affiliated with GoMami.** This is an independent community project.

> **Alpha.** `verify_connection`, `get_account` and `list_servers` have been tested against the live API. All other tools, including every tool that changes a server, have only been tested against a local mock. Try them on a disposable server first.

## What you can ask

- "List my GoMami servers and show their IP addresses."
- "When does this server's current traffic period end?"
- "Show the recent tasks for this server and tell me if any failed."
- "Which OS templates can I rebuild this server with?"

## Supported agents

Any agent that can start a local MCP server over stdio should work.

| Agent | Status |
| --- | --- |
| Claude Code | Tested with the live API |
| Official MCP Python SDK | Protocol tested |
| Codex | Should work, not tested yet |
| Cursor | Should work, not tested yet |
| VS Code | Should work, not tested yet |
| Claude Desktop | Should work, not tested yet |
| DeepSeek Harness | Should work through its MCP client plugin, not tested yet |
| Web-only agents that need a remote HTTP server | Not supported |

If you try it with another agent, please share the result in [Discussions](https://github.com/Guoqiang1006/gomami-mcp/discussions).

## Quick start

You need macOS or Linux, Python 3.10 or newer, [uv](https://docs.astral.sh/uv/) and a GoMami API token.

### 1. Create a token

Sign in at `gomami.io` and open [Create API Token](https://gomami.io/createapi.php). The token has full account access and is shown only once.

### 2. Save the token

Run this command, paste the token (nothing is displayed), then press Enter:

```bash
(umask 077; mkdir -p ~/.config/gomami-mcp; IFS= read -rs t; printf '%s\n' "$t" > ~/.config/gomami-mcp/token; unset t)
```

### 3. Add the server to your agent

Use one of the configurations below, then start a new session.

### 4. Check the connection

Ask your agent to run `verify_connection`.

## Agent configuration

Desktop apps may not find `uvx` on their `PATH`. If the server fails to start, replace `uvx` with the full path printed by `command -v uvx`.

### Claude Code

```bash
claude mcp add gomami --scope user -- uvx gomami-mcp@0.2.0
```

### Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.gomami]
command = "uvx"
args = ["gomami-mcp@0.2.0"]
env = { GOMAMI_MCP_ACCESS = "read" }
startup_timeout_sec = 60
```

### Cursor

Add this to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "gomami": {
      "type": "stdio",
      "command": "uvx",
      "args": ["gomami-mcp@0.2.0"],
      "env": { "GOMAMI_MCP_ACCESS": "read" }
    }
  }
}
```

### VS Code

Add this to `.vscode/mcp.json`:

```json
{
  "servers": {
    "gomami": {
      "type": "stdio",
      "command": "uvx",
      "args": ["gomami-mcp@0.2.0"],
      "env": { "GOMAMI_MCP_ACCESS": "read" }
    }
  }
}
```

### Claude Desktop

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gomami": {
      "command": "uvx",
      "args": ["gomami-mcp@0.2.0"],
      "env": { "GOMAMI_MCP_ACCESS": "read" }
    }
  }
}
```

### Other agents

Configure a local stdio server with this command:

```bash
uvx gomami-mcp@0.2.0
```

For DeepSeek Harness, use this command with its `@deepseek-ai/dsh-mcp-client` plugin.

## Other VirtFusion panels

GoMami's panel is [VirtFusion](https://virtfusion.com). Other hosts that use VirtFusion expose the same customer API, so you can point this server at their panel instead. Look for an API page in your panel, such as `/account/api`.

1. Save that panel's token. Each panel gets its own file, named after the panel's host. For example, for GreenCloud (`cp.green.cloud`):

   ```bash
   (umask 077; mkdir -p ~/.config/gomami-mcp; IFS= read -rs t; printf '%s\n' "$t" > ~/.config/gomami-mcp/token-cp.green.cloud; unset t)
   ```

2. Add a second server entry with `GOMAMI_API_BASE` set to the panel's API URL. For Claude Code:

   ```bash
   claude mcp add greencloud --scope user -e GOMAMI_API_BASE=https://cp.green.cloud/api -- uvx gomami-mcp@0.2.0
   ```

GreenCloud has been tested with the read-only tools. Other panels have not been tested, and a host may turn off parts of the API.

## Settings

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `GOMAMI_MCP_ACCESS` | `read` | Access tier: `read`, `operate` or `full`. Unknown values fall back to `read`. |
| `GOMAMI_MCP_PROTECTED_SERVERS` | empty | Comma-separated server IDs that can be read but not changed. |
| `GOMAMI_API_BASE` | `https://cp.gomami.io/api` | API URL of a VirtFusion panel. Only `https://` is accepted. If the value is invalid, every request is refused instead of falling back to GoMami. |
| `GOMAMI_TOKEN_FILE` | see note | Token file. Defaults to `~/.config/gomami-mcp/token` for GoMami and `~/.config/gomami-mcp/token-<host>` for other panels, so a token is never sent to the wrong host. |
| `GOMAMI_API_TOKEN` | empty | Token value. Takes priority over the token file. If you use more than one panel, prefer token files, because this value is sent to whichever panel `GOMAMI_API_BASE` names. |

## Tools

| Tier | Tools |
| --- | --- |
| `read` | `verify_connection`, `get_account`, `list_ssh_keys`, `list_servers`, `get_server`, `list_os_templates`, `list_swap_options`, `list_isos`, `list_tasks`, `get_task`, `list_resource_packs`, `get_resource_pack` |
| `operate` | All of the above, plus `get_vnc_status`, `boot_server`, `restart_server`, `shutdown_server`, `power_off_server`, `rename_server` |
| `full` | All of the above, plus `rebuild_server`, `reset_server_password`, `toggle_rescue`, `toggle_vnc`, `set_iso`, `set_boot_order`, `update_server_settings`, `add_ssh_key`, `delete_ssh_key`, `create_resource_pack_server`, `delete_resource_pack_server` |

## Safety

- **Protect production servers.** Add them to `GOMAMI_MCP_PROTECTED_SERVERS`. The MCP server enforces this list in every agent.
- **Do not rely on approval prompts alone.** Whether an agent asks before running a tool depends on that agent and its settings.
- **Confirmation text prevents mistakes, not decisions.** Tools that change a server need text such as `REBUILD <server-id>`, but a model can fill it in by itself.
- **Secrets stay out of the chat.** VNC credentials are hidden, and reset passwords are saved under `~/.config/gomami-mcp/secrets/` with mode `600`.
- **Write requests are never retried automatically.**

See [SECURITY.md](https://github.com/Guoqiang1006/gomami-mcp/blob/main/SECURITY.md) for details and limits.

## Known limitations

- Windows is not supported.
- The API reference does not say what value `set_iso` needs to eject an ISO.
- The API reference describes `GET /server/{id}/vnc` as a toggle, which looks like a typo. It is placed in the `operate` tier to be safe.
- The API is behind Cloudflare. Blocked requests are reported clearly, and this project does not try to work around them.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests use a local mock and never contact GoMami.

## License

[MIT](https://github.com/Guoqiang1006/gomami-mcp/blob/main/LICENSE)
