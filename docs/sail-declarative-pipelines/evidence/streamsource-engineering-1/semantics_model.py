"""Small algebra model, not an execution of Spark, Sail, Delta or Iceberg."""
from itertools import permutations, product
import json


def spark(chunks):
    live = None
    tombstone = None
    for chunk in chunks:
        # One permitted max_by outcome: later supplied row wins an equal sequence.
        winner = max(enumerate(chunk), key=lambda pair: (pair[1][0], pair[0]))[1]
        seq, action, payload = winner
        if tombstone is not None and seq < tombstone:
            continue
        if action == "delete":
            tombstone = seq if tombstone is None else max(tombstone, seq)
            if live is not None and seq > live[0]:
                live = None
        else:
            if tombstone is not None and seq >= tombstone:
                tombstone = None
            if live is None or seq >= live[0]:
                live = winner
    return {"live": live, "tombstone": tombstone}


def partitions(events):
    for cuts in product((False, True), repeat=len(events) - 1):
        result = [[events[0]]]
        for cut, event in zip(cuts, events[1:]):
            if cut:
                result.append([])
            result[-1].append(event)
        yield result


def proposed(chunks):
    fingerprints = {}
    state = None
    for chunk in chunks:
        for version, action, payload in chunk:
            canonical = (action, payload)
            if version in fingerprints and fingerprints[version] != canonical:
                return "conflict"
            fingerprints[version] = canonical
        for event in chunk:
            if state is None or event[0] > state[0]:
                state = event
    return state


upsert = (5, "upsert", "A")
delete = (5, "delete", None)
newer = (9, "upsert", "N")
valid = [(8, "upsert", "A"), (9, "delete", None), (8, "upsert", "A")]
conflicting = [(8, "upsert", "A"), (8, "upsert", "B"), newer]
valid_cases = [proposed(chunks) for order in set(permutations(valid)) for chunks in partitions(order)]
conflict_cases = [proposed(chunks) for order in permutations(conflicting) for chunks in partitions(order)]
assert all(result == (9, "delete", None) for result in valid_cases)
assert all(result == "conflict" for result in conflict_cases)
assert spark([[upsert, delete]])["live"] is None
assert spark([[upsert], [delete]])["live"] == upsert
assert spark([[(5, "upsert", "A")], [(5, "upsert", "B")]])["live"][2] == "B"
assert spark([[(5, "upsert", "B")], [(5, "upsert", "A")]])["live"][2] == "A"
result = {
    "method": "Python logic model only; source-derived rules; no engine execution",
    "spark_equal_version_combined": spark([[upsert, delete]]),
    "spark_equal_version_separate": spark([[upsert], [delete]]),
    "spark_equal_upserts_ab": spark([[(5, "upsert", "A")], [(5, "upsert", "B")]]),
    "spark_equal_upserts_ba": spark([[(5, "upsert", "B")], [(5, "upsert", "A")]]),
    "spark_losing_delete_same_interval": spark([[(5, "delete", None), newer]]),
    "spark_losing_delete_after_newer": spark([[newer], [(5, "delete", None)]]),
    "proposed_valid_distinct_order_partition_cases": len(valid_cases),
    "proposed_valid_result": valid_cases[0],
    "proposed_conflict_permutation_partition_cases": len(conflict_cases),
    "proposed_conflict_result": "conflict in every case",
    "limits": [
        "One key, fixed scalar versions, replace-row upserts and deletes only",
        "Fingerprint retention is unbounded in this tiny model",
        "No storage, transactions, concurrency, failures, planner or Arrow execution",
        "The chosen Spark max_by tie outcome is allowed, not guaranteed"
    ],
}
print(json.dumps(result, indent=2))
