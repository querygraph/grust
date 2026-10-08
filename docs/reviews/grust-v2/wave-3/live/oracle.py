"""Independent DFS oracle on immutable fixture tuples; no Sail/Rust plan reuse."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Oracle:
    mode: str = "Walk"
    min_hops: int = 1
    max_hops: int = 5
    shortest: bool = False
    all_ties: bool = True
    incoming: bool = False


EDGES = ((100, 1, 2), (101, 1, 2), (102, 2, 3), (103, 3, 3), (104, 3, 1))


def rows(spec: Oracle) -> list[list[int]]:
    candidates: list[list[int]] = []
    for source in range(1, 6):
        visit(source, (source,), (), spec, candidates)
    if not spec.shortest:
        return candidates
    selected: list[list[int]] = []
    for pair in sorted({(r[0], r[1]) for r in candidates}):
        matching = [r for r in candidates if (r[0], r[1]) == pair]
        minimum = min(r[2] for r in matching)
        ties = [r for r in matching if r[2] == minimum]
        selected.extend(ties if spec.all_ties else ties[:1])
    return selected


def visit(
    source: int,
    vertices: tuple[int, ...],
    edges: tuple[int, ...],
    spec: Oracle,
    output: list[list[int]],
) -> None:
    if len(edges) >= spec.min_hops:
        output.append([source, vertices[-1], len(edges)])
    if len(edges) == spec.max_hops:
        return
    if spec.mode == "Simple" and edges and vertices[-1] == source:
        return
    for edge, a, b in EDGES:
        if spec.incoming:
            a, b = b, a
        if a != vertices[-1]:
            continue
        if spec.mode in {"Trail", "Simple"} and edge in edges:
            continue
        if spec.mode == "Acyclic" and b in vertices:
            continue
        if spec.mode == "Simple" and b in vertices and b != source:
            continue
        visit(source, (*vertices, b), (*edges, edge), spec, output)


SPECS = {
    "unbounded_shortest": Oracle(shortest=True, all_ties=False),
    "unbounded_all_shortest": Oracle(shortest=True),
    "unbounded_acyclic_all": Oracle(mode="Acyclic"),
    "unbounded_trail_all": Oracle(mode="Trail"),
    "unbounded_simple_all": Oracle(mode="Simple"),
    "unbounded_min_two": Oracle(min_hops=2, shortest=True),
    "unbounded_zero_shortest": Oracle(min_hops=0, shortest=True),
    "unbounded_incoming_shortest": Oracle(shortest=True, incoming=True),
}
