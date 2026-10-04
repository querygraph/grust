# In cluster mode, `GROUP BY` over a table with a declared sort order fails with an internal error

**Kind:** query failure in cluster mode; the same query runs in local mode.

## Summary

A catalog table created with `SORTED BY (k)` over several files makes `GROUP BY k` plan a sorted aggregation with an order-preserving hash repartition. In `local-cluster` mode the job planner refuses that repartition:

```
internal error: repartition is order-preserving and would result in incorrect results in distributed execution
```

## Environment

- Sail `main` at `99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2), unmodified, built with `cargo build --release --locked -p sail-cli`.
- DataFusion 55.1.0, as pinned by that commit.
- Client: PySpark 4.0.1 (Spark Connect), Python 3.12.8, pyarrow 25.0.1.
- macOS 26.2 on an Apple M1 Max. Local mode and `local-cluster` mode, default settings.

## Reproduce

```sh
python repro.py /path/to/release/sail
```

[`repro.py`](repro.py) starts its own server, runs the case, and stops the server. It needs `pyspark[connect]` 4.0 and `pyarrow`. The output of the run reported here is [`output.txt`](output.txt).

The table is four Parquet files, each sorted by `k`, behind `CREATE TABLE t (k BIGINT) USING parquet CLUSTERED BY (k) SORTED BY (k) INTO 4 BUCKETS LOCATION ...`.

## Observed

| Mode | `SELECT k, count(*) FROM t GROUP BY k` | The same files read by path |
|---|---|---|
| `local` | 1,000 groups | 1,000 groups |
| `local-cluster` | **internal error** | 1,000 groups |

The plan in both modes contains:

```
RepartitionExec: partitioning=Hash([#0@0], 10), input_partitions=10, preserve_order=true, sort_exprs=#0@0 ASC NULLS LAST
```

## Expected

The query runs in cluster mode and returns 1,000 groups.

## Cause

`crates/sail-execution/src/job_graph/planner.rs:463-471` returns the error for any `RepartitionExec` with `preserve_order()`. Its comment says no case had been found in which an order-preserving repartition is constructed. This is one: a scan with a declared order, several partitions, and an aggregate on the ordered key.

## Possible fix

Either support the order-preserving exchange (merge the sorted streams on the read side of the shuffle), or, when planning for cluster mode, replace it with a plain repartition and let the aggregate run in its unsorted mode.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

No existing issue or pull request found. Open pull request #1448 ("feat: implement bucketed Parquet read with shuffle elimination") works in the same area and lists distributed execution as not yet validated.

## Notes

- Only `local-cluster` mode was run, not a multi-process cluster.
- A join on the ordered key was not checked for the same failure.
