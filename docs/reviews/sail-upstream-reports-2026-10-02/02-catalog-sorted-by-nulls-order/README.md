# A table declared `SORTED BY (c)` is read as sorted `NULLS LAST`: `ORDER BY c NULLS LAST` returns nulls first

**Kind:** wrong result order, silently. Also a missed optimization.

## Summary

For a catalog table created with `CLUSTERED BY (c) SORTED BY (c) INTO n BUCKETS`, Sail declares the scan's order as `c ASC NULLS LAST`. Spark's ascending order is nulls first, and that is how such a table's files are sorted. So:

- `ORDER BY c ASC NULLS LAST` is planned with no sort, and returns the nulls **first**;
- the default `ORDER BY c`, which is nulls first, keeps its `SortExec` although the files already have that order.

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

The table is one Parquet file holding five nulls followed by 0 to 99,999, which is ascending with nulls first.

## Observed

| Query | Source | `SortExec` in plan | First rows | Last rows | |
|---|---|---|---|---|---|
| `ORDER BY id ASC NULLS LAST` | table with `SORTED BY` | 0 | `NULL, NULL, NULL` | 99997, 99998, 99999 | **wrong** |
| `ORDER BY id ASC NULLS LAST` | same file read by path | 1 | 0, 1, 2 | `NULL, NULL, NULL` | correct |
| `ORDER BY id` | table with `SORTED BY` | 1 | `NULL, NULL, NULL` | 99997, 99998, 99999 | correct, sort not avoided |
| `ORDER BY id` | same file read by path | 1 | `NULL, NULL, NULL` | 99997, 99998, 99999 | correct |

## Expected

`ORDER BY id ASC NULLS LAST` returns the nulls last. Ideally the default `ORDER BY id` over the table needs no sort.

## Cause

The conversion of a catalog sort column to a sort expression hard-codes `nulls_first: false` (`crates/sail-common-datafusion/src/catalog/mod.rs:84-90`). The listing source passes that order to the scan (`crates/sail-data-source/src/listing/source.rs:268`), and the optimizer removes a sort that the declared order already satisfies.

## Possible fix

Set `nulls_first` to match Spark's default for the direction: nulls first for ascending, nulls last for descending.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

No issue found. **Open pull request #1857** ("perf: persist sort order from CTAS ORDER BY to eliminate redundant SortExec", opened 2026-05-05) changes the cause: its description says it stores `nulls_first` in `CatalogTableSort`, which "was always `false`, mismatching Spark's convention". It presents this as a performance change. The wrong result order shown here is not mentioned there. This report is best filed with a reference to #1857, or as a comment on it.

## Notes

- The file in the reproducer was written with pyarrow, in the order Spark uses for an ascending sort. Sail itself cannot write into a bucketed table today.
- Any declared order is trusted without a check. That is the nature of a declaration; this report is only about which order is declared.
