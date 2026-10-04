# `spark_partition_id()` and `monotonically_increasing_id()` fail outside a projection

**Kind:** query failure for expressions Spark accepts.

## Summary

Both functions work in `select` and `withColumn`. In a filter, a grouping expression or a sort key they fail:

```
spark_partition_id() was not rewritten into a partition-aware operator
```

In SQL, `GROUP BY spark_partition_id()` fails with a different message: `Non-deterministic expression spark_partition_id should not appear in an aggregate query`.

`df.groupBy(spark_partition_id()).count()` is the usual way to look at partition sizes in Spark.

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

On `spark.range(1000).repartition(4)`:

| Expression | Result |
|---|---|
| `select(spark_partition_id())` | values 0 to 3 |
| `withColumn("p", spark_partition_id()).groupBy("p").count()` | four groups of 250 |
| `groupBy(spark_partition_id()).count()` | **error**: not rewritten into a partition-aware operator |
| `filter(spark_partition_id() == 0).count()` | **error**: the same, inside a round-robin repartition |
| `orderBy(spark_partition_id())` | **error**: the same |
| SQL `GROUP BY spark_partition_id()` | **error**: non-deterministic expression in an aggregate query |
| `groupBy(monotonically_increasing_id() % 2).count()` | **error**: not rewritten |
| `filter(monotonically_increasing_id() < 5).count()` | **error**: not rewritten |

## Expected

The functions evaluate wherever an expression is allowed, as in the projection case. Spark accepts them in filters and grouping expressions; that is stated from Spark's documented behaviour and common use, and Spark was not run for this report. The sort-key case is not claimed for Spark.

## Cause

The functions are placeholders that a plan rewriter replaces with a column produced by a partition-aware operator. The rewriters are applied to projection lists only (`crates/sail-plan/src/resolver/query/lateral.rs:129-131`, `crates/sail-plan/src/resolver/query/aggregate.rs:272-274`). In a filter, a grouping expression or a sort key the placeholder survives to execution and raises the error (`crates/sail-function/src/scalar/misc/spark_partition_id.rs:45`, `monotonically_increasing_id.rs:45`).

## Possible fix

Apply the same rewrite to filter predicates, grouping expressions and sort keys: add the generated column below the operator and reference it. This is what the workaround does by hand with `withColumn`.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

**Partly known.** Open issue #1361 ("Expression rewriter for aggregates", 2026-02-12) lists `monotonically_increasing_id()` in `GROUP BY` and `ORDER BY` of aggregate queries as cases to handle. A review comment on pull request #1727 (2026-04-19) names the filter case exactly, and the reply defers it as follow-up work with a pointer to #1361. No issue was found that tracks the filter and sort-key cases or carries a reproducer. This report is best filed as a comment on #1361, or as a new issue that references it.

## Notes

- The workaround is to materialise the value with `withColumn` first.
