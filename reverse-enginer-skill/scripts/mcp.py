#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


DEFAULT_MCP_URL = "http://127.0.0.1:8745/mcp"
DEFAULT_TIMEOUT = 600.0


def model_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    raise TypeError(f"无法序列化 {type(value).__name__}")


def split_key_value(raw: str) -> tuple[str, str]:
    key, separator, value = raw.partition("=")
    if not separator or not key:
        raise argparse.ArgumentTypeError("参数必须使用 KEY=VALUE 格式")
    return key, value


def load_json_object(raw: str) -> dict[str, Any]:
    if raw.startswith("@"):
        value = json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    else:
        value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("tool arguments 必须是 JSON object")
    return value


def parse_tool_arguments(args: argparse.Namespace) -> dict[str, Any]:
    result = load_json_object(args.args) if args.args else {}

    for raw in args.arg:
        key, value = split_key_value(raw)
        try:
            result[key] = json.loads(value)
        except json.JSONDecodeError:
            result[key] = value

    for raw in args.arg_json:
        key, value = split_key_value(raw)
        result[key] = json.loads(value)

    for raw in args.arg_str:
        key, value = split_key_value(raw)
        result[key] = value

    return result


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


async def execute(args: argparse.Namespace) -> int:
    timeout = httpx.Timeout(args.timeout)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http_client:
        async with streamable_http_client(
            args.url,
            http_client=http_client,
            terminate_on_close=False,
        ) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=args.timeout),
            ) as session:
                await session.initialize()

                if args.command == "tools":
                    result = await session.list_tools()
                    for tool in result.tools:
                        title = tool.title
                        if not title and tool.description:
                            title = tool.description.splitlines()[0]
                        print(f"{tool.name} — {title}" if title else tool.name)
                    return 0

                if args.command == "tool-schema":
                    result = await session.list_tools()
                    tool = next((item for item in result.tools if item.name == args.name), None)
                    if tool is None:
                        print(f"Tool not found: {args.name}", file=sys.stderr)
                        return 1
                    print_json(model_to_dict(tool))
                    return 0

                if args.command == "call":
                    result = await session.call_tool(
                        args.name,
                        arguments=parse_tool_arguments(args),
                    )
                    payload = model_to_dict(result)
                    if args.structured:
                        payload = payload.get("structuredContent", payload)
                    print_json(payload)
                    return 1 if result.isError else 0

                raise ValueError(f"未知命令：{args.command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="使用 mcp SDK 通过 Streamable HTTP 调用 MCP tools",
    )
    parser.add_argument("--url", default=DEFAULT_MCP_URL, help="MCP endpoint URL")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"单次调用超时秒数，默认 {DEFAULT_TIMEOUT:g}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("tools", help="列出 tools")

    schema_parser = subparsers.add_parser("tool-schema", help="输出 tool JSON schema")
    schema_parser.add_argument("name", help="tool 名称")

    call_parser = subparsers.add_parser("call", help="调用 tool")
    call_parser.add_argument("name", help="tool 名称")
    call_parser.add_argument("--args", help="JSON object 或 @path/to/file.json")
    call_parser.add_argument(
        "--arg",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="自动按 JSON scalar 解析，可重复",
    )
    call_parser.add_argument(
        "--arg-json",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="显式 JSON 参数，可重复",
    )
    call_parser.add_argument(
        "--arg-str",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="强制使用字符串参数，可重复",
    )
    call_parser.add_argument(
        "--structured",
        action="store_true",
        help="只输出 structuredContent",
    )
    return parser


def unwrap_error(error: BaseException) -> BaseException:
    while isinstance(error, BaseExceptionGroup) and len(error.exceptions) == 1:
        error = error.exceptions[0]
    return error


def main() -> int:
    args = build_parser().parse_args()
    try:
        return asyncio.run(execute(args))
    except Exception as error:
        print(f"error: {unwrap_error(error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())