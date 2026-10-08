"""Independent semantic and refusal controls against a real HTTP/Sail/Nutmeg run."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pyarrow as pa  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parent.parent


class Client:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.base = json.loads(
            (ROOT / "examples/01-session-open.request.json").read_text()
        )
        self.base["context"] = {
            "graph": "research-graph",
            "snapshot": "fixture-1",
            "projection": "all-v1",
            "hierarchy": "groups-v1",
            "layout": "xy-v1",
            "selection": None,
        }
        self.base["budget"]["deadline_ms"] = 60000
        self.sid: str | None = None
        self.revision = "0"
        self.results: list[dict[str, Any]] = []

    def post(
        self, request: dict[str, Any], route: str = "/cosmolang"
    ) -> dict[str, Any]:
        with urlopen(
            Request(
                self.endpoint + route,
                data=json.dumps(request).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=90,
        ) as response:
            return dict(json.loads(response.read()))

    def request(self, op: str, params: dict[str, Any]) -> dict[str, Any]:
        request = copy.deepcopy(self.base)
        request["request_id"] = uuid.uuid4().hex
        request["command"] = {"op": op, "params": params}
        if self.sid:
            request["session_id"] = self.sid
            request["expect_revision"] = self.revision
        return request

    def call(self, op: str, params: dict[str, Any]) -> dict[str, Any]:
        result = self.post(self.request(op, params))
        if result["status"] != "ready":
            raise AssertionError(result)
        self.sid, self.revision = result["session_id"], result["revision"]
        return result

    def artifact(self, resource: dict[str, Any]) -> bytes:
        with urlopen(
            self.endpoint
            + "/objects/"
            + urlparse(resource["uri"]).netloc
            + urlparse(resource["uri"]).path,
            timeout=30,
        ) as response:
            data = response.read()
        assert len(data) == int(resource["encoded_bytes"])
        assert hashlib.sha256(data).hexdigest() == resource["sha256"]
        return data

    def view(
        self, reply: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        manifest = json.loads(self.artifact(reply["resources"][0]))
        return (
            manifest,
            pa.ipc.open_stream(self.artifact(manifest["points"]))
            .read_all()
            .to_pylist(),
            pa.ipc.open_stream(self.artifact(manifest["links"])).read_all().to_pylist(),
        )

    def passed(self, name: str, **evidence: Any) -> None:
        self.results.append({"control": name, "outcome": "passed", **evidence})


def run(endpoint: str, output: Path) -> None:
    client = Client(endpoint)
    client.call("session.open", {"renderer": "cosmograph", "dimensions": 2})
    params = json.loads((ROOT / "examples/09-view-request.request.json").read_text())[
        "command"
    ]["params"]
    params["columns"] = []
    request = client.request("view.request", params)
    reply = client.post(request)
    assert reply["status"] == "ready", reply
    client.revision = reply["revision"]
    assert client.post(request) == reply
    client.passed("idempotent_retry_before_stale_revision_check")
    changed = copy.deepcopy(request)
    changed["budget"]["max_points"] = 1
    assert client.post(changed)["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    client.passed("idempotency_payload_conflict")
    stale = client.request("session.sync", {})
    stale["expect_revision"] = "0"
    assert client.post(stale)["error"]["code"] == "REVISION_CONFLICT"
    client.passed("stale_revision_refused")
    manifest, points, links = client.view(reply)
    assert [(p["id"], p["represented_vertices"]) for p in points] == [
        ("h/a", "2"),
        ("h/b", "2"),
        ("h/c", "2"),
    ]
    assert links == [
        {"source": "h/a", "target": "h/a", "multiplicity": "2"},
        {"source": "h/a", "target": "h/b", "multiplicity": "1"},
        {"source": "h/b", "target": "h/b", "multiplicity": "1"},
        {"source": "h/b", "target": "h/c", "multiplicity": "1"},
    ]
    client.passed(
        "exact_quotient_parallel_edges_and_self_loops", points=points, links=links
    )
    expanded = client.call(
        "hierarchy.expand",
        {
            "group": {"kind": "aggregate", "id": "h/a"},
            "view_id": manifest["view_id"],
            "quality": {"membership": "complete", "edges": "complete"},
        },
    )
    _, expanded_points, expanded_links = client.view(expanded)
    assert {p["id"] for p in expanded_points} == {
        "v/research/-9007199254740993",
        "v/research/9007199254740993",
        "h/b",
        "h/c",
    }
    assert {l["source"] for l in expanded_links} | {
        l["target"] for l in expanded_links
    } <= {p["id"] for p in expanded_points}
    assert {
        "source": "v/research/9007199254740993",
        "target": "h/b",
        "multiplicity": "1",
    } in expanded_links
    client.passed(
        "expanded_incident_edges_and_lossless_signed_ids",
        points=expanded_points,
        links=expanded_links,
    )
    follow = json.loads((ROOT / "examples/14-graph-follow.request.json").read_text())[
        "command"
    ]["params"]
    selection = client.call("graph.follow", follow)["selection_handle"]
    client.base["context"]["selection"] = selection
    _, selected_points, _ = client.view(client.call("view.request", params))
    assert [(p["id"], p["represented_vertices"]) for p in selected_points] == [
        ("h/a", "2"),
        ("h/b", "1"),
    ]
    client.passed("exact_two_hop_set_reachability", points=selected_points)
    wcc_params = json.loads((ROOT / "examples/19-graph-wcc.request.json").read_text())[
        "command"
    ]["params"]
    wcc = client.call("graph.wcc", wcc_params)
    rows = (
        pa.ipc.open_stream(client.artifact(wcc["resources"][0])).read_all().to_pylist()
    )
    assert {r["id"] for r in rows} == {
        "v/research/-9007199254740993",
        "v/research/9007199254740993",
        "v/research/5",
    }
    assert len({r["component"] for r in rows}) == 1
    client.passed("native_nutmeg_wcc_exact_partition", rows=rows)
    for name, mutate, expected in (
        ("point_cap", lambda r: r["budget"].update(max_points=1), "BUDGET_EXCEEDED"),
        (
            "scan_cap",
            lambda r: r["budget"].update(max_scan_edges="0"),
            "BUDGET_EXCEEDED",
        ),
        (
            "context_pin",
            lambda r: r["context"].update(snapshot="stale"),
            "CONTEXT_MISMATCH",
        ),
    ):
        request = client.request("view.request", params)
        mutate(request)
        refusal = client.post(request)
        assert (
            refusal["status"] == "refused" and refusal["error"]["code"] == expected
        ), refusal
        client.passed(name, response=refusal)
    tools = client.post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, "/mcp")
    assert tools["result"]["tools"][0]["name"] == "cosmolang_request"
    rpc = client.post(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "cosmolang_request",
                "arguments": {"request": client.request("session.sync", {})},
            },
        },
        "/mcp",
    )
    assert json.loads(rpc["result"]["content"][0]["text"])["status"] == "ready"
    client.passed("mcp_tool_uses_same_gateway")
    close = client.request("session.close", {})
    closed = client.post(close)
    assert client.post(close) == closed
    client.passed("idempotent_close")
    output.write_text(
        json.dumps(
            {
                "observed_utc": datetime.now(timezone.utc).isoformat(),
                "results": client.results,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"cosmolang: PASSED {len(client.results)} native semantic controls")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:18767")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.endpoint, args.output)


if __name__ == "__main__":
    main()
