"""Illustrate prepared-boundary identity with a deterministic transition model.

This is not a reproduction in Sail, a Spark comparison, or an implementation
of a coordinator. It models only append effects and skipping checkpoint IDs
already held by a sink. Run this file to regenerate the adjacent JSON record.
"""

from collections import Counter
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Sink:
    name: str
    last_checkpoint: int
    rows: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Checkpoint:
    identifier: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Observation:
    sink: str
    last_checkpoint: int
    rows: tuple[int, ...]
    missing: tuple[int, ...]
    duplicated: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Scenario:
    policy: str
    checkpoints: tuple[Checkpoint, ...]
    observations: tuple[Observation, ...]
    exactly_once: bool
    expected_result: str


@dataclass(frozen=True, slots=True)
class Record:
    scope: str
    script_sha256: str
    assumptions: tuple[str, ...]
    initial_sinks: tuple[Sink, ...]
    expected_rows: tuple[int, ...]
    scenarios: tuple[Scenario, ...]
    controls: str


EXPECTED = tuple(range(10))
INITIAL = (Sink("A", 2, tuple(range(6))), Sink("B", 1, tuple(range(3))))


def apply(sink: Sink, checkpoint: Checkpoint) -> Sink:
    """A sink atomically appends a range unless it already holds the ID."""
    if checkpoint.identifier <= sink.last_checkpoint:
        return sink
    return replace(
        sink,
        last_checkpoint=checkpoint.identifier,
        rows=sink.rows + tuple(range(checkpoint.start, checkpoint.end)),
    )


def observe(sink: Sink) -> Observation:
    counts = Counter(sink.rows)
    return Observation(
        sink.name,
        sink.last_checkpoint,
        sink.rows,
        tuple(row for row in EXPECTED if counts[row] == 0),
        tuple(row for row, count in sorted(counts.items()) if count > 1),
    )


def require_exactly_once(sinks: tuple[Sink, ...]) -> None:
    for sink in sinks:
        assert Counter(sink.rows) == Counter(EXPECTED), observe(sink)


def run_policy(
    policy: str, checkpoints: tuple[Checkpoint, ...], should_pass: bool
) -> Scenario:
    sinks = INITIAL
    for checkpoint in checkpoints:
        sinks = tuple(apply(sink, checkpoint) for sink in sinks)
    try:
        require_exactly_once(sinks)
    except AssertionError:
        passed = False
    else:
        passed = True
    assert passed == should_pass, (policy, tuple(observe(sink) for sink in sinks))
    return Scenario(
        policy,
        checkpoints,
        tuple(observe(sink) for sink in sinks),
        passed,
        "preserves both sinks" if should_pass else "negative control detects violation",
    )


def main() -> None:
    scenarios = (
        run_policy("reuse prepared ID at new boundary", (Checkpoint(2, 3, 10),), False),
        run_policy("allocate fresh ID for replayed prefix", (Checkpoint(3, 3, 10),), False),
        run_policy(
            "replay prepared boundary then new boundary",
            (Checkpoint(2, 3, 6), Checkpoint(3, 6, 10)),
            True,
        ),
    )
    assert scenarios[0].observations[0].missing == (6, 7, 8, 9)
    assert scenarios[1].observations[0].duplicated == (3, 4, 5)
    assert all(not item.missing and not item.duplicated for item in scenarios[2].observations)
    record = Record(
        "Deterministic append-effect model only; not a Sail or Spark execution",
        sha256(Path(__file__).read_bytes()).hexdigest(),
        (
            "Rows are stable integers 0 through 9 and positions are half-open offsets.",
            "Both sinks completed checkpoint 1 through position 3.",
            "Checkpoint 2 was prepared through position 6; only A committed it.",
            "Recovery starts at position 3, the least committed sink position.",
            "Each sink atomically appends unless identifier <= its last committed ID.",
            "No transforms, operator state, concurrency, crashes during recovery or storage failures are modeled.",
        ),
        INITIAL,
        EXPECTED,
        scenarios,
        "Two incorrect policies fail the exactly-once assertion; fixed-boundary replay passes it.",
    )
    output = Path(__file__).with_name("checkpoint-boundary-model.json")
    output.write_text(json.dumps(asdict(record), indent=2, sort_keys=True) + "\n")
    print("Model checks passed: two negative controls and one fixed-boundary scenario.")
    print(output)


if __name__ == "__main__":
    main()
