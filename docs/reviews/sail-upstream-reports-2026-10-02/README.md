# Sail: reports for upstream, each standalone

Prepared 2026-10-02 and **filed the same day as issues #2722 to #2732 in
`lakehq/sail`**, at the user's instruction (table below). Each folder is one
report that stands on its own: a description, a reproducer that needs
only a Sail binary, the output of that reproducer, the cause in the code and
a possible fix. No report depends on another, on any extension, or on
anything outside its folder.

All were reproduced on unmodified Sail `main` at
`99ee46f69a97342e91bf7d4eaedb4509f1d8a9c2` (2026-10-02, version 0.7.2,
DataFusion 55.1.0), release build, macOS on an Apple M1 Max, with PySpark
4.0.1 as the Spark Connect client.

| # | Report | Kind | Reproducer needs |
|---|---|---|---|
| 01 | [`checkpoint()` after a sort returns wrong results](01-checkpoint-after-sort-wrong-results/README.md) | wrong results | a checkpoint path |
| 02 | [`SORTED BY` is read as `NULLS LAST`: `ORDER BY c NULLS LAST` returns nulls first](02-catalog-sorted-by-nulls-order/README.md) | wrong result order | defaults |
| 03 | [In cluster mode, `GROUP BY` over a table with a declared sort order fails](03-cluster-group-by-over-sorted-table-fails/README.md) | query failure | `local-cluster` mode |
| 04 | [`EXPLAIN` fails for a sort-merge join that executes correctly](04-explain-fails-for-sort-merge-join/README.md) | `EXPLAIN` failure | `prefer_hash_join=false` |
| 05 | [A sort before a Delta write is removed](05-sort-before-delta-write-is-dropped/README.md) | behaviour differs between sinks | defaults |
| 06 | [`DataFrameWriter.sortBy` fails to resolve a column that exists](06-writer-sortby-cannot-resolve-column/README.md) | misleading error | defaults |
| 07 | [`repartitionByRange` hash-partitions, silently](07-repartition-by-range-is-hash/README.md) | semantic difference from Spark | defaults |
| 08 | [`spark_partition_id()` and `monotonically_increasing_id()` fail outside a projection](08-partition-id-outside-projection-fails/README.md) | query failure | defaults |
| 09 | [The sort order in a Parquet footer is never used](09-parquet-sorting-columns-never-used/README.md) | missed optimization | defaults |
| 10 | [`partitionBy` writes are 5 to 45 times slower than plain writes](10-partitionby-write-slow/README.md) | performance | defaults |
| 11 | [A sort before `monotonically_increasing_id()` is removed](11-sort-before-monotonic-id-is-dropped/README.md) | wrong values | defaults |
| 12 | [A sort before a Parquet write is dropped with `mode("overwrite")`](12-overwrite-write-drops-sort/README.md) | behaviour differs between save modes | defaults |

Reports 01 to 10 are in order of severity: answers that are wrong first,
then failures, then behaviour, then speed. Report 11 was found later the same
day and belongs with the first two; it was filed as #2732. Report 12 was found on 2026-10-03 by the visualization study. **It is prepared and not filed.**

## Filed

| # | Issue |
|---|---|
| 01 | [#2722](https://github.com/lakehq/sail/issues/2722) |
| 02 | [#2723](https://github.com/lakehq/sail/issues/2723) |
| 03 | [#2724](https://github.com/lakehq/sail/issues/2724) |
| 04 | [#2725](https://github.com/lakehq/sail/issues/2725) |
| 05 | [#2726](https://github.com/lakehq/sail/issues/2726) |
| 06 | [#2727](https://github.com/lakehq/sail/issues/2727) |
| 07 | [#2728](https://github.com/lakehq/sail/issues/2728) |
| 08 | [#2729](https://github.com/lakehq/sail/issues/2729) |
| 09 | [#2730](https://github.com/lakehq/sail/issues/2730) |
| 10 | [#2731](https://github.com/lakehq/sail/issues/2731) |
| 11 | [#2732](https://github.com/lakehq/sail/issues/2732) |

## Filing

[`issues/`](issues/) holds a title and a body per report, ready to file: the
report's text with its reproducer and output inlined, and no link to
anything outside the issue. `issues/file_issues.sh` files them in order with
`gh issue create` and records the URLs in `issues/filed.txt`. It was run
on 2026-10-02; rerunning it files nothing, because every report is recorded.

## Running a reproducer

```sh
python <folder>/repro.py /path/to/release/sail
```

Each script starts its own server on a free port with the settings its
report names, runs, prints, and stops the server. It needs
`pyspark[connect]` 4.0 and `pyarrow` in the Python that runs it. The server
embeds Python, so the script points it at that same environment.

## Existing upstream items

`lakehq/sail` issues and pull requests were searched on 2026-10-02 (read
only). Each report has the detail in its "Related upstream items" section.

| # | Found |
|---|---|
| 01 | nothing |
| 02 | no issue; open pull request #1857 fixes the cause as a performance change and does not mention the wrong order |
| 03 | nothing; open pull request #1448 is in the same area |
| 04 | nothing |
| 05 | no issue for Delta; open pull request #1862 reports the same symptom for CTAS to Parquet |
| 06 | nothing |
| 07 | nothing |
| 08 | **partly known**: open issue #1361 covers the aggregate cases; a review comment on #1727 names the filter case and defers it |
| 09 | nothing |
| 10 | no issue; open pull request #1360 addresses Delta partitioned writes; DataFusion's tracker search was incomplete |
| 11 | nothing; merged pull request #1936 is about the operator's partitioning |
| 12 | nothing; open pull request #1862 reports a dropped sort for CTAS |

So none is an exact duplicate of an open issue. 02 and 08 should reference
the existing items rather than stand alone.

## What was not done

- No fix was built or tested. The "possible fix" sections come from reading
  the code.
- Nothing was run on a multi-process cluster, on Linux, or against an object
  store. Cluster evidence is `local-cluster` mode.
- Statements about Spark's behaviour come from its documentation and common
  use. Spark itself was not run.
