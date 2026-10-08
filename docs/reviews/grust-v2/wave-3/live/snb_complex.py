"""Independent CSV answers for unchanged official SNB IC2, IC8 and IC9."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from snb_dataset import Dataset


@dataclass(frozen=True, slots=True)
class Person:
    id: int
    first: str
    last: str


@dataclass(frozen=True, slots=True)
class Message:
    id: int
    author: int
    content: str | None
    date: int


@dataclass(frozen=True, slots=True)
class Oracle:
    people: dict[int, Person]
    messages: dict[int, Message]
    neighbors: dict[int, list[int]]
    replies: tuple[tuple[int, int], ...]

    @classmethod
    def from_csv(cls, dataset: Dataset) -> Oracle:
        people = {
            r["id"]: Person(r["id"], r["firstName"], r["lastName"])
            for r in dataset.table("person").records
        }
        creators = {
            r["src"]: r["dst"]
            for name in ("post_hascreator_person", "comment_hascreator_person")
            for r in dataset.table(name).records
        }
        messages = {
            r["id"]: Message(
                r["id"],
                creators[r["id"]],
                r["content"] if r["content"] is not None else r.get("imageFile"),
                r["creationDate"],
            )
            for name in ("post", "comment")
            for r in dataset.table(name).records
        }
        neighbors: dict[int, list[int]] = {identity: [] for identity in people}
        for row in dataset.table("person_knows_person").records:
            neighbors[row["src"]].append(row["dst"])
            if row["src"] != row["dst"]:
                neighbors[row["dst"]].append(row["src"])
        replies = tuple(
            (r["src"], r["dst"])
            for name in ("comment_replyof_post", "comment_replyof_comment")
            for r in dataset.table(name).records
        )
        return cls(people, messages, neighbors, replies)

    def rows(
        self, query: int, person: int, maximum: int | None = None
    ) -> list[list[Any]]:
        if person not in self.people:
            return []
        if query == 8:
            candidates = [
                self.messages[reply]
                for reply, parent in self.replies
                if self.messages[parent].author == person
            ]
        else:
            neighbors = self.neighbors[person]
            if query == 9:
                neighbors = sorted(
                    (
                        set(neighbors)
                        | {
                            other
                            for friend in neighbors
                            for other in self.neighbors[friend]
                        }
                    )
                    - {person}
                )
            assert maximum is not None
            candidates = [
                message
                for friend in neighbors
                for message in self.messages.values()
                if message.author == friend
                and (message.date <= maximum if query == 2 else message.date < maximum)
            ]
        candidates.sort(key=lambda message: (-message.date, message.id))
        result = []
        for message in candidates[:20]:
            author = self.people[message.author]
            if query == 8:
                result.append(
                    [
                        author.id,
                        author.first,
                        author.last,
                        message.date,
                        message.id,
                        message.content,
                    ]
                )
            else:
                result.append(
                    [
                        author.id,
                        author.first,
                        author.last,
                        message.id,
                        message.content,
                        message.date,
                    ]
                )
        return result


def request(dataset: Dataset, root: Path) -> dict[str, Any]:
    oracle = Oracle.from_csv(dataset)
    queries = []
    first = next(iter(oracle.people))
    for query in (2, 8, 9):
        path = root / f"cypher/queries/interactive-complex-{query}.cypher"
        productive = max(
            oracle.people,
            key=lambda person: len(oracle.rows(query, person, (1 << 63) - 1)),
        )
        bindings = [
            (identity, (1 << 63) - 1)
            for identity in dict.fromkeys((first, productive, -1))
        ]
        if query != 8:
            top = oracle.rows(query, productive, (1 << 63) - 1)
            boundary = int(top[0][-1])
            bindings.extend(
                (productive, cutoff)
                for cutoff in (0, boundary - 1, boundary, boundary + 1)
            )
        for identity, maximum in bindings:
            parameters = {"personId": identity}
            if query != 8:
                parameters["maxDate"] = maximum
            queries.append(
                {
                    "name": f"ldbc_ic{query}_{identity}_{maximum}"
                    if query != 8
                    else f"ldbc_ic8_{identity}",
                    "text": path.read_text(),
                    "text_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "parameters": parameters,
                    "expected": oracle.rows(query, identity, maximum),
                    "ordered": True,
                }
            )
    return {
        "schema": dataset.schema,
        "tables": [t.metadata() for t in dataset.tables],
        "queries": queries,
        "dataset_sha256": dataset.sha256,
    }
