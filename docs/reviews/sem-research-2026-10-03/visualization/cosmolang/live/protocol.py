"""Schema-checked local exploration gateway; immutable Arrow view artifacts."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from provider import Provider, Refusal, View
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
OPERATIONS = (
    "session.open",
    "session.sync",
    "session.close",
    "view.request",
    "hierarchy.expand",
    "hierarchy.collapse",
    "graph.follow",
    "graph.wcc",
)


@dataclass(slots=True)
class Session:
    context: dict[str, Any]
    revision: int = 0
    selections: dict[str, tuple[str, ...]] = field(default_factory=dict)
    views: dict[str, View] = field(default_factory=dict)
    replay: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)


class Gateway:
    def __init__(self, provider: Provider, output: Path) -> None:
        self.provider = provider
        self.output = output
        output.mkdir(parents=True, exist_ok=True)
        schemas = [json.loads(path.read_text()) for path in ROOT.glob("*.schema.json")]
        registry = Registry().with_resources(
            (s["$id"], Resource.from_contents(s)) for s in schemas
        )
        self.validators = {
            s["$id"].rsplit(":", 1)[1]: Draft202012Validator(s, registry=registry)
            for s in schemas
        }
        self.sessions: dict[str, Session] = {}
        self.closed: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {}
        self.opens: dict[str, tuple[str, dict[str, Any]]] = {}
        self.resources: dict[str, tuple[str, bytes]] = {}

    def resource(
        self, session_id: str, columns: dict[str, list[Any]]
    ) -> tuple[dict[str, str], int]:
        table = pa.table(
            {
                key: pa.array(
                    values, type=pa.float64() if key in {"x", "y"} else pa.string()
                )
                for key, values in columns.items()
            }
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        data = sink.getvalue().to_pybytes()
        handle = uuid.uuid4().hex
        if (
            sum(len(value[1]) for value in self.resources.values()) + len(data)
            > 64 << 20
        ):
            raise Refusal(
                "BUDGET_EXCEEDED", "local artifact store exceeds 64 MiB; close sessions"
            )
        self.resources[handle] = (session_id, data)
        return {
            "handle": handle,
            "uri": f"cosmolang://{session_id}/{handle}",
            "sha256": hashlib.sha256(data).hexdigest(),
            "encoded_bytes": str(len(data)),
            "media_type": "application/vnd.apache.arrow.stream",
        }, table.nbytes

    def response(
        self, request: dict[str, Any], session_id: str | None, status: str = "ready"
    ) -> dict[str, Any]:
        session = self.sessions.get(session_id or "")
        return {
            "cosmolang": "0.1",
            "request_id": request.get("request_id", "invalid"),
            "session_id": session_id,
            "revision": str(session.revision) if session else None,
            "context": session.context if session else None,
            "status": status,
        }

    def call(self, request: dict[str, Any]) -> dict[str, Any]:
        session_id = request.get("session_id") or ""
        try:
            self.validators["request"].validate(request)
            fingerprint = hashlib.sha256(
                json.dumps(request, sort_keys=True, allow_nan=False).encode()
            ).hexdigest()
            op = request["command"]["op"]
            replay = (
                self.opens
                if op == "session.open"
                else self.closed.get(
                    session_id, self.sessions.get(session_id, Session({})).replay
                )
            )
            if request["request_id"] in replay:
                old_hash, old_response = replay[request["request_id"]]
                if old_hash != fingerprint:
                    raise Refusal(
                        "IDEMPOTENCY_CONFLICT",
                        "request ID reused with a different payload",
                    )
                return old_response
            if op not in OPERATIONS:
                raise Refusal(
                    "UNSUPPORTED_CAPABILITY",
                    f"operation not implemented by this slice: {op}",
                )
            catalog = self.provider.catalog
            for key in ("graph", "snapshot", "projection", "hierarchy", "layout"):
                if request["context"][key] != getattr(catalog, key):
                    raise Refusal("CONTEXT_MISMATCH", f"catalog {key} differs")
            if op == "session.open":
                if (
                    request["command"]["params"]["dimensions"] != 2
                    or request["context"]["selection"] is not None
                ):
                    raise Refusal(
                        "UNSUPPORTED_CAPABILITY",
                        "open requires 2D and no existing selection",
                    )
                if len(self.sessions) >= 8 or len(self.opens) >= 64:
                    raise Refusal("BUDGET_EXCEEDED", "local session cap reached")
                session_id = uuid.uuid4().hex
                self.sessions[session_id] = Session(dict(request["context"]))
                result = self.response(request, session_id)
                result["capabilities"] = {
                    "operations": list(OPERATIONS),
                    "dimensions": [2],
                    "camera_pose3d": False,
                    "providers": ["Sail", "Nutmeg", "Cosmograph-2.5.1"],
                    "resident_point_cap": 10000,
                }
            else:
                if session_id not in self.sessions:
                    raise Refusal("NOT_FOUND", "unknown session")
                session = self.sessions[session_id]
                if request["expect_revision"] != str(session.revision):
                    raise Refusal("REVISION_CONFLICT", "stale session revision")
                if any(
                    request["context"][key] != session.context[key]
                    for key in (
                        "graph",
                        "snapshot",
                        "projection",
                        "hierarchy",
                        "layout",
                    )
                ):
                    raise Refusal("CONTEXT_MISMATCH", "session context differs")
                result = self.execute(request, session_id, session)
            result["context"] = dict(request["context"])
            self.validators["response"].validate(result)
            replay[request["request_id"]] = (fingerprint, result)
            return result
        except (Refusal, ValidationError, ValueError) as exc:
            result = self.response(request, session_id, "refused")
            result["error"] = {
                "code": exc.code if isinstance(exc, Refusal) else "INVALID_ARGUMENT",
                "message": str(exc)[:512],
                "retryable": False,
            }
            self.validators["response"].validate(result)
            return result

    def execute(
        self, request: dict[str, Any], sid: str, session: Session
    ) -> dict[str, Any]:
        op, params, budget = (
            request["command"]["op"],
            request["command"]["params"],
            request["budget"],
        )
        if op in {"session.sync", "session.close"}:
            result = self.response(request, sid)
            if op == "session.close":
                self.resources = {
                    key: value
                    for key, value in self.resources.items()
                    if value[0] != sid
                }
                self.closed[sid] = session.replay
                del self.sessions[sid]
            return result
        catalog = self.provider.catalog
        scan_factor = max(1, params.get("max_hops", 2))
        if catalog.edge_rows > 1000000 or catalog.vertex_rows > 1000000:
            raise Refusal(
                "BUDGET_EXCEEDED",
                "local slice requires a catalog shard no larger than one million vertices/edges",
            )
        if catalog.edge_rows * scan_factor > int(
            budget["max_scan_edges"]
        ) or catalog.source_bytes * scan_factor > int(budget["max_scan_bytes"]):
            raise Refusal(
                "BUDGET_EXCEEDED", "catalog scan envelope exceeds request budget"
            )
        if (
            len(session.views) >= 16
            or len(session.selections) >= 16
            or len(session.replay) >= 128
        ):
            raise Refusal(
                "BUDGET_EXCEEDED",
                "local session artifact cap reached; close the session",
            )
        if int(budget["max_working_bytes"]) < 536870912:
            raise Refusal("BUDGET_EXCEEDED", "provider requires a 512 MiB managed pool")
        start = time.monotonic()
        selection = request["context"]["selection"]
        members = session.selections.get(selection) if selection else None
        if selection and members is None:
            raise Refusal("NOT_FOUND", "unknown selection")
        if op == "graph.follow":
            if (
                params["domain"] != "projection"
                or params["vertex_predicate"] is not None
                or params["edge_predicate"] is not None
                or "ids" not in params["seeds"]
            ):
                raise Refusal(
                    "UNSUPPORTED_CAPABILITY",
                    "first follow slice supports unfiltered projection seeds by ID",
                )
            if any(seed["kind"] != "vertex" for seed in params["seeds"]["ids"]):
                raise Refusal("INVALID_ARGUMENT", "follow seeds must be vertices")
            members = self.provider.follow(
                tuple(seed["id"] for seed in params["seeds"]["ids"]),
                params["direction"],
                params["max_hops"],
                min(10000, budget["max_points"]),
            )
            if (time.monotonic() - start) * 1000 > budget["deadline_ms"]:
                raise Refusal(
                    "DEADLINE_EXCEEDED", "deadline exceeded before publishing selection"
                )
            handle = uuid.uuid4().hex
            session.selections[handle] = members
            session.revision += 1
            result = self.response(request, sid)
            result["selection_handle"] = handle
            result["result_contract"] = {
                "kind": "membership",
                "domain": "projection",
                "scope_handle": catalog.projection,
                "contract_version": "bounded-set-reachability-seeds-included-v1",
                "quality": "exact",
                "sampling_seed": None,
            }
            return result
        if op == "graph.wcc":
            if params["domain"] != "selection" or members is None:
                raise Refusal(
                    "UNSUPPORTED_CAPABILITY", "CSR WCC requires a bounded selection"
                )
            if (
                params["provider"] != "nutmeg"
                or params["contract_version"] != "source-weak-v1"
                or params["label_convention"] != "opaque"
                or params["method"]
                not in {"wcc", "wccRandomized", "wccRandomizedFused"}
            ):
                raise Refusal(
                    "UNSUPPORTED_CAPABILITY",
                    "unsupported native WCC method or label contract",
                )
            components = self.provider.components(
                members, f"cosmolang-{uuid.uuid4().hex}", params["method"]
            )
            if (time.monotonic() - start) * 1000 > budget["deadline_ms"]:
                raise Refusal(
                    "DEADLINE_EXCEEDED", "deadline exceeded before publishing WCC"
                )
            resource, decoded = self.resource(
                sid,
                {
                    "id": [row[0] for row in components],
                    "component": [row[1] for row in components],
                },
            )
            if int(resource["encoded_bytes"]) > int(
                budget["max_wire_bytes"]
            ) or decoded > int(budget["max_decoded_bytes"]):
                del self.resources[resource["handle"]]
                raise Refusal("BUDGET_EXCEEDED", "WCC artifact exceeds wire cap")
            session.revision += 1
            result = self.response(request, sid)
            result["resources"] = [resource]
            return result
        expanded: frozenset[str] = frozenset()
        if op in {"hierarchy.expand", "hierarchy.collapse"}:
            previous = session.views.get(params["view_id"])
            if previous is None:
                raise Refusal("NOT_FOUND", "unknown base view")
            group = params["group"]["id"]
            if params["group"]["kind"] != "aggregate" or not group.startswith("h/"):
                raise Refusal("INVALID_ARGUMENT", "expansion requires aggregate ID")
            if op == "hierarchy.expand" and group not in {
                point.id for point in previous.points
            }:
                raise Refusal("NOT_FOUND", "aggregate is not in the current frontier")
            expanded = (
                previous.expanded | {group[2:]}
                if op == "hierarchy.expand"
                else previous.expanded - {group[2:]}
            )
            members = previous.members
        elif params["frontier_handle"] is not None or params["columns"]:
            raise Refusal(
                "UNSUPPORTED_CAPABILITY",
                "initial view uses catalog frontier and its base columns",
            )
        view = self.provider.view(
            expanded,
            members,
            min(10000, budget["max_points"]),
            min(100000, budget["max_links"]),
        )
        if (time.monotonic() - start) * 1000 > budget["deadline_ms"]:
            raise Refusal(
                "DEADLINE_EXCEEDED",
                "cooperative deadline exceeded before publishing the view",
            )
        view_id = uuid.uuid4().hex
        points, point_bytes = self.resource(
            sid,
            {
                key: [asdict(point)[key] for point in view.points]
                for key in ("id", "kind", "x", "y", "represented_vertices")
            },
        )
        links, link_bytes = self.resource(
            sid,
            {
                key: [asdict(link)[key] for link in view.links]
                for key in ("source", "target", "multiplicity")
            },
        )
        if sum(int(r["encoded_bytes"]) for r in (points, links)) > int(
            budget["max_wire_bytes"]
        ) or point_bytes + link_bytes > int(budget["max_decoded_bytes"]):
            for resource in (points, links):
                del self.resources[resource["handle"]]
            raise Refusal("BUDGET_EXCEEDED", "view exceeds wire or decode cap")
        manifest = {
            "cosmolang": "0.1",
            "view_id": view_id,
            "generation": str(session.revision + 1),
            "context": dict(request["context"]),
            "frontier_handle": view_id,
            "coordinate_frame": "catalog-xy-v1",
            "dimensions": 2,
            "representation": "quotient",
            "membership_status": "complete",
            "edge_status": "complete",
            "counts": {
                "points": str(len(view.points)),
                "links": str(len(view.links)),
                "represented_vertices": str(
                    sum(int(p.represented_vertices) for p in view.points)
                ),
                "omitted_edges": "0",
            },
            "points": points,
            "links": links,
            "decoded_bytes": str(point_bytes + link_bytes),
            "applied_budget": budget,
            "edge_policy": {
                "direction": "directed",
                "parallel": "aggregate",
                "self_loops": "summarize",
            },
            "quality_provenance": "Exact supplied membership; quotient self loops retained with multiplicity; catalog coordinates averaged.",
        }
        self.validators["manifest"].validate(manifest)
        encoded = json.dumps(manifest, allow_nan=False).encode()
        self.resources[view_id] = (sid, encoded)
        session.views[view_id] = view
        session.revision += 1
        result = self.response(request, sid)
        result["view_id"] = view_id
        result["resources"] = [
            {
                "handle": view_id,
                "uri": f"cosmolang://{sid}/{view_id}",
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "encoded_bytes": str(len(encoded)),
                "media_type": "application/json",
            }
        ]
        return result
