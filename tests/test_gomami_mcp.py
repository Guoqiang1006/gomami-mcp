from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gomami_mcp as gm  # noqa: E402

SERVER_ID = "6b32bae9-83e9-44f9-afd4-244f1fa27a49"

# Every operation in the API reference at cp.gomami.io/account/api (29 in total).
DOCUMENTED_OPERATIONS = {
    "GET /connect", "GET /account", "GET /account/sshKeys", "POST /account/sshKeys",
    "DELETE /account/sshKeys/{sshKeyId}", "GET /server", "GET /server/{serverId}",
    "POST /server/{serverId}/resetPassword", "PUT /server/{serverId}/name", "POST /server/{serverId}/rescue",
    "PUT /server/{serverId}/settings", "POST /server/{serverId}/bootOrder", "POST /server/{serverId}/build",
    "GET /server/{serverId}/operatingSystemTemplates", "GET /server/{serverId}/swap",
    "POST /server/{serverId}/vnc", "GET /server/{serverId}/vnc", "POST /server/{serverId}/restart",
    "POST /server/{serverId}/boot", "POST /server/{serverId}/shutdown", "POST /server/{serverId}/powerOff",
    "GET /server/{serverId}/tasks", "GET /server/{serverId}/task/{taskId}", "POST /server/{serverId}/iso",
    "GET /server/{serverId}/isos", "GET /resourcePack", "GET /resourcePack/{resourcePackId}",
    "POST /resourcePack/{resourcePackId}/{createId}", "DELETE /resourcePack/{serverId}",
}


class FakeApi(BaseHTTPRequestHandler):
    requests: list[dict] = []
    responses: dict[str, tuple[int, dict[str, str], bytes]] = {}

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        FakeApi.requests.append({
            "method": self.command, "path": self.path, "body": body,
            "auth": self.headers.get("Authorization"), "agent": self.headers.get("User-Agent"),
        })
        status, headers, payload = FakeApi.responses.get(
            f"{self.command} {self.path}", (200, {"Content-Type": "application/json"}, b'{"data":{"ok":true}}'))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def log_message(self, *args) -> None:
        pass


class ServiceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["no_proxy"] = "127.0.0.1"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self) -> None:
        FakeApi.requests = []
        FakeApi.responses = {}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def service(self, access: str = "full", protected: set[str] | None = None) -> gm.GomamiService:
        base = f"http://127.0.0.1:{self.httpd.server_address[1]}/api"
        return gm.GomamiService(gm.GomamiClient(lambda: "test-token", base), access, protected or set(), Path(self.tmp.name))

    def call(self, service: gm.GomamiService, tool_name: str, /, **args):
        return gm.McpServer(service)._call_tool({"name": tool_name, "arguments": args})


class ToolTableTests(unittest.TestCase):
    def test_every_documented_operation_has_exactly_one_tool(self) -> None:
        actual = [f"{tool.method} {tool.path}" for tool in gm.TOOLS]
        self.assertEqual(len(actual), len(set(actual)))
        self.assertEqual(set(actual), DOCUMENTED_OPERATIONS)

    def test_every_state_changing_request_needs_confirmation(self) -> None:
        for tool in gm.TOOLS:
            if tool.method != "GET":
                self.assertIsNotNone(tool.confirm, tool.name)

    def test_read_tier_only_uses_get(self) -> None:
        for tool in gm.TOOLS:
            if tool.tier == "read":
                self.assertEqual(tool.method, "GET", tool.name)

    def test_confirm_templates_only_use_required_arguments(self) -> None:
        for tool in gm.TOOLS:
            if tool.confirm:
                tool.confirm.format(**{name: "x" for name in tool.required})


class AccessTests(ServiceTestCase):
    def test_default_tier_lists_only_read_tools(self) -> None:
        names = {tool["name"] for tool in self.service("read").list_tools()}
        self.assertEqual(len(names), 12)
        self.assertNotIn("restart_server", names)
        self.assertNotIn("rebuild_server", names)

    def test_operate_tier_excludes_rebuild(self) -> None:
        names = {tool["name"] for tool in self.service("operate").list_tools()}
        self.assertEqual(len(names), 18)
        self.assertIn("restart_server", names)
        self.assertNotIn("rebuild_server", names)

    def test_disabled_tool_is_refused_without_a_request(self) -> None:
        result = self.call(self.service("read"), "restart_server", serverId=SERVER_ID, confirm=SERVER_ID)
        self.assertTrue(result["isError"])
        self.assertEqual(FakeApi.requests, [])

    def test_unknown_access_value_falls_back_to_read(self) -> None:
        self.assertEqual(gm.build_service({"GOMAMI_MCP_ACCESS": "admin"}).access, "read")

    def test_wrong_confirmation_is_refused(self) -> None:
        result = self.call(self.service(), "rebuild_server", serverId=SERVER_ID, method="self", confirm=SERVER_ID)
        self.assertTrue(result["isError"])
        self.assertEqual(FakeApi.requests, [])

    def test_protected_server_is_refused_even_with_confirmation(self) -> None:
        service = self.service(protected={SERVER_ID})
        result = self.call(service, "rebuild_server", serverId=SERVER_ID.upper(), method="self",
                           confirm=f"REBUILD {SERVER_ID.upper()}")
        self.assertTrue(result["isError"])
        self.assertEqual(FakeApi.requests, [])

    def test_protected_server_can_still_be_read(self) -> None:
        result = self.call(self.service("read", {SERVER_ID}), "get_server", serverId=SERVER_ID)
        self.assertFalse(result["isError"])


class RequestTests(ServiceTestCase):
    def test_query_and_auth_headers(self) -> None:
        result = self.call(self.service("read"), "get_server", serverId=SERVER_ID, state=True)
        self.assertFalse(result["isError"])
        request = FakeApi.requests[0]
        self.assertEqual(request["path"], f"/api/server/{SERVER_ID}?state=true")
        self.assertEqual(request["auth"], "Bearer test-token")
        self.assertTrue(request["agent"].startswith("gomami-mcp/"))

    def test_rebuild_body_excludes_path_and_confirmation(self) -> None:
        self.call(self.service(), "rebuild_server", serverId=SERVER_ID, method="template", templateId=85,
                  sshKeys=[1], confirm=f"REBUILD {SERVER_ID}")
        request = FakeApi.requests[0]
        self.assertEqual(request["path"], f"/api/server/{SERVER_ID}/build")
        self.assertEqual(json.loads(request["body"]), {"method": "template", "templateId": 85, "sshKeys": [1]})

    def test_template_rebuild_requires_template_id(self) -> None:
        result = self.call(self.service(), "rebuild_server", serverId=SERVER_ID, method="template",
                           confirm=f"REBUILD {SERVER_ID}")
        self.assertTrue(result["isError"])
        self.assertEqual(FakeApi.requests, [])

    def test_path_traversal_is_rejected(self) -> None:
        result = self.call(self.service("read"), "get_server", serverId="../account")
        self.assertTrue(result["isError"])
        self.assertEqual(FakeApi.requests, [])

    def test_boolean_is_not_accepted_as_integer(self) -> None:
        result = self.call(self.service("read"), "list_servers", results=True)
        self.assertTrue(result["isError"])

    def test_unknown_argument_is_rejected(self) -> None:
        result = self.call(self.service("read"), "list_servers", surprise=1)
        self.assertTrue(result["isError"])

    def test_connect_accepts_empty_html_response(self) -> None:
        FakeApi.responses["GET /api/connect"] = (200, {"Content-Type": "text/html; charset=utf-8"}, b"")
        result = self.call(self.service("read"), "verify_connection")
        self.assertFalse(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"]), {"ok": True, "status": 200})

    def test_no_content_response(self) -> None:
        FakeApi.responses[f"PUT /api/server/{SERVER_ID}/name"] = (204, {}, b"")
        result = self.call(self.service("operate"), "rename_server", serverId=SERVER_ID, name="LAX", confirm=SERVER_ID)
        self.assertEqual(json.loads(result["content"][0]["text"]), {"ok": True, "status": 204})


class SecretTests(ServiceTestCase):
    def test_vnc_credentials_are_hidden(self) -> None:
        payload = {"data": {"enabled": True, "ip": "192.0.2.1", "port": 5901, "password": "vnc-pass-value",
                            "wss": {"token": "wss-token-value", "url": "/vnc/?token=wss-token-value"}}}
        FakeApi.responses[f"GET /api/server/{SERVER_ID}/vnc"] = (200, {"Content-Type": "application/json"},
                                                                 json.dumps(payload).encode())
        text = self.call(self.service("operate"), "get_vnc_status", serverId=SERVER_ID)["content"][0]["text"]
        self.assertNotIn("vnc-pass-value", text)
        self.assertNotIn("wss-token-value", text)
        self.assertIn("5901", text)

    def test_reset_password_goes_to_private_file_only(self) -> None:
        payload = {"data": {"expectedPassword": "new-root-value", "task": {"id": 7, "status": "accepted"}}}
        FakeApi.responses[f"POST /api/server/{SERVER_ID}/resetPassword"] = (200, {"Content-Type": "application/json"},
                                                                            json.dumps(payload).encode())
        result = self.call(self.service(), "reset_server_password", serverId=SERVER_ID,
                           confirm=f"RESET_PASSWORD {SERVER_ID}")
        text = result["content"][0]["text"]
        self.assertNotIn("new-root-value", text)
        path = Path(json.loads(text)["data"]["credentialFile"])
        self.assertEqual(path.read_text().strip(), "new-root-value")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_token_file_with_open_permissions_is_refused(self) -> None:
        path = Path(self.tmp.name) / "token"
        path.write_text("abc\n")
        path.chmod(0o644)
        with self.assertRaises(gm.ToolError):
            gm.load_token({}, path)
        path.chmod(0o600)
        self.assertEqual(gm.load_token({}, path), "abc")

    def test_token_with_inner_whitespace_is_refused(self) -> None:
        with self.assertRaises(gm.ToolError):
            gm.load_token({"GOMAMI_API_TOKEN": "abc\r\nX-Evil: 1"}, Path(self.tmp.name) / "missing")


class ErrorTests(ServiceTestCase):
    def assert_error(self, response: tuple, expected: str) -> None:
        FakeApi.responses["GET /api/account"] = response
        result = self.call(self.service("read"), "get_account")
        self.assertTrue(result["isError"])
        self.assertIn(expected, result["content"][0]["text"])
        self.assertNotIn("test-token", result["content"][0]["text"])

    def test_invalid_token(self) -> None:
        self.assert_error((401, {}, b""), "HTTP 401")

    def test_api_error_list_is_shown(self) -> None:
        self.assert_error((422, {"Content-Type": "application/json"}, b'{"errors":["bad name"]}'), "bad name")

    def test_rate_limit_reports_reset_time(self) -> None:
        self.assert_error((429, {"X-RateLimit-Reset": "1795005999"}, b""), "1795005999")

    def test_cloudflare_challenge_is_named(self) -> None:
        self.assert_error((403, {"Content-Type": "text/html", "cf-mitigated": "challenge"}, b"<html>"), "Cloudflare")

    def test_html_success_is_an_error(self) -> None:
        self.assert_error((200, {"Content-Type": "text/html"}, b"<html>"), "Cloudflare")

    def test_redirect_is_not_followed(self) -> None:
        self.assert_error((302, {"Location": "/api/connect"}, b""), "redirect")
        self.assertEqual(len(FakeApi.requests), 1)


class ProtocolTests(unittest.TestCase):
    def exchange(self, messages: list, env: dict[str, str] | None = None) -> list[dict]:
        script = str(Path(gm.__file__).resolve())
        lines = [m if isinstance(m, str) else json.dumps(m) for m in messages]
        with tempfile.TemporaryDirectory() as home:
            full_env = {"PATH": os.environ.get("PATH", ""), "HOME": home, **(env or {})}
            done = subprocess.run([sys.executable, script], input="\n".join(lines) + "\n", env=full_env,
                                  capture_output=True, text=True, timeout=15, check=True)
        return [json.loads(line) for line in done.stdout.splitlines()]

    def test_handshake_and_tool_listing(self) -> None:
        replies = self.exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        ])
        self.assertEqual([reply["id"] for reply in replies], [1, 2, 3])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(len(replies[2]["result"]["tools"]), 12)

    def test_unknown_protocol_version_gets_latest(self) -> None:
        reply = self.exchange([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999"}}])[0]
        self.assertEqual(reply["result"]["protocolVersion"], gm.PROTOCOL_VERSIONS[0])

    def test_bad_input_keeps_server_running(self) -> None:
        replies = self.exchange(["not json", [1], {"jsonrpc": "2.0", "id": 5, "method": "nope"},
                                 {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "nope"}},
                                 {"jsonrpc": "2.0", "id": 7, "method": "ping"}])
        self.assertEqual([r.get("error", {}).get("code") for r in replies], [-32700, -32600, -32601, -32602, None])

    def test_missing_token_is_a_tool_error(self) -> None:
        reply = self.exchange([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": "verify_connection", "arguments": {}}}])[0]
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("No token configured", reply["result"]["content"][0]["text"])


class PanelUrlTests(unittest.TestCase):
    def setUp(self) -> None:
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        patcher = mock.patch.object(gm.Path, "home", return_value=Path(home.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def token_error(self, environ: dict[str, str]) -> str:
        service = gm.build_service(environ)
        with self.assertRaises(gm.ToolError) as caught:
            service.client._token_loader()
        return str(caught.exception)

    def test_default_panel_is_gomami_with_original_token_file(self) -> None:
        service = gm.build_service({})
        self.assertEqual(service.client._base_url, gm.API_BASE)
        self.assertEqual(gm.panel_label({}), "GoMami")
        self.assertTrue(self.token_error({}).rstrip(".").endswith("/token"))

    def test_custom_panel_uses_its_own_token_file(self) -> None:
        environ = {"GOMAMI_API_BASE": "https://cp.example.com/api/"}
        service = gm.build_service(environ)
        self.assertEqual(service.client._base_url, "https://cp.example.com/api")
        self.assertEqual(gm.panel_label(environ), "cp.example.com")
        self.assertTrue(self.token_error(environ).rstrip(".").endswith("/token-cp.example.com"))

    def test_token_file_can_be_set_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "panel-token"
            path.write_text("abc\n", encoding="utf-8")
            path.chmod(0o600)
            service = gm.build_service({"GOMAMI_API_BASE": "https://cp.example.com/api", "GOMAMI_TOKEN_FILE": str(path)})
            self.assertEqual(service.client._token_loader(), "abc")

    def test_invalid_panel_url_refuses_every_request(self) -> None:
        for value in ("http://cp.example.com/api", "https://user:pw@cp.example.com/api", "https://cp.example.com/api?x=1", "cp.example.com"):
            with self.subTest(value=value):
                environ = {"GOMAMI_API_BASE": value, "GOMAMI_API_TOKEN": "abc"}
                with contextlib.redirect_stderr(io.StringIO()):
                    service = gm.build_service(environ)
                result = gm.McpServer(service)._call_tool({"name": "verify_connection", "arguments": {}})
                self.assertTrue(result["isError"])
                self.assertIn("No request was sent", result["content"][0]["text"])


class ReleaseMetadataTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    def test_server_json_matches_the_package(self) -> None:
        server = json.loads((self.root / "server.json").read_text(encoding="utf-8"))
        package = server["packages"][0]
        self.assertEqual(server["version"], gm.__version__)
        self.assertEqual(package["version"], gm.__version__)
        self.assertEqual(package["identifier"], "gomami-mcp")
        self.assertLessEqual(len(server["description"]), 100)

    def test_readme_has_the_registry_ownership_marker(self) -> None:
        server = json.loads((self.root / "server.json").read_text(encoding="utf-8"))
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"<!-- mcp-name: {server['name']} -->", readme)

    def test_readmes_install_the_current_version(self) -> None:
        for name in ("README.md", "README.zh-CN.md"):
            readme = (self.root / name).read_text(encoding="utf-8")
            self.assertIn(f"gomami-mcp@{gm.__version__}", readme)


if __name__ == "__main__":
    unittest.main()
