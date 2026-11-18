# GoMami MCP

[简体中文](README.zh-CN.md)

An unofficial [Model Context Protocol](https://modelcontextprotocol.io) server for managing GoMami servers from Claude Code and other MCP clients. It is read-only by default and has no third-party dependencies.

> **Not affiliated with GoMami.** This is an independent community project. "GoMami" is used only to describe the service this tool works with.

> **Alpha.** The read-only connection, account and server list calls have been tested against the live API. All other tools have only been tested against a local mock, so try them on a disposable server first.

## Requirements

- Python 3.10 or newer
- macOS or Linux
- A GoMami API token

## Setup

1. Sign in at `gomami.io` and open [Create API Token](https://gomami.io/createapi.php). Tokens have full account access and are shown only once.

2. Save the token. Run this, paste the token (nothing is displayed), then press Enter:

```bash
(umask 077; mkdir -p ~/.config/gomami-mcp; IFS= read -rs t; printf '%s\n' "$t" > ~/.config/gomami-mcp/token; unset t)
```

3. Clone this repository and add the server to Claude Code:

```bash
claude mcp add gomami --scope user -- python3 /absolute/path/to/gomami-mcp/src/gomami_mcp.py
```

4. In a new session, ask your assistant to run `verify_connection`.

Other MCP clients can use the same command with this configuration:

```json
{
  "mcpServers": {
    "gomami": {
      "command": "python3",
      "args": ["/absolute/path/to/gomami-mcp/src/gomami_mcp.py"],
      "env": { "GOMAMI_MCP_ACCESS": "read" }
    }
  }
}
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GOMAMI_MCP_ACCESS` | `read` | Access tier: `read`, `operate` or `full`. Unknown values fall back to `read`. |
| `GOMAMI_MCP_PROTECTED_SERVERS` | empty | Comma-separated server IDs that can be read but not changed. |
| `GOMAMI_API_TOKEN` | empty | Token value. Takes priority over `~/.config/gomami-mcp/token`. |

## Tools

All 29 operations in the GoMami API reference are available.

| Tier | Tools |
| --- | --- |
| `read` | `verify_connection`, `get_account`, `list_ssh_keys`, `list_servers`, `get_server`, `list_os_templates`, `list_swap_options`, `list_isos`, `list_tasks`, `get_task`, `list_resource_packs`, `get_resource_pack` |
| `operate` | All of the above, plus `get_vnc_status`, `boot_server`, `restart_server`, `shutdown_server`, `power_off_server`, `rename_server` |
| `full` | All of the above, plus `rebuild_server`, `reset_server_password`, `toggle_rescue`, `toggle_vnc`, `set_iso`, `set_boot_order`, `update_server_settings`, `add_ssh_key`, `delete_ssh_key`, `create_resource_pack_server`, `delete_resource_pack_server` |

## Safety

- Add production servers to `GOMAMI_MCP_PROTECTED_SERVERS`. This is enforced by the server and cannot be overridden by a tool call.
- State-changing tools need confirmation text, such as `REBUILD <server-id>`. This prevents mistakes, but a model can fill it in by itself.
- VNC passwords and connection tokens are never returned to the chat.
- Reset passwords are saved under `~/.config/gomami-mcp/secrets/` with mode `600`.
- Write requests are never retried automatically.

See [SECURITY.md](SECURITY.md) for details and limits.

## Known limitations

- The API reference does not say what value `set_iso` needs to eject an ISO.
- The API reference describes `GET /server/{id}/vnc` as a toggle, which looks like a typo. It is placed in the `operate` tier to be safe.
- The API is behind Cloudflare. Blocked requests are reported clearly, and this project does not try to work around them.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests use a local mock and never contact GoMami.

## License

[MIT](LICENSE)
