"""The engine-neutral, zero-input relation protocol for staging ownership."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, cast

from pyspark.sql.connect.dataframe import DataFrame
from pyspark.sql.connect.plan import LogicalPlan

from . import utils_pb2 as _wire

if TYPE_CHECKING:
    from pyspark.sql import Row
    from pyspark.sql.connect.client import SparkConnectClient
    from pyspark.sql.connect.proto import Relation
    from pyspark.sql.connect.session import SparkSession

# Generated protobuf module: no type stubs, so its messages are typed as Any.
wire: Any = _wire

TYPE_URL: str = "type.googleapis.com/gf.utils.v1.Request"
CLIENT_VERSION: str = "0.1.0"


class CapabilityError(RuntimeError):
    """The server does not implement the required versioned utils contract."""


class _UtilsRelation(LogicalPlan):
    def __init__(self, request: Any) -> None:
        super().__init__(None)
        self.payload: bytes = request.SerializeToString()

    def plan(self, session: SparkConnectClient) -> Relation:
        relation = self._create_proto_relation()
        relation.extension.type_url = TYPE_URL
        relation.extension.value = self.payload
        return relation


class GraphUtils:
    """Filesystem operations scoped by a server-issued run capability.

    All returned paths name storage visible to the server. Python never opens
    them. A successful exists/list keeps the session active; closing a Spark
    session or letting it expire invalidates its retained graph results.
    """

    def __init__(self, spark: SparkSession) -> None:
        self.spark = spark
        try:
            rows = self._request(wire.Request(ping=wire.Ping(client_version=CLIENT_VERSION)))
        except Exception as exc:
            raise CapabilityError(
                "graph utils Ping failed: enable the server's owned-run storage service"
            ) from exc
        if len(rows) != 1 or rows[0].kind != "pong":
            raise CapabilityError("invalid graph utils Ping receipt")
        pong = rows[0]
        try:
            self.capabilities: frozenset[str] = frozenset(json.loads(pong.capabilities))
        except (ValueError, TypeError) as exc:
            raise CapabilityError("invalid graph utils capabilities JSON") from exc
        if pong.protocol_version != 1 or not {"fs", "owned_runs_v1"} <= self.capabilities:
            raise CapabilityError("graph utils requires protocol 1 and fs, owned_runs_v1 capabilities")
        self.root: str = pong.path
        self.engine: str = pong.engine
        self.lease_seconds: int = pong.lease_seconds

    def _request(self, request: Any) -> list[Row]:
        # Receipt collection is bounded. Graph rows are never returned here.
        return DataFrame(_UtilsRelation(request), self.spark).collect()

    def allocate(self, *, request_id: str | None = None) -> tuple[str, str]:
        request_id = request_id or str(uuid.uuid4())
        row = self._request(wire.Request(mkdir=wire.Mkdir(root="", request_id=request_id)))[0]
        return row.path, row.token

    def exists(self, path: str, token: str) -> bool:
        return cast(bool, self._request(wire.Request(exists=wire.Exists(path=path, token=token)))[0].value)

    def ls(self, path: str, token: str, *, limit: int = 1000) -> list[Row]:
        return self._request(wire.Request(ls=wire.Ls(path=path, limit=limit, token=token)))

    def remove(self, path: str, token: str) -> int:
        # Row inherits tuple.count; field access must not resolve that method.
        return cast(int, self._request(wire.Request(rm=wire.Rm(path=path, token=token)))[0]["count"])
