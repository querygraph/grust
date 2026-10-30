#!/usr/bin/env python3
"""Replay a source-derived Scala map-order hypothesis against archived lookups.

No JVM execution. ASCII-only lowercase comparison; not a Java ROOT implementation.
"""

import hashlib
import json
from pathlib import Path
import platform
import sys


INPUT = Path(
    "/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/"
    "evidence/fable-column-oracles/jvm/results.json"
)
MASK = 0xFFFFFFFF


def improved_java_hash(value):
    encoded = value.encode("utf-16-be")
    hashed = 0
    for offset in range(0, len(encoded), 2):
        unit = int.from_bytes(encoded[offset : offset + 2], "big")
        hashed = (31 * hashed + unit) & MASK
    hashed = (hashed + (~(hashed << 9) & MASK)) & MASK
    hashed ^= hashed >> 14
    hashed = (hashed + (hashed << 4)) & MASK
    hashed ^= hashed >> 10
    return hashed


def hash_traversal(names, hashes, shift=0):
    if shift >= 32:
        return list(names)
    buckets = [[] for _ in range(32)]
    for name in names:
        buckets[(hashes[name] >> shift) & 31].append(name)
    ordered = [bucket[0] for bucket in buckets if len(bucket) == 1]
    for bucket in buckets:
        if len(bucket) > 1:
            ordered.extend(hash_traversal(bucket, hashes, shift + 5))
    return ordered


def replay(record):
    fields = record["fields"]
    query = record["query"]
    if not all(name.isascii() for name in [*fields, query]):
        raise ValueError("This replay deliberately supports only ASCII lookup records")
    # Python dictionaries retain a key's first insertion position on replacement.
    exact = {}
    for index, name in enumerate(fields):
        exact[name] = index
    unique_names = list(exact)
    hashes = {name: improved_java_hash(name) for name in unique_names}
    traversal = (
        unique_names
        if len(unique_names) <= 4
        else hash_traversal(unique_names, hashes)
    )
    insensitive = {}
    for name in traversal:
        insensitive[name.lower()] = exact[name]
    actual = {
        "exact_index": exact.get(query),
        "insensitive_index": insensitive.get(query.lower()),
    }
    expected = {key: record[key] for key in actual}
    return {
        "case": record["case"],
        "fields": fields,
        "query": query,
        "distinct_exact_names": len(unique_names),
        "hypothesized_traversal": traversal,
        "improved_hashes_u32": hashes,
        "expected": expected,
        "actual": actual,
        "matches": actual == expected,
    }


def main():
    raw = INPUT.read_bytes()
    records = json.loads(raw)
    lookups = [record for record in records if record["kind"] == "lookup"]
    if len(lookups) != 23:
        raise ValueError(f"Expected the retained 23 lookup records; found {len(lookups)}")
    results = [replay(record) for record in lookups]
    mismatches = [result for result in results if not result["matches"]]
    script = Path(__file__).resolve()
    receipt = {
        "scope": (
            "Source-derived insertion-only Scala map traversal hypothesis replay "
            "against archived direct StructType lookup observations. No new JVM, "
            "Spark, Rust, Sail, or CDC execution; not a parity verdict."
        ),
        "lowercase_scope": (
            "All compared field names and queries are asserted ASCII. Python lower "
            "is used only for these ASCII strings; no Java ROOT Unicode claim."
        ),
        "input_path": str(INPUT),
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "script_path": str(script),
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "command": ["python3", str(script)],
        "stdout_redirect": "/tmp/sail-sdp-scala-lookup-replay.json",
        "input_record_count": len(records),
        "checked_lookup_records": len(results),
        "matching_lookup_records": len(results) - len(mismatches),
        "checked_comparisons": 2 * len(results),
        "mismatches": mismatches,
        "results": results,
    }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
