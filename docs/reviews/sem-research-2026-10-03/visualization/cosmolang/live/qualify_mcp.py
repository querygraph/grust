"""Real MCP SDK client against the stdio transport and native provider."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def qualify(fixture: Path, output: Path, endpoint: str) -> None:
    source = Path(__file__).resolve().parent
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            str(source / "server.py"),
            "--stdio",
            "--endpoint",
            endpoint,
            "--vertices",
            str(fixture / "vertices.parquet"),
            "--edges",
            str(fixture / "edges.parquet"),
            "--catalog",
            str(fixture / "catalog.json"),
            "--output",
            str(output.parent / "mcp-objects"),
        ],
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        initialized = await session.initialize()
        tools = await session.list_tools()
        assert [tool.name for tool in tools.tools] == ["cosmolang_request"]
        request = json.loads(
            (source.parent / "examples/01-session-open.request.json").read_text()
        )
        request["request_id"] = "mcp-open"
        catalog = json.loads((fixture / "catalog.json").read_text())
        request["context"] = {
            key: catalog[key]
            for key in ("graph", "snapshot", "projection", "hierarchy", "layout")
        }
        request["context"]["selection"] = None
        reply = await session.call_tool("cosmolang_request", {"request": request})
        assert not reply.is_error
        content = reply.content[0]
        assert content.type == "text"
        opened = json.loads(content.text)
        assert opened["status"] == "ready"
        view_params = json.loads(
            (source.parent / "examples/09-view-request.request.json").read_text()
        )["command"]["params"]
        view_params["columns"] = []
        request["budget"]["deadline_ms"] = 60000
        request.update(
            request_id="mcp-view",
            session_id=opened["session_id"],
            expect_revision=opened["revision"],
            command={"op": "view.request", "params": view_params},
        )
        view_result = await session.call_tool("cosmolang_request", {"request": request})
        assert not view_result.is_error
        view_content = view_result.content[0]
        assert view_content.type == "text"
        view_reply = json.loads(view_content.text)
        artifact = await session.read_resource(view_reply["resources"][0]["uri"])
        manifest_content = artifact.contents[0]
        assert hasattr(manifest_content, "text")
        assert json.loads(manifest_content.text)["counts"]["points"] == "3"
        opened["revision"] = view_reply["revision"]
        request.update(
            request_id="mcp-close",
            session_id=opened["session_id"],
            expect_revision=opened["revision"],
            command={"op": "session.close", "params": {}},
        )
        assert not (
            await session.call_tool("cosmolang_request", {"request": request})
        ).is_error
        output.write_text(
            json.dumps(
                {
                    "observed_utc": datetime.now(timezone.utc).isoformat(),
                    "outcome": "passed",
                    "protocol": initialized.protocol_version,
                    "controls": [
                        "initialize",
                        "tools/list",
                        "tools/call session.open",
                        "tools/call view.request",
                        "resources/read manifest",
                        "tools/call session.close",
                    ],
                },
                indent=2,
            )
            + "\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--endpoint", default="sc://127.0.0.1:18765")
    args = parser.parse_args()
    asyncio.run(qualify(args.fixture, args.output, args.endpoint))


if __name__ == "__main__":
    main()
