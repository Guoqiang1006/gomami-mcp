# GoMami MCP

[English](README.md)

非官方的 [Model Context Protocol](https://modelcontextprotocol.io) 服务，让 Claude Code 等 MCP 客户端管理 GoMami 服务器。默认只读，没有第三方依赖。

> **与 GoMami 官方无关。** 这是独立的社区项目，“GoMami” 仅用于说明本工具适用的服务。

> **Alpha 阶段。** 连接验证、账户信息和服务器列表已用真实 API 测试。其他工具只在本地模拟接口上测试过，请先在可以清空的服务器上试用。

## 环境要求

- Python 3.10 或更新版本
- macOS 或 Linux
- GoMami API 令牌

## 安装

1. 登录 `gomami.io`，打开 [创建 API Token](https://gomami.io/createapi.php)。令牌拥有整个账户的权限，只显示一次。

2. 保存令牌。运行下面的命令，粘贴令牌（屏幕不会显示），再按回车：

```bash
(umask 077; mkdir -p ~/.config/gomami-mcp; IFS= read -rs t; printf '%s\n' "$t" > ~/.config/gomami-mcp/token; unset t)
```

3. 克隆本仓库，然后接入 Claude Code：

```bash
claude mcp add gomami --scope user -- python3 /绝对路径/gomami-mcp/src/gomami_mcp.py
```

4. 新开一个会话，让助手调用 `verify_connection`。

## 配置

| 环境变量 | 默认值 | 作用 |
| --- | --- | --- |
| `GOMAMI_MCP_ACCESS` | `read` | 权限级别：`read`、`operate` 或 `full`。无法识别的值按 `read` 处理。 |
| `GOMAMI_MCP_PROTECTED_SERVERS` | 空 | 逗号分隔的服务器 ID，这些服务器只能查询，不能改动。 |
| `GOMAMI_API_TOKEN` | 空 | 令牌内容，优先于 `~/.config/gomami-mcp/token`。 |

## 权限

GoMami API 文档中的 29 个接口都有对应工具。

| 权限 | 能做什么 |
| --- | --- |
| `read` | 查看连接、账户、SSH 密钥、服务器、系统模板、Swap、ISO、任务和资源包 |
| `operate` | 以上全部，加 VNC 状态、开机、重启、关机、强制断电、改名 |
| `full` | 以上全部，加重装、重置密码、救援模式、VNC 开关、ISO、启动顺序、服务器设置、增删 SSH 密钥、创建和删除服务器 |

## 安全

- 请把生产服务器加入 `GOMAMI_MCP_PROTECTED_SERVERS`。这项限制由服务端执行，工具调用无法绕过。
- 改变服务器状态的工具需要确认文本，例如 `REBUILD <服务器ID>`。它能防止误操作，但模型可以自己填写。
- VNC 密码和连接令牌不会返回到对话。
- 重置后的密码保存在 `~/.config/gomami-mcp/secrets/`，文件权限为 `600`。
- 写操作不会自动重试。

更多说明见 [SECURITY.md](SECURITY.md)。

## 已知限制

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
