"""Vectorized full-domain BFS certificate; no graph adjacency or Python row map."""

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

import bfs_models as m

I64 = NDArray[np.int64]
Bool = NDArray[np.bool_]


@dataclass(slots=True)
class State:
    ids: I64
    source: int
    verification_batch_rows: int = 65536
    identity_domain: bool = field(init=False)
    distance: I64 = field(init=False)
    parent: I64 = field(init=False)
    minimum_parent: I64 = field(init=False)
    seen: Bool = field(init=False)
    predecessor_found: Bool = field(init=False)
    failures: m.Failures = field(default_factory=m.Failures)
    rows: int = 0
    edges: int = 0

    def __post_init__(self) -> None:
        if self.ids.dtype != np.int64 or self.ids.ndim != 1 or not self.ids.size:
            raise ValueError("nonempty signed Int64 domain required")
        if np.searchsorted(self.ids, self.source) >= len(self.ids):
            raise ValueError("source outside sorted domain")
        if int(self.ids[np.searchsorted(self.ids, self.source)]) != self.source:
            raise ValueError("source outside sorted domain")
        if self.verification_batch_rows < 1:
            raise ValueError("positive domain verification batch required")
        self.identity_domain = True
        for start in range(0, len(self.ids), self.verification_batch_rows):
            end = min(len(self.ids), start + self.verification_batch_rows)
            if not np.array_equal(
                self.ids[start:end], np.arange(start, end, dtype=np.int64)
            ):
                self.identity_domain = False
                break
        n = len(self.ids)
        self.distance = np.full(n, -1, dtype=np.int64)
        self.parent = np.zeros(n, dtype=np.int64)
        self.minimum_parent = np.full(n, np.iinfo(np.int64).max, dtype=np.int64)
        self.seen = np.zeros(n, dtype=np.bool_)
        self.predecessor_found = np.zeros(n, dtype=np.bool_)

    def positions(self, values: I64) -> tuple[I64, Bool]:
        if self.identity_domain:
            known = (values >= 0) & (values < len(self.ids))
            return np.clip(values, 0, len(self.ids) - 1), known
        positions = np.searchsorted(self.ids, values).astype(np.int64, copy=False)
        in_range = positions < len(self.ids)
        safe = np.minimum(positions, len(self.ids) - 1)
        known = in_range & (self.ids[safe] == values)
        return safe, known

    def result_batch(
        self,
        ids: I64,
        distance: I64,
        hops: I64,
        parent: I64,
        valid_id: Bool,
        valid_distance: Bool,
        valid_hops: Bool,
        valid_parent: Bool,
    ) -> None:
        n = len(ids)
        if any(
            len(value) != n
            for value in (
                distance,
                hops,
                parent,
                valid_id,
                valid_distance,
                valid_hops,
                valid_parent,
            )
        ):
            raise ValueError("result batch lengths differ")
        self.rows += n
        positions, known = self.positions(ids)
        known &= valid_id
        self.failures.null_ids += int(np.count_nonzero(~valid_id))
        self.failures.unknown_ids += int(np.count_nonzero(valid_id & ~known))
        self.failures.null_tuple += int(
            np.count_nonzero(
                (valid_distance != valid_hops) | (valid_distance != valid_parent)
            )
        )
        invalid = valid_distance & ((distance < 0) | (distance >= len(self.ids)))
        self.failures.invalid_distance += int(np.count_nonzero(invalid))
        self.failures.distance_hops += int(
            np.count_nonzero(valid_distance & valid_hops & (distance != hops))
        )
        selected = positions[known]
        unique, first = np.unique(selected, return_index=True)
        self.failures.duplicate_rows += len(selected) - len(unique)
        self.failures.duplicate_rows += int(np.count_nonzero(self.seen[unique]))
        # Retain the first physical row; duplicate output never qualifies.
        fresh = ~self.seen[unique]
        rows = np.flatnonzero(known)[first[fresh]]
        target = unique[fresh]
        self.seen[target] = True
        good_distance = valid_distance[rows] & ~invalid[rows]
        self.distance[target] = np.where(good_distance, distance[rows], -1)
        self.parent[target] = parent[rows]

    def edge_batch(self, source: I64, target: I64) -> None:
        if len(source) != len(target):
            raise ValueError("edge batch lengths differ")
        left, left_known = self.positions(source)
        right, right_known = self.positions(target)
        if not np.all(left_known & right_known):
            raise ValueError("original edge endpoint outside vertex domain")
        self.edges += len(source)
        dl, dr = self.distance[left], self.distance[right]
        reached_left, reached_right = dl >= 0, dr >= 0
        self.failures.edge_reachability_closure += int(
            np.count_nonzero(reached_left != reached_right)
        )
        both = reached_left & reached_right
        self.failures.edge_level_gap += int(
            np.count_nonzero(both & (np.abs(dl - dr) > 1))
        )
        forward = reached_left & (dr == dl + 1)
        backward = reached_right & (dl == dr + 1)
        np.minimum.at(self.minimum_parent, right[forward], source[forward])
        self.predecessor_found[right[forward]] = True
        np.minimum.at(self.minimum_parent, left[backward], target[backward])
        self.predecessor_found[left[backward]] = True

    def finish(
        self,
        receipt: m.Receipt,
        terminal: m.Terminal | None,
        max_levels: int,
        batch_rows: int,
    ) -> None:
        reached, maximum, unique = 0, -1, 0
        for start in range(0, len(self.ids), batch_rows):
            end = min(len(self.ids), start + batch_rows)
            ids, distances = self.ids[start:end], self.distance[start:end]
            seen = self.seen[start:end]
            parents = self.parent[start:end]
            present = seen & (distances >= 0)
            root = ids == self.source
            unique += int(np.count_nonzero(seen))
            reached += int(np.count_nonzero(present))
            maximum = max(maximum, int(np.max(distances)))
            self.failures.source_tuple += int(
                np.count_nonzero(
                    root & (~seen | (distances != 0) | (parents != self.source))
                )
            )
            self.failures.non_source_zero += int(
                np.count_nonzero(~root & present & (distances == 0))
            )
            positive = present & (distances > 0)
            self.failures.minimum_parent += int(
                np.count_nonzero(
                    positive
                    & (
                        ~self.predecessor_found[start:end]
                        | (parents != self.minimum_parent[start:end])
                    )
                )
            )
        self.failures.missing_ids = len(self.ids) - unique
        receipt.failures = self.failures
        receipt.output_rows, receipt.edge_rows = self.rows, self.edges
        receipt.unique_output_ids, receipt.reached = unique, reached
        receipt.max_distance = maximum
        receipt.computed_terminal_levels = maximum + 1 if maximum >= 0 else None
        receipt.observed_terminal = terminal
        receipt.full_domain_passed = (
            self.rows == len(self.ids)
            and unique == len(self.ids)
            and self.failures.duplicate_rows
            == self.failures.unknown_ids
            == self.failures.null_ids
            == 0
        )
        receipt.parent_paths_and_minimum_parent_passed = (
            self.failures.source_tuple
            == self.failures.non_source_zero
            == self.failures.minimum_parent
            == self.failures.null_tuple
            == self.failures.invalid_distance
            == self.failures.distance_hops
            == 0
        )
        receipt.all_edge_lower_bound_and_reachability_passed = (
            self.failures.edge_level_gap == self.failures.edge_reachability_closure == 0
        )
        receipt.terminal_empty_expansion_cap_passed = (
            terminal is not None
            and terminal.converged == 1
            and terminal.phase == max_levels + 1
            and 1 <= terminal.levels <= max_levels
            and terminal.levels == receipt.computed_terminal_levels
            and terminal.reached == reached
        )
        receipt.full_array_bytes = sum(
            array.nbytes
            for array in (
                self.ids,
                self.distance,
                self.parent,
                self.minimum_parent,
                self.seen,
                self.predecessor_found,
            )
        )
        receipt.identity_domain_verified = self.identity_domain
        # Advisory visible batch-buffer allowance, not an enforced decoder/RSS bound.
        receipt.declared_batch_array_allowance_bytes = 512 * batch_rows
