"""Loopback-only HTTP and MCP JSON-RPC facade over the same Cosmolang gateway."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pyspark.sql.connect.session import SparkSession

from protocol import Gateway
from provider import Catalog, Provider

LOGGER = logging.getLogger(__name__)


class Service:
    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway
        self.lock = threading.Lock()

    def dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            try:
                return self.gateway.call(payload)
            except Exception:
                LOGGER.exception("Cosmolang provider failed")
                result = self.gateway.response(
                    payload, payload.get("session_id"), "error"
                )
                result["error"] = {
                    "code": "PROVIDER_FAILED",
                    "message": "Native provider failed; see owned server log",
                    "retryable": False,
                }
                return result

    def rpc(self, payload: dict[str, Any]) -> dict[str, Any]:
        """MCP tools carry the identical request object, never embedded graph rows."""
        method = payload.get("method")
        result: dict[str, Any]
        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "cosmolang-local", "version": "0.1.0"},
            }
        elif method == "resources/list":
            result = {"resources": []}
        elif method == "resources/read":
            uri = payload.get("params", {}).get("uri", "")
            parsed = urlparse(uri)
            found = self.gateway.resources.get(parsed.path.lstrip("/"))
            if (
                parsed.scheme != "cosmolang"
                or found is None
                or found[0] != parsed.netloc
            ):
                return {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "error": {"code": -32002, "message": "Unknown resource"},
                }
            data = found[1]
            content = (
                {"uri": uri, "mimeType": "application/json", "text": data.decode()}
                if data.startswith(b"{")
                else {
                    "uri": uri,
                    "mimeType": "application/vnd.apache.arrow.stream",
                    "blob": base64.b64encode(data).decode(),
                }
            )
            result = {"contents": [content]}
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "cosmolang_request",
                        "description": "Explore a pinned graph with Cosmolang; bounded resources are fetched separately.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"request": {"type": "object"}},
                            "required": ["request"],
                            "additionalProperties": False,
                        },
                    }
                ]
            }
        elif (
            method == "tools/call"
            and payload.get("params", {}).get("name") == "cosmolang_request"
        ):
            response = self.dispatch(payload["params"]["arguments"]["request"])
            result = {
                "content": [{"type": "text", "text": json.dumps(response)}],
                "isError": response["status"] in {"error", "refused"},
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32601, "message": "Unknown method or tool"},
            }
        return {"jsonrpc": "2.0", "id": payload.get("id"), "result": result}


def app_for(service: Service) -> FastAPI:
    app = FastAPI()

    @app.post("/cosmolang")
    async def command(request: Request) -> JSONResponse:
        raw = await request.body()
        if len(raw) > 1 << 20:
            return JSONResponse({"error": "request exceeds 1 MiB"}, status_code=413)
        try:
            payload = json.loads(raw)
        except ValueError:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        return JSONResponse(service.dispatch(payload))

    @app.post("/mcp")
    async def mcp(request: Request) -> JSONResponse:
        raw = await request.body()
        if len(raw) > 1 << 20:
            return JSONResponse({"error": "request exceeds 1 MiB"}, status_code=413)
        return JSONResponse(service.rpc(json.loads(raw)))

    @app.get("/objects/{session_id}/{handle}")
    def resource(session_id: str, handle: str) -> Response:
        with service.lock:
            found = service.gateway.resources.get(handle)
            if found is None or found[0] != session_id:
                return Response(status_code=404)
            data = found[1]
            return Response(
                data,
                media_type="application/json"
                if data.startswith(b"{")
                else "application/vnd.apache.arrow.stream",
                headers={
                    "Cache-Control": "private, immutable",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ready"}

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--vertices", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18767)
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args()
    spark = SparkSession.builder.remote(args.endpoint).create()
    try:
        provider = Provider(
            spark,
            str(args.vertices),
            str(args.edges),
            Catalog(**json.loads(args.catalog.read_text())),
        )
        service = Service(Gateway(provider, args.output))
        if args.stdio:
            for line in sys.stdin:
                if len(line) > 1 << 20:
                    continue
                message = json.loads(line)
                if "id" in message:
                    print(json.dumps(service.rpc(message)), flush=True)
            return
        uvicorn.run(
            app_for(service),
            host="127.0.0.1",
            port=args.port,
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
