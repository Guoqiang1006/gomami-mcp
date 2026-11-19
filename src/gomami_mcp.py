#!/usr/bin/env python3
"""Unofficial MCP server for the GoMami customer API and other VirtFusion panels. Standard library only."""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

__version__ = "0.2.0"

API_BASE = "https://cp.gomami.io/api"
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REDACTED = "[hidden; view it in the control panel]"
SENSITIVE_KEY = re.compile(r"password|passphrase|secret|token|^wss$", re.IGNORECASE)
TIERS = ("read", "operate", "full")
SAFE_ID = r"^[A-Za-z0-9_-]{1,64}$"


class ToolError(Exception):
    """A failure the calling model should see as a tool result."""


# --- Tool table ------------------------------------------------------------

SERVER_ID = {"type": "string", "pattern": SAFE_ID, "description": "Server ID (UUID) from list_servers"}
RESULTS = {"type": "integer", "minimum": 1, "maximum": 200, "description": "Results per page (default 20, max 200)"}
PAGE = {"type": "integer", "minimum": 1, "description": "Page number, starting at 1"}


def _check_build(args: dict[str, Any]) -> None:
    if args["method"] == "template" and "templateId" not in args:
        raise ToolError("templateId is required when method is template. Use list_os_templates to find one.")


def _check_settings(args: dict[str, Any]) -> None:
    if "autoConfiguration" not in args and "bootType" not in args:
        raise ToolError("Provide at least one of autoConfiguration or bootType.")


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    tier: str
    method: str
    path: str
    props: dict[str, dict[str, Any]] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    query: tuple[str, ...] = ()
    body: tuple[str, ...] = ()
    confirm: str | None = None
    destructive: bool = True
    check: Callable[[dict[str, Any]], None] | None = None

    @property
    def read_only(self) -> bool:
        return self.tier == "read"

    def input_schema(self) -> dict[str, Any]:
        props = dict(self.props)
        required = list(self.required)
        if self.confirm:
            props["confirm"] = {
                "type": "string",
                "description": f"Confirmation text. Must exactly match: {self.confirm}",
            }
            required.append("confirm")
        return {"type": "object", "properties": props, "required": required, "additionalProperties": False}

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema(),
            "annotations": {
                "title": self.title,
                "readOnlyHint": self.read_only,
                "destructiveHint": False if self.read_only else self.destructive,
                "idempotentHint": self.read_only,
                "openWorldHint": True,
            },
        }


def _server_read(name: str, title: str, description: str, suffix: str) -> Tool:
    return Tool(name, title, description, "read", "GET", f"/server/{{serverId}}/{suffix}",
                {"serverId": SERVER_ID}, ("serverId",))


def _power(name: str, title: str, description: str, suffix: str, destructive: bool = True) -> Tool:
    return Tool(name, title, description, "operate", "POST", f"/server/{{serverId}}/{suffix}",
                {"serverId": SERVER_ID}, ("serverId",), confirm="{serverId}", destructive=destructive)


TOOLS: tuple[Tool, ...] = (
    # Read only.
    Tool("verify_connection", "Verify connection", "Check that the API is reachable and the token is valid.",
         "read", "GET", "/connect"),
    Tool("get_account", "Account", "Read the account name, email address and timezone.", "read", "GET", "/account"),
    Tool("list_ssh_keys", "SSH keys", "List the SSH public keys on the account.", "read", "GET", "/account/sshKeys",
         {"results": RESULTS, "page": PAGE}, query=("results", "page")),
    Tool("list_servers", "Servers", "List the servers on the account.", "read", "GET", "/server",
         {"results": RESULTS, "page": PAGE}, query=("results", "page")),
    Tool("get_server", "Server details",
         "Read a server's configuration, network and traffic period. Set state=true to include its live state.",
         "read", "GET", "/server/{serverId}",
         {"serverId": SERVER_ID, "state": {"type": "boolean", "description": "Include the live server state"}},
         ("serverId",), query=("state",)),
    _server_read("list_os_templates", "OS templates", "List the OS templates available for a rebuild.",
                 "operatingSystemTemplates"),
    _server_read("list_swap_options", "Swap options", "List the swap sizes available for a rebuild.", "swap"),
    _server_read("list_isos", "ISOs", "List the ISO images available to this server.", "isos"),
    Tool("list_tasks", "Tasks", "List a server's recent tasks.", "read", "GET", "/server/{serverId}/tasks",
         {"serverId": SERVER_ID, "results": {"type": "integer", "minimum": 1, "description": "Results per page"},
          "page": PAGE},
         ("serverId",), query=("results", "page")),
    Tool("get_task", "Task details", "Read the status of one task.", "read", "GET", "/server/{serverId}/task/{taskId}",
         {"serverId": SERVER_ID, "taskId": {"type": "string", "pattern": SAFE_ID, "description": "Task ID"}},
         ("serverId", "taskId")),
    Tool("list_resource_packs", "Resource packs", "List resource packs and their usage.", "read", "GET", "/resourcePack"),
    Tool("get_resource_pack", "Resource pack details",
         "Read a resource pack's options, including the createId values needed to create a server.",
         "read", "GET", "/resourcePack/{resourcePackId}",
         {"resourcePackId": {"type": "integer", "minimum": 1, "description": "Resource pack ID"}},
         ("resourcePackId",)),

    # Day-to-day operations.
    Tool("get_vnc_status", "VNC status",
         "Read whether VNC is enabled, with its address and port. The password and connection token are hidden.",
         "operate", "GET", "/server/{serverId}/vnc", {"serverId": SERVER_ID}, ("serverId",), destructive=False),
    _power("boot_server", "Boot server", "Start the server.", "boot", destructive=False),
    _power("restart_server", "Restart server", "Restart the server. Running services are briefly interrupted.", "restart"),
    _power("shutdown_server", "Shut down server", "Shut the server down cleanly. Services stay down until it is booted.",
           "shutdown"),
    _power("power_off_server", "Power off server", "Cut power immediately. Data not yet written to disk may be lost.",
           "powerOff"),
    Tool("rename_server", "Rename server", "Change the server's display name in the control panel.", "operate", "PUT",
         "/server/{serverId}/name",
         {"serverId": SERVER_ID, "name": {"type": "string", "minLength": 1, "maxLength": 255, "description": "New name"}},
         ("serverId", "name"), body=("name",), confirm="{serverId}", destructive=False),

    # High-risk operations.
    Tool("rebuild_server", "Rebuild server", "Rebuild the server. All data on its disk is permanently erased.", "full",
         "POST", "/server/{serverId}/build",
         {
             "serverId": SERVER_ID,
             "method": {"type": "string", "enum": ["template", "self"], "description": "Install method"},
             "templateId": {"type": "integer", "description": "OS template ID. Required when method is template"},
             "name": {"type": "string", "description": "Server name"},
             "hostname": {"type": "string", "description": "Hostname"},
             "sshKeys": {"type": "array", "items": {"type": "integer"}, "description": "SSH key IDs"},
             "swap": {"type": "integer", "description": "Swap value from list_swap_options"},
             "ipv6": {"type": "boolean", "description": "Enable IPv6"},
             "timezone": {"type": "string", "description": "Timezone, for example America/Los_Angeles"},
             "userData": {"type": "string", "description": "cloud-init user_data"},
         },
         ("serverId", "method"),
         body=("method", "templateId", "name", "hostname", "sshKeys", "swap", "ipv6", "timezone", "userData"),
         confirm="REBUILD {serverId}", check=_check_build),
    Tool("reset_server_password", "Reset server password",
         "Reset the server's login password. The new password is saved to a private local file, not returned to the chat.",
         "full", "POST", "/server/{serverId}/resetPassword", {"serverId": SERVER_ID}, ("serverId",),
         confirm="RESET_PASSWORD {serverId}"),
    Tool("toggle_rescue", "Toggle rescue mode", "Turn rescue mode on or off. This changes the server's running state.",
         "full", "POST", "/server/{serverId}/rescue", {"serverId": SERVER_ID}, ("serverId",),
         confirm="RESCUE {serverId}"),
    Tool("toggle_vnc", "Toggle VNC", "Turn the VNC console on or off. When on, the console is reachable over the network.",
         "full", "POST", "/server/{serverId}/vnc", {"serverId": SERVER_ID}, ("serverId",), confirm="VNC {serverId}"),
    Tool("set_iso", "Insert or eject ISO",
         "Change ISO media by ISO ID or remote URL. The API reference does not say what value ejects an ISO.",
         "full", "POST", "/server/{serverId}/iso",
         {"serverId": SERVER_ID, "iso": {"type": "string", "minLength": 1, "description": "ISO ID or remote ISO URL"}},
         ("serverId", "iso"), body=("iso",), confirm="ISO {serverId}"),
    Tool("set_boot_order", "Set boot order", "Set the disk and CD-ROM boot order.", "full", "POST",
         "/server/{serverId}/bootOrder",
         {"serverId": SERVER_ID,
          "order": {"type": "string", "enum": ["hdd,cdrom", "cdrom,hdd"], "description": "Boot order"}},
         ("serverId", "order"), body=("order",), confirm="BOOT_ORDER {serverId}"),
    Tool("update_server_settings", "Update server settings",
         "Change the boot type or auto-configuration. A wrong value can stop the server from booting.",
         "full", "PUT", "/server/{serverId}/settings",
         {
             "serverId": SERVER_ID,
             "autoConfiguration": {"type": "boolean", "description": "Enable auto-configuration"},
             "bootType": {"type": "string", "enum": ["uefi", "bios"], "description": "Boot type"},
         },
         ("serverId",), body=("autoConfiguration", "bootType"), confirm="SETTINGS {serverId}", check=_check_settings),
    Tool("add_ssh_key", "Add SSH key", "Add an SSH public key to the account.", "full", "POST", "/account/sshKeys",
         {
             "name": {"type": "string", "pattern": r"^[^\r\n]{1,100}$", "description": "Key name"},
             "publicKey": {"type": "string", "minLength": 1, "description": "SSH public key"},
         },
         ("name", "publicKey"), body=("name", "publicKey"), confirm="ADD_SSH_KEY {name}"),
    Tool("delete_ssh_key", "Delete SSH key", "Delete an SSH public key from the account.", "full", "DELETE",
         "/account/sshKeys/{sshKeyId}",
         {"sshKeyId": {"type": "string", "pattern": SAFE_ID, "description": "SSH key ID"}}, ("sshKeyId",),
         confirm="DELETE_SSH_KEY {sshKeyId}"),
    Tool("create_resource_pack_server", "Create server", "Create a server from a resource pack. This uses pack quota.",
         "full", "POST", "/resourcePack/{resourcePackId}/{createId}",
         {
             "resourcePackId": {"type": "integer", "minimum": 1, "description": "Resource pack ID"},
             "createId": {"type": "string", "pattern": SAFE_ID, "description": "createId from get_resource_pack"},
             "cpuCores": {"type": "integer", "minimum": 1, "description": "CPU cores, for variable plans only"},
             "memory": {"type": "integer", "minimum": 1, "description": "Memory, for variable plans only"},
             "storage": {"type": "integer", "minimum": 1, "description": "Storage, for variable plans only"},
         },
         ("resourcePackId", "createId"), body=("cpuCores", "memory", "storage"),
         confirm="CREATE_SERVER {resourcePackId} {createId}"),
    Tool("delete_resource_pack_server", "Delete server",
         "Delete a server created from a resource pack. Its data cannot be recovered.", "full", "DELETE",
         "/resourcePack/{serverId}", {"serverId": SERVER_ID}, ("serverId",), confirm="DELETE_SERVER {serverId}"),
)
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


# --- Argument validation ---------------------------------------------------

def _matches_type(value: Any, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, {"string": str, "boolean": bool, "array": list}[expected])


def _validate_value(name: str, value: Any, schema: dict[str, Any]) -> None:
    if not _matches_type(value, schema["type"]):
        raise ToolError(f"Argument {name} must be of type {schema['type']}.")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolError(f"Argument {name} must be one of: {', '.join(schema['enum'])}.")
    if "minimum" in schema and value < schema["minimum"]:
        raise ToolError(f"Argument {name} must be at least {schema['minimum']}.")
    if "maximum" in schema and value > schema["maximum"]:
        raise ToolError(f"Argument {name} must be at most {schema['maximum']}.")
    if "minLength" in schema and len(value) < schema["minLength"]:
        raise ToolError(f"Argument {name} must not be empty.")
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        raise ToolError(f"Argument {name} is too long.")
    if "pattern" in schema and not re.fullmatch(schema["pattern"].strip("^$"), value):
        raise ToolError(f"Argument {name} has an invalid format.")
    if schema["type"] == "array":
        for item in value:
            _validate_value(f"{name}[]", item, schema["items"])


def validate_arguments(tool: Tool, args: dict[str, Any]) -> None:
    schema = tool.input_schema()
    unknown = sorted(set(args) - set(schema["properties"]))
    if unknown:
        raise ToolError(f"Unsupported arguments: {', '.join(unknown)}.")
    missing = [name for name in schema["required"] if name not in args]
    if missing:
        raise ToolError(f"Missing arguments: {', '.join(missing)}.")
    for name, value in args.items():
        _validate_value(name, value, schema["properties"][name])
    if tool.check:
        tool.check(args)


# --- Output handling -------------------------------------------------------

def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: REDACTED if SENSITIVE_KEY.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def save_secret(directory: Path, filename: str, secret: str) -> Path:
    if os.name != "posix":
        raise ToolError("Saving a reset password needs POSIX file permissions, so the request was not sent.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = directory / filename
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(secret + "\n")
    return path


# --- HTTP client -----------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward the bearer token to another location."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class GomamiClient:
    def __init__(self, token_loader: Callable[[], str], base_url: str = API_BASE):
        self._token_loader = token_loader
        self._base_url = base_url.rstrip("/")
        self._host = urllib.parse.urlsplit(self._base_url).hostname or "the API"
        self._opener = urllib.request.build_opener(_NoRedirect)

    def request(self, method: str, path: str, query: dict[str, Any], body: dict[str, Any] | None) -> Any:
        url = self._base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(
                {k: str(v).lower() if isinstance(v, bool) else v for k, v in query.items()}
            )
        data = b"" if method in ("POST", "PUT") else None
        if body:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self._token_loader()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"gomami-mcp/{__version__}",
        })
        try:
            with self._opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                return self._parse_success(response.status, response.headers, response.read(MAX_RESPONSE_BYTES + 1))
        except urllib.error.HTTPError as error:
            with error:
                raise ToolError(self._describe_error(error.code, error.headers, error.read(MAX_RESPONSE_BYTES))) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            hint = "" if method == "GET" else " The action may have been submitted. Check list_tasks before retrying."
            raise ToolError(f"Could not reach {self._host}: {reason}.{hint}") from None

    @staticmethod
    def _parse_success(status: int, headers: Any, raw: bytes) -> Any:
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ToolError("The API response was too large, so reading stopped.")
        if not raw.strip():  # GET /connect answers 200 with an empty text/html body.
            return {"ok": True, "status": status}
        if "text/html" in (headers.get("Content-Type") or "").lower():
            raise ToolError("The API returned a web page instead of JSON. Cloudflare may have blocked the request.")
        try:
            return json.loads(raw)
        except ValueError:
            return {"ok": True, "status": status, "body": raw[:500].decode("utf-8", "replace")}

    @staticmethod
    def _describe_error(status: int, headers: Any, raw: bytes) -> str:
        content_type = (headers.get("Content-Type") or "").lower()
        if headers.get("cf-mitigated") or "text/html" in content_type and status in (403, 429, 503):
            return f"Cloudflare blocked the request (HTTP {status}). This is not a token or argument problem."
        detail = ""
        try:
            errors = json.loads(raw).get("errors")
            if isinstance(errors, list):
                detail = "; ".join(str(item) for item in errors)
            elif errors:
                detail = str(errors)
        except (ValueError, AttributeError):
            pass
        messages = {
            401: "The token is missing, invalid or expired (HTTP 401).",
            404: "The resource does not exist or is not on this account (HTTP 404).",
            409: "The server's current state does not allow this action. A task may be running (HTTP 409).",
            422: "The API rejected these arguments (HTTP 422).",
            503: "The API is temporarily unavailable (HTTP 503).",
        }
        if status == 429:
            message = f"Too many requests (HTTP 429). Limit resets at: {headers.get('X-RateLimit-Reset') or 'unknown'}."
        elif status in (301, 302, 303, 307, 308):
            message = f"The API returned a redirect (HTTP {status}). It was not followed, to protect the token."
        else:
            message = messages.get(status, f"The API returned an error (HTTP {status}).")
        return f"{message} {detail}".strip()


# --- Token loading ---------------------------------------------------------

def parse_api_base(value: str) -> str:
    """Return a normalised panel API URL, or raise ValueError.

    Only HTTPS is accepted, so the bearer token is never sent in clear text.
    """
    url = value.strip().rstrip("/")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("GOMAMI_API_BASE must be an https:// URL, for example https://cp.example.com/api")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("GOMAMI_API_BASE must not contain credentials, a query string or a fragment")
    return url


def load_token(environ: dict[str, str], token_file: Path) -> str:
    token = environ.get("GOMAMI_API_TOKEN", "").strip()
    if not token:
        try:
            mode = token_file.stat().st_mode
        except FileNotFoundError:
            raise ToolError(f"No token configured. Set GOMAMI_API_TOKEN or save the token to {token_file}.") from None
        if os.name == "posix" and stat.S_IMODE(mode) & 0o077:
            raise ToolError(f"The token file is too permissive. Run: chmod 600 {token_file}")
        token = token_file.read_text(encoding="utf-8").strip()
    if not token or re.search(r"\s", token):
        raise ToolError("The token is empty or malformed.")
    return token


# --- Tool execution --------------------------------------------------------

class GomamiService:
    def __init__(self, client: GomamiClient, access: str, protected: set[str], config_dir: Path):
        self.client = client
        self.access = access
        self.protected = protected
        self.config_dir = config_dir

    def enabled(self, tool: Tool) -> bool:
        return TIERS.index(tool.tier) <= TIERS.index(self.access)

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.describe() for tool in TOOLS if self.enabled(tool)]

    def call(self, tool: Tool, args: dict[str, Any]) -> Any:
        if not self.enabled(tool):
            raise ToolError(f"{tool.name} requires GOMAMI_MCP_ACCESS={tool.tier}. Current access: {self.access}.")
        validate_arguments(tool, args)
        if tool.confirm:
            expected = tool.confirm.format(**args)
            if args["confirm"] != expected:
                raise ToolError(f"Confirmation text did not match, so nothing was done. Expected: {expected}")
            server_id = str(args.get("serverId", "")).lower()
            if server_id in self.protected:
                raise ToolError(f"Server {args['serverId']} is in GOMAMI_MCP_PROTECTED_SERVERS. Refused {tool.name}.")
        if tool.name == "reset_server_password" and os.name != "posix":
            raise ToolError("reset_server_password needs POSIX file permissions, so the request was not sent.")

        path = re.sub(r"\{(\w+)\}", lambda m: urllib.parse.quote(str(args[m.group(1)]), safe=""), tool.path)
        query = {name: args[name] for name in tool.query if name in args}
        body = {name: args[name] for name in tool.body if name in args}
        result = self.client.request(tool.method, path, query, body or None)
        if tool.name == "reset_server_password":
            result = self._store_reset_password(args["serverId"], result)
        return redact(result)

    def _store_reset_password(self, server_id: str, result: Any) -> Any:
        data = result.get("data") if isinstance(result, dict) else None
        password = data.pop("expectedPassword", None) if isinstance(data, dict) else None
        if isinstance(password, str) and password:
            path = save_secret(self.config_dir / "secrets", f"reset-password-{server_id}.txt", password)
            data["credentialFile"] = str(path)
        return result


# --- MCP over stdio --------------------------------------------------------

def _text_result(payload: Any, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class McpServer:
    def __init__(self, service: GomamiService, panel: str = "GoMami"):
        self.service = service
        self.panel = panel

    def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            requested = params.get("protocolVersion")
            return {
                "protocolVersion": requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "gomami", "title": "GoMami (unofficial)", "version": __version__},
                "instructions": (
                    f"Manages {self.panel} servers. Current access: {self.service.access}. "
                    "These servers may run production services. Before any action that changes a server, "
                    "explain the impact to the user and get their agreement."
                ),
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.service.list_tools()}
        if method == "tools/call":
            return self._call_tool(params)
        raise RpcError(-32601, f"Method not found: {method}")

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        tool = TOOLS_BY_NAME.get(params.get("name"))
        args = params.get("arguments", {})
        if tool is None:
            raise RpcError(-32602, f"Unknown tool: {params.get('name')}")
        if not isinstance(args, dict):
            raise RpcError(-32602, "arguments must be an object")
        try:
            return _text_result(self.service.call(tool, args))
        except ToolError as error:
            return _text_result(str(error), is_error=True)
        except OSError as error:
            return _text_result(f"Local file operation failed: {error.strerror or type(error).__name__}", is_error=True)

    def handle_line(self, line: bytes) -> dict[str, Any] | None:
        try:
            message = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if not isinstance(message, dict):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        method = message.get("method")
        if method is None and ("result" in message or "error" in message):
            return None
        if "id" not in message:
            return None
        request_id = message["id"]
        try:
            params = message.get("params", {})
            if not isinstance(method, str):
                raise RpcError(-32600, "Invalid Request")
            if not isinstance(params, dict):
                raise RpcError(-32602, "params must be an object")
            return {"jsonrpc": "2.0", "id": request_id, "result": self.dispatch(method, params)}
        except RpcError as error:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": error.code, "message": error.message}}
        except Exception as error:  # Keep the server alive; never echo request data.
            print(f"gomami-mcp: internal error: {type(error).__name__}", file=sys.stderr)
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": "Internal error"}}

    def serve(self, stdin: Any, stdout: Any) -> None:
        for line in stdin:
            if not line.strip():
                continue
            response = self.handle_line(line)
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
                stdout.flush()


def default_token_name(base: str) -> str:
    """GoMami keeps the original file name; any other panel gets its own file, so tokens never cross."""
    return "token" if base == API_BASE else f"token-{urllib.parse.urlsplit(base).hostname}"


def _refuse(message: str) -> Callable[[], str]:
    def loader() -> str:
        raise ToolError(message)
    return loader


def panel_label(environ: dict[str, str]) -> str:
    """Name shown to the agent: GoMami by default, otherwise the panel's host name."""
    try:
        base = parse_api_base(environ.get("GOMAMI_API_BASE", "") or API_BASE)
    except ValueError:
        return "VirtFusion"
    host = urllib.parse.urlsplit(base).hostname or ""
    return "GoMami" if base == API_BASE else host


def build_service(environ: dict[str, str]) -> GomamiService:
    access = environ.get("GOMAMI_MCP_ACCESS", "read").strip().lower() or "read"
    if access not in TIERS:
        print("gomami-mcp: unknown GOMAMI_MCP_ACCESS, falling back to read", file=sys.stderr)
        access = "read"
    config_dir = Path.home() / ".config" / "gomami-mcp"
    protected = {item.strip().lower() for item in environ.get("GOMAMI_MCP_PROTECTED_SERVERS", "").split(",") if item.strip()}
    try:
        base = parse_api_base(environ.get("GOMAMI_API_BASE", "") or API_BASE)
    except ValueError as error:
        # Never fall back to the default panel: that would send this token to the wrong company.
        print(f"gomami-mcp: {error}", file=sys.stderr)
        return GomamiService(GomamiClient(_refuse(f"{error}. No request was sent."), API_BASE), access, protected, config_dir)
    token_file = Path(environ.get("GOMAMI_TOKEN_FILE", "").strip() or config_dir / default_token_name(base)).expanduser()
    client = GomamiClient(lambda: load_token(environ, token_file), base)
    return GomamiService(client, access, protected, config_dir)


def main() -> None:
    environ = dict(os.environ)
    McpServer(build_service(environ), panel_label(environ)).serve(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    main()
