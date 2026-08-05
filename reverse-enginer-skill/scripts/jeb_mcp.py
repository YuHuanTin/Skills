import argparse
import json
import re
import sys
from typing import Any

import requests


DEFAULT_MCP_URL = "http://localhost:8425/mcp"
DEFAULT_PROTOCOL_VERSION = "2025-03-26"


class JebMcpClient:
    """MCP client over the Streamable HTTP transport (2025-03-26)."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.session_id: str | None = None
        self._request_id = 0
        init = self._send(
            "initialize",
            {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "jeb-mcp-cli", "version": "1.0"},
            },
            expect_response=True,
        )
        self.server_info = init.get("serverInfo", {})
        self._send("notifications/initialized", {}, expect_response=False)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def _send(
        self, method: str, params: dict[str, Any], *, expect_response: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if expect_response:
            self._request_id += 1
            payload["id"] = self._request_id
        response = self.session.post(
            self.base_url, json=payload, headers=self._headers(), timeout=120
        )
        response.raise_for_status()
        if self.session_id is None:
            self.session_id = response.headers.get("Mcp-Session-Id")
        if not expect_response:
            return {}
        return self._extract_result(response, payload["id"])

    @staticmethod
    def _extract_result(response: requests.Response, request_id: int) -> dict[str, Any]:
        content_type = response.headers.get("Content-Type", "")
        messages: list[dict[str, Any]]
        if "text/event-stream" in content_type:
            messages = []
            for line in response.text.splitlines():
                if line.startswith("data: "):
                    try:
                        messages.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        continue
        else:
            messages = [response.json()]
        for message in messages:
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
            return message.get("result", {})
        raise RuntimeError(f"No response received for request id {request_id}")

    def close(self) -> None:
        if self.session_id:
            try:
                self.session.delete(self.base_url, headers=self._headers(), timeout=10)
            except requests.RequestException:
                pass
            self.session_id = None
        self.session.close()

    def __enter__(self) -> "JebMcpClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._send(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            expect_response=True,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._send("tools/list", {}, expect_response=True)
        return result.get("tools", [])


def _parse_scalar(raw: str) -> Any:
    raw = _strip_outer_quotes(raw)
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _strip_outer_quotes(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    return raw


def _parse_key_value_items(
    items: list[str] | None,
    *,
    parser: Any,
    option_name: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"Invalid {option_name} value: {item!r}. Expected key=value.")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid {option_name} value: {item!r}. Key cannot be empty.")
        payload[key] = parser(raw_value.strip())
    return payload


def _parse_json_value(raw: str) -> Any:
    raw = _strip_outer_quotes(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        try:
            return json.loads(_to_relaxed_json(raw))
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON value: {raw!r}") from exc


def _to_relaxed_json(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', text)

    def repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        value = match.group(2).strip()
        lowered = value.lower()
        if value.startswith(('"', "{", "[", "-")):
            return prefix + value
        if value.startswith("'") and value.endswith("'"):
            return prefix + json.dumps(value[1:-1])
        if lowered in {"true", "false", "null"}:
            return prefix + lowered
        if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
            return prefix + value
        return prefix + json.dumps(value)

    return re.sub(r'(:\s*)([^,\]\}]+)', repl, text)


def _parse_string_value(raw: str) -> str:
    return _strip_outer_quotes(raw)


def parse_key_value_args(items: list[str] | None) -> dict[str, Any]:
    return _parse_key_value_items(items, parser=_parse_scalar, option_name="--arg")


def parse_json_args(items: list[str] | None) -> dict[str, Any]:
    return _parse_key_value_items(items, parser=_parse_json_value, option_name="--arg-json")


def parse_string_args(items: list[str] | None) -> dict[str, Any]:
    return _parse_key_value_items(items, parser=_parse_string_value, option_name="--arg-str")


def parse_args_json(
    raw: str | None,
    kv_items: list[str] | None = None,
    json_items: list[str] | None = None,
    string_items: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    payload.update(parse_string_args(string_items))
    payload.update(parse_key_value_args(kv_items))
    payload.update(parse_json_args(json_items))
    if not raw:
        return payload
    if raw.startswith("@"):
        with open(raw[1:], "r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    else:
        value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Tool arguments must be a JSON object")
    payload.update(value)
    return payload


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_tools(client: JebMcpClient, _args: argparse.Namespace) -> int:
    for tool in client.list_tools():
        title = tool.get("title") or tool.get("description", "").splitlines()[0:1]
        title = title if isinstance(title, str) else (title[0] if title else "")
        print(f"{tool['name']} — {title}" if title else tool["name"])
    return 0


def cmd_tool_schema(client: JebMcpClient, args: argparse.Namespace) -> int:
    tools = {tool["name"]: tool for tool in client.list_tools()}
    tool = tools.get(args.name)
    if not tool:
        print(f"Tool not found: {args.name}", file=sys.stderr)
        return 1
    print_json(tool)
    return 0


def cmd_call(client: JebMcpClient, args: argparse.Namespace) -> int:
    result = client.call_tool(
        args.name,
        parse_args_json(args.args, args.arg, args.arg_json, args.arg_str),
    )
    if args.structured:
        payload = result.get("structuredContent", result)
    else:
        payload = result
    print_json(payload)
    return 1 if result.get("isError") else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Small CLI client for the local JEB MCP server"
    )
    parser.add_argument("--url", default=DEFAULT_MCP_URL, help="MCP base URL")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("tools", help="List available tools")

    schema_parser = subparsers.add_parser("tool-schema", help="Print a tool's JSON schema")
    schema_parser.add_argument("name", help="Tool name")

    call_parser = subparsers.add_parser("call", help="Call a tool with JSON arguments")
    call_parser.add_argument("name", help="Tool name")
    call_parser.add_argument(
        "--args",
        help="JSON object or @path/to/file.json",
    )
    call_parser.add_argument(
        "--arg",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Direct argument, repeatable. Values are auto-parsed as JSON scalars when possible.",
    )
    call_parser.add_argument(
        "--arg-json",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="PowerShell-friendly JSON argument for arrays/objects, repeatable.",
    )
    call_parser.add_argument(
        "--arg-str",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Force a literal string value, repeatable.",
    )
    call_parser.add_argument(
        "--structured",
        action="store_true",
        help="Print only structuredContent (drops the redundant stringified content block).",
    )

    return parser


COMMANDS = {
    "tools": cmd_tools,
    "tool-schema": cmd_tool_schema,
    "call": cmd_call,
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    with JebMcpClient(args.url) as client:
        return COMMANDS[args.command](client, args)


if __name__ == "__main__":
    raise SystemExit(main())