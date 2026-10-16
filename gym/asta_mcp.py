#!/usr/bin/env python3
"""Minimal client for the Asta MCP server (https://asta-tools.allen.ai/mcp/v1).

Fallback pathway for when the `asta` CLI token (ASTA_TOKEN) is expired: the
MCP server authenticates with a separate key, read from the `ASTA_x-api-key`
environment variable (never printed).

Usage:
    python3 asta_mcp.py <tool_name> '<json_arguments>'

Examples:
    python3 asta_mcp.py search_papers_by_relevance \
        '{"keywords": "self-driving laboratory orchestration", "limit": 15}'
    python3 asta_mcp.py snippet_search \
        '{"query": "dynamic scheduling of autonomous experiments", "limit": 10}'
    python3 asta_mcp.py get_paper \
        '{"paper_id": "DOI:10.1039/D1DD00001A", "fields": "title,year,venue,tldr"}'

Prints the tool result (JSON) to stdout.
"""
import json
import os
import sys
import urllib.request

ENDPOINT = "https://asta-tools.allen.ai/mcp/v1"


def call_tool(name: str, arguments: dict):
    key = os.environ["ASTA_x-api-key"]
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "x-api-key": key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read().decode()
    # Response is SSE ("event: message\ndata: {...}") or plain JSON.
    msg = None
    for line in body.splitlines():
        if line.startswith("data: "):
            msg = json.loads(line[len("data: "):])
    if msg is None:
        msg = json.loads(body)
    if "error" in msg:
        raise RuntimeError(msg["error"])
    result = msg["result"]
    if result.get("isError"):
        raise RuntimeError(result)
    out = []
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                out.append(json.loads(item["text"]))
            except (json.JSONDecodeError, TypeError):
                out.append(item["text"])
    return out[0] if len(out) == 1 else out


if __name__ == "__main__":
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(call_tool(tool, args), indent=2))
