# GoMami MCP

[![Test](https://github.com/Guoqiang1006/gomami-mcp/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/Guoqiang1006/gomami-mcp/actions/workflows/test.yml)
[![Release](https://img.shields.io/github/v/release/Guoqiang1006/gomami-mcp?include_prereleases)](https://github.com/Guoqiang1006/gomami-mcp/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/github/license/Guoqiang1006/gomami-mcp)](LICENSE)

[English](README.md)

让支持 [Model Context Protocol](https://modelcontextprotocol.io) 的 AI Agent 管理你的 GoMami 服务器，包括 Claude Code、Codex、Cursor 和 VS Code。

- **默认只读：** 只有明确开启后，才能改动服务器。
- **在你的电脑上运行：** 不需要部署服务器，令牌只会发送给 GoMami。
- **没有第三方 Python 依赖：** 覆盖 GoMami API 文档中的全部 29 个接口。

> **与 GoMami 官方无关。** 这是独立的社区项目。

> **Alpha 阶段。** `verify_connection`、`get_account` 和 `list_servers` 已用真实 API 测试。其他工具，包括所有会改动服务器的工具，都只在本地模拟接口上测试过，请先在可以清空的服务器上试用。

## 可以这样问

- “列出我的 GoMami 服务器和 IP 地址。”
- “这台服务器当前的流量周期什么时候结束？”
- “看看这台服务器最近的任务，有没有失败的？”
- “这台服务器可以重装哪些系统？”

## 支持的 Agent

只要 Agent 能通过 stdio 启动本地 MCP 服务，就应该可以使用。

| Agent | 状态 |
| --- | --- |
| Claude Code | 已用真实 API 测试 |
| 官方 MCP Python SDK | 已测试协议兼容性 |
| Codex | 应该可用，尚未实测 |
| Cursor | 应该可用，尚未实测 |
| VS Code | 应该可用，尚未实测 |
| Claude Desktop | 应该可用，尚未实测 |
| DeepSeek Harness | 应该可通过其 MCP 客户端插件使用，尚未实测 |
| 只能连接远程 HTTP 服务的网页版 Agent | 不支持 |

如果你在其他 Agent 上试过，欢迎到 [Discussions](https://github.com/Guoqiang1006/gomami-mcp/discussions) 分享结果。

## 快速开始

你需要 macOS 或 Linux、Python 3.10 或更新版本、[uv](https://docs.astral.sh/uv/) 和 GoMami API 令牌。

### 1. 创建令牌

登录 `gomami.io`，打开 [创建 API Token](https://gomami.io/createapi.php)。令牌拥有整个账户的权限，只显示一次。

### 2. 保存令牌

运行下面的命令，粘贴令牌（屏幕不会显示），再按回车：

```bash
(umask 077; mkdir -p ~/.config/gomami-mcp; IFS= read -rs t; printf '%s\n' "$t" > ~/.config/gomami-mcp/token; unset t)
```

### 3. 接入 Agent

从下面选择对应的配置，然后新开一个会话。

### 4. 测试连接

让 Agent 调用 `verify_connection`。

## Agent 配置

桌面应用可能找不到 `uvx`。如果服务启动失败，请把 `uvx` 换成 `command -v uvx` 输出的完整路径。

### Claude Code

```bash
claude mcp add gomami --scope user -- uvx --from git+https://github.com/Guoqiang1006/gomami-mcp.git@v0.1.0 gomami-mcp
```

### Codex

添加到 `~/.codex/config.toml`：

```toml
[mcp_servers.gomami]
command = "uvx"
args = ["--from", "git+https://github.com/Guoqiang1006/gomami-mcp.git@v0.1.0", "gomami-mcp"]
env = { GOMAMI_MCP_ACCESS = "read" }
startup_timeout_sec = 60
```

### Cursor

添加到 `~/.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "gomami": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Guoqiang1006/gomami-mcp.git@v0.1.0", "gomami-mcp"],
      "env": { "GOMAMI_MCP_ACCESS": "read" }
    }
  }
}
```

### VS Code

添加到 `.vscode/mcp.json`：

```json
{
  "servers": {
    "gomami": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Guoqiang1006/gomami-mcp.git@v0.1.0", "gomami-mcp"],
      "env": { "GOMAMI_MCP_ACCESS": "read" }
    }
  }
}
```

### Claude Desktop

添加到 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "gomami": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Guoqiang1006/gomami-mcp.git@v0.1.0", "gomami-mcp"],
      "env": { "GOMAMI_MCP_ACCESS": "read" }
    }
  }
}
```

### 其他 Agent

用下面的命令配置本地 stdio 服务：

```bash
uvx --from git+https://github.com/Guoqiang1006/gomami-mcp.git@v0.1.0 gomami-mcp
```

DeepSeek Harness 可以在 `@deepseek-ai/dsh-mcp-client` 插件中使用这条命令。

## 设置

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `GOMAMI_MCP_ACCESS` | `read` | 权限级别：`read`、`operate` 或 `full`。无法识别的值按 `read` 处理。 |
| `GOMAMI_MCP_PROTECTED_SERVERS` | 空 | 逗号分隔的服务器 ID，这些服务器只能查询，不能改动。 |
| `GOMAMI_API_TOKEN` | 空 | 令牌内容，优先于 `~/.config/gomami-mcp/token`。 |

## 工具

| 权限 | 工具 |
| --- | --- |
| `read` | `verify_connection`、`get_account`、`list_ssh_keys`、`list_servers`、`get_server`、`list_os_templates`、`list_swap_options`、`list_isos`、`list_tasks`、`get_task`、`list_resource_packs`、`get_resource_pack` |
| `operate` | 以上全部，加 `get_vnc_status`、`boot_server`、`restart_server`、`shutdown_server`、`power_off_server`、`rename_server` |
| `full` | 以上全部，加 `rebuild_server`、`reset_server_password`、`toggle_rescue`、`toggle_vnc`、`set_iso`、`set_boot_order`、`update_server_settings`、`add_ssh_key`、`delete_ssh_key`、`create_resource_pack_server`、`delete_resource_pack_server` |

## 安全

- **保护生产服务器：** 请把它们加入 `GOMAMI_MCP_PROTECTED_SERVERS`。无论使用哪个 Agent，MCP 服务都会执行这份名单。
- **不要只依赖确认弹窗：** Agent 执行工具前是否询问你，取决于它自己的设计和设置。
- **确认文本只能防止误操作：** 改动服务器的工具需要填写确认文本，例如 `REBUILD <服务器ID>`，但模型可以自己填写。
- **敏感信息不进入对话：** VNC 凭据会被隐藏，重置后的密码保存在 `~/.config/gomami-mcp/secrets/`，文件权限为 `600`。
- **写操作不会自动重试。**

更多说明见 [SECURITY.md](SECURITY.md)。

## 已知限制

- 不支持 Windows。
- API 文档没有说明 `set_iso` 弹出 ISO 时应填什么。
- API 文档把 `GET /server/{id}/vnc` 描述成切换操作，看起来是笔误。为稳妥起见，它放在 `operate` 权限。
- API 位于 Cloudflare 之后。请求被拦截时会明确提示，本项目不会尝试绕过。

## 开发

```bash
python3 -m unittest discover -s tests -v
```

测试使用本地模拟接口，不会访问 GoMami。

## 许可证

[MIT](LICENSE)
