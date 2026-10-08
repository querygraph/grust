"""Pinned SNB v1 CSV fixture, schema metadata and an independent short-query oracle."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]  # Arrow publishes no Python type stubs.
import pyarrow.parquet as pq  # type: ignore[import-untyped]  # Arrow publishes no Python type stubs.

PIN = "f9c394a92cd55e535893f6c9907b141d6533c817"


@dataclass(frozen=True, slots=True)
class Table:
    group: int
    name: str
    records: list[dict[str, Any]]
    types: dict[str, str]
    source: int | None = None
    target: int | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "name": self.name,
            "rows": len(self.records),
            "distinct": {
                key: len(
                    {
                        json.dumps(r[key], sort_keys=True)
                        for r in self.records
                        if r[key] is not None
                    }
                )
                for key in self.types
            },
            "source_ndv": len({r["src"] for r in self.records})
            if self.source
            else None,
            "target_ndv": len({r["dst"] for r in self.records})
            if self.target
            else None,
        }

    def ddl(self) -> str:
        return ",".join(f"`{key}` {value}" for key, value in self.types.items())


def csv_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(newline="") as stream:
        reader = csv.reader(stream, delimiter="|")
        return next(reader), list(reader)


def convert(value: str, ty: str) -> Any:
    if not value:
        return None
    if ty in {"BIGINT", "INT"}:
        return int(value)
    if ty == "ARRAY<STRING>":
        return value.split(";")
    return value


def logical(ty: str) -> Any:
    return {
        "BIGINT": "Int64",
        "INT": "Int32",
        "STRING": "String",
        "ARRAY<STRING>": {"List": "String"},
    }[ty]


def properties(types: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {"name": key, "ty": logical(ty), "nullable": key != "id"}
        for key, ty in types.items()
        if key != "_identity"
    ]


@dataclass(frozen=True, slots=True)
class Dataset:
    tables: tuple[Table, ...]
    schema: dict[str, Any]
    files: dict[str, str]
    sha256: str

    def table(self, name: str) -> Table:
        return next(t for t in self.tables if t.name == name)


def load(root: Path) -> Dataset:
    data = root / "cypher/test-data/vanilla"
    tables: list[Table] = []
    files: dict[str, str] = {}
    types: list[dict[str, Any]] = []
    vertices: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def read(relative: str) -> tuple[list[str], list[list[str]]]:
        path = data / relative
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return csv_rows(path)

    common_message = {
        "id": "BIGINT",
        "creationDate": "BIGINT",
        "locationIP": "STRING",
        "browserUsed": "STRING",
        "content": "STRING",
        "length": "INT",
    }
    types.extend(
        [
            {
                "id": 100,
                "name": "Message",
                "labels": ["Message"],
                "supertypes": [],
                "properties": properties(common_message),
            },
            {
                "id": 101,
                "name": "Place",
                "labels": ["Place"],
                "supertypes": [],
                "properties": properties(
                    {"id": "BIGINT", "name": "STRING", "url": "STRING"}
                ),
            },
        ]
    )
    for group, name, parent, declared in [
        (
            1,
            "Person",
            [],
            {
                "id": "BIGINT",
                "firstName": "STRING",
                "lastName": "STRING",
                "gender": "STRING",
                "birthday": "BIGINT",
                "creationDate": "BIGINT",
                "locationIP": "STRING",
                "browserUsed": "STRING",
                "speaks": "ARRAY<STRING>",
                "email": "ARRAY<STRING>",
            },
        ),
        (
            2,
            "Post",
            [100],
            {**common_message, "imageFile": "STRING", "language": "STRING"},
        ),
        (3, "Comment", [100], common_message),
        (4, "Forum", [], {"id": "BIGINT", "title": "STRING", "creationDate": "BIGINT"}),
    ]:
        header, rows = read(f"dynamic/{name.lower()}_0_0.csv")
        header = [
            "speaks" if name == "Person" and h == "language" else h for h in header
        ]
        records = [
            {
                "_identity": int(row[0]),
                **{
                    key: convert(value, declared[key])
                    for key, value in zip(header, row, strict=True)
                },
            }
            for row in rows
        ]
        tables.append(
            Table(group, name.lower(), records, {"_identity": "BIGINT", **declared})
        )
        own = {
            key: ty
            for key, ty in declared.items()
            if not parent or key not in common_message
        }
        types.append(
            {
                "id": group,
                "name": name,
                "labels": [name],
                "supertypes": parent,
                "properties": properties(own),
            }
        )
        vertices.append(
            {
                "id": group,
                "element_type": group,
                "identity": "Opaque",
                "constraints": [],
            }
        )
    header, rows = read("static/place_0_0.csv")
    for group, name in [(5, "City"), (6, "Country"), (7, "Continent")]:
        declared = {
            "_identity": "BIGINT",
            "id": "BIGINT",
            "name": "STRING",
            "url": "STRING",
        }
        records = [
            {
                "_identity": int(row[0]),
                **{
                    key: convert(value, declared[key])
                    for key, value in zip(header[:3], row[:3], strict=True)
                },
            }
            for row in rows
            if row[3] == name.lower()
        ]
        tables.append(Table(group, name.lower(), records, declared))
        types.append(
            {
                "id": group,
                "name": name,
                "labels": [name],
                "supertypes": [101],
                "properties": [],
            }
        )
        vertices.append(
            {
                "id": group,
                "element_type": group,
                "identity": "Opaque",
                "constraints": [],
            }
        )
    for group, name, file, src, dst in [
        (10, "KNOWS", "person_knows_person", 1, 1),
        (11, "REPLY_OF", "comment_replyOf_comment", 3, 3),
        (12, "REPLY_OF", "comment_replyOf_post", 3, 2),
        (13, "CONTAINER_OF", "forum_containerOf_post", 4, 2),
        (14, "HAS_MODERATOR", "forum_hasModerator_person", 4, 1),
        (15, "HAS_CREATOR", "post_hasCreator_person", 2, 1),
        (16, "HAS_CREATOR", "comment_hasCreator_person", 3, 1),
        (17, "IS_LOCATED_IN", "person_isLocatedIn_place", 1, 5),
    ]:
        header, rows = read(f"dynamic/{file}_0_0.csv")
        declared = {
            "_identity": "BIGINT",
            "src": "BIGINT",
            "dst": "BIGINT",
            **({"creationDate": "BIGINT"} if name == "KNOWS" else {}),
        }
        records = [
            {
                "_identity": index,
                "src": int(row[0]),
                "dst": int(row[1]),
                **({"creationDate": int(row[2])} if name == "KNOWS" else {}),
            }
            for index, row in enumerate(rows)
        ]
        tables.append(Table(group, file.lower(), records, declared, src, dst))
        types.append(
            {
                "id": group + 1000,
                "name": f"{name}_{group}",
                "labels": [name],
                "supertypes": [],
                "properties": properties({"creationDate": "BIGINT"})
                if name == "KNOWS"
                else [],
            }
        )
        edges.append(
            {
                "id": group,
                "element_type": group + 1000,
                "source": src,
                "target": dst,
                "direction": "Directed",
                "identity": "Opaque",
            }
        )
    sha = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return Dataset(
        tuple(tables),
        {"types": types, "vertices": vertices, "edges": edges},
        files,
        sha,
    )


def oracle(dataset: Dataset, query: int, identity: int) -> list[list[Any]]:
    people = {r["id"]: r for r in dataset.table("person").records}
    posts = {r["id"]: r for r in dataset.table("post").records}
    comments = {r["id"]: r for r in dataset.table("comment").records}
    if query == 1:
        p = people.get(identity)
        return (
            []
            if p is None
            else [
                [
                    p[k]
                    for k in (
                        "firstName",
                        "lastName",
                        "birthday",
                        "locationIP",
                        "browserUsed",
                    )
                ]
                + [r["dst"], p["gender"], p["creationDate"]]
                for r in dataset.table("person_islocatedin_place").records
                if r["src"] == identity
            ]
        )
    if query == 3:
        output = []
        for r in dataset.table("person_knows_person").records:
            if r["src"] == identity or r["dst"] == identity:
                friend = people[r["dst"] if r["src"] == identity else r["src"]]
                output.append(
                    [
                        friend["id"],
                        friend["firstName"],
                        friend["lastName"],
                        r["creationDate"],
                    ]
                )
        return sorted(output, key=lambda r: (-r[3], r[0]))
    message = posts.get(identity, comments.get(identity))
    if message is None:
        return []
    if query == 4:
        content = (
            message["content"]
            if message["content"] is not None
            else message.get("imageFile")
        )
        return [[message["creationDate"], content]]
    if query == 5:
        table = (
            "post_hascreator_person"
            if identity in posts
            else "comment_hascreator_person"
        )
        return [
            [people[r["dst"]][k] for k in ("id", "firstName", "lastName")]
            for r in dataset.table(table).records
            if r["src"] == identity
        ]
    if query == 6:
        parents = {
            r["src"]: r["dst"]
            for t in ("comment_replyof_comment", "comment_replyof_post")
            for r in dataset.table(t).records
        }
        current = identity
        while current in comments:
            current = parents[current]
        forums = {r["id"]: r for r in dataset.table("forum").records}
        moderators = {
            r["src"]: people[r["dst"]]
            for r in dataset.table("forum_hasmoderator_person").records
        }
        return [
            [
                r["src"],
                forums[r["src"]]["title"],
                moderators[r["src"]]["id"],
                moderators[r["src"]]["firstName"],
                moderators[r["src"]]["lastName"],
            ]
            for r in dataset.table("forum_containerof_post").records
            if r["dst"] == current
        ]
    raise ValueError(f"unsupported oracle {query}")


def request(dataset: Dataset, root: Path) -> dict[str, Any]:
    people = dataset.table("person").records
    posts = dataset.table("post").records
    comments = dataset.table("comment").records
    queries = []
    for query, ids in [
        (1, [people[0]["id"], -1]),
        (3, [people[0]["id"], -1]),
        (4, [posts[0]["id"], comments[0]["id"], -1]),
        (5, [posts[0]["id"], comments[0]["id"], -1]),
        (6, [posts[0]["id"], comments[0]["id"], -1]),
    ]:
        path = root / f"cypher/queries/interactive-short-{query}.cypher"
        text = path.read_text()
        for identity in ids:
            queries.append(
                {
                    "name": f"ldbc_is{query}_{identity}",
                    "text": text,
                    "text_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "parameters": {
                        "personId" if query in (1, 3) else "messageId": identity
                    },
                    "expected": oracle(dataset, query, identity),
                    "ordered": query == 3,
                }
            )
    return {
        "schema": dataset.schema,
        "tables": [t.metadata() for t in dataset.tables],
        "queries": queries,
        "dataset_sha256": dataset.sha256,
    }


def write_parquet(table: Table, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    types = {
        "BIGINT": pa.int64(),
        "INT": pa.int32(),
        "STRING": pa.string(),
        "ARRAY<STRING>": pa.list_(pa.string()),
    }
    schema = pa.schema(
        [
            pa.field(key, types[ty], nullable=key != "_identity")
            for key, ty in table.types.items()
        ]
    )
    pq.write_table(
        pa.Table.from_pylist(table.records, schema=schema),
        destination / "part-00000.parquet",
    )
