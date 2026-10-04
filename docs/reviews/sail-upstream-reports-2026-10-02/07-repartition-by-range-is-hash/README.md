# `repartitionByRange` hash-partitions, silently

**Kind:** semantic difference from Spark. Query results are correct; the partition contents are not what was asked for.

## Summary

`df.repartitionByRange(n, "id")` plans `RepartitionExec: partitioning=Hash([id], n)`. The partitions' key ranges overlap completely. There is no warning. Anything that relies on range partitions is affected: sorted files with disjoint key ranges after `sortWithinPartitions`, per-partition processing by key range, and file pruning on the result.

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

[`repro.py`](repro.py) starts its own server, runs the case, and stops the server. It needs `pyspark[connect]` 4.0 and `pyarrow`. The output of the run reported here is [`output.txt`](output.txt).

## Observed

```
plan: RepartitionExec: partitioning=Hash([#0@0], 4), input_partitions=1
partition 0: ids 2 to 999,991, 250,006 rows
partition 1: ids 1 to 999,994, 249,999 rows
partition 2: ids 10 to 999,999, 249,997 rows
partition 3: ids 0 to 999,995, 249,998 rows
```

## Expected

Four partitions with disjoint, ordered key ranges, about 250,000 rows each, as Spark's `repartitionByRange` produces. Or an error saying range partitioning is not supported.

## Cause

`repartitionByRange` arrives as a repartition by expression and is always resolved to `ExplicitRepartitionKind::Hash` (`crates/sail-plan/src/resolver/query/repartition.rs:52-58`). The kinds are `Coalesce`, `RoundRobin` and `Hash` (`crates/sail-logical-plan/src/repartition.rs:9-13`). The sort direction of the range expression is dropped.

DataFusion 55.1.0 has `Partitioning::Range` with explicit split points, and `RepartitionExec` executes it. Sail's shuffle writer, job graph and checkpoint code already pass such a partitioning through. Nothing constructs one, and nothing samples the input to choose split points.

## Possible fix

Add a range kind to the explicit repartition, choose split points by sampling the input as Spark does, and plan `Partitioning::Range`. Until then, reject `repartitionByRange` or log that it is hash-partitioned.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

No existing issue or pull request found. Open pull request #2553 ("feat: range partitioning for Iceberg") has no description; from its title it concerns table partitioning, not `repartitionByRange`.

## Notes

- "Nothing constructs one" rests on a search of the source for `Partitioning::Range` and `RangePartitioning::`.
