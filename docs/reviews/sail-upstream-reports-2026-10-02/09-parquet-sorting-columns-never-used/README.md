# The sort order in a Parquet footer (`sorting_columns`) is never used

**Kind:** missed optimization; the code that would use it is unreachable.

## Summary

A Parquet file whose footer declares `sorting_columns` is read with no declared order. `ORDER BY` on that column still plans a `SortExec`. Sail has code to derive a scan's order from Parquet footers, but the path that reaches it is never taken for a read by path.

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

The file holds `id` from 0 to 199,999 in order, written by pyarrow with `sorting_columns=[SortingColumn(0, descending=False, nulls_first=True)]`.

## Observed

```
footer sorting_columns: (SortingColumn(column_index=0, descending=False, nulls_first=True),)
ORDER BY id                  | SortExec in plan: 1
ORDER BY id ASC NULLS FIRST  | SortExec in plan: 1
ORDER BY id ASC NULLS LAST   | SortExec in plan: 1
```

## Expected

`ORDER BY id` (ascending, nulls first) over this file needs no sort.

## Cause

The listing planner derives an order from the footers only when the source has no configured sort order: `try_create_output_ordering` in `crates/sail-data-source/src/listing/planner.rs:264-276` returns early when `file_sort_order` is not empty, and otherwise calls `ordering_from_parquet_metadata` (`crates/sail-data-source/src/formats/parquet/read.rs:206`). But the listing source always passes `file_sort_order: vec![sort_order]` (`crates/sail-data-source/src/listing/source.rs:268`), a list of one element even when `sort_order` itself is empty. So the early return is always taken.

## Possible fix

Pass an empty `file_sort_order` when the table has no sort order: `if sort_order.is_empty() { vec![] } else { vec![sort_order] }`.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

No existing issue or pull request found. Open pull request #1857 also wires `file_sort_order`, from table metadata rather than from footers.

## Notes

- Not checked: whether the derived order is then correct for a multi-file scan, where the files' key ranges may overlap. The declared order must hold per partition, so file grouping matters.
- Sail does not write `sorting_columns` itself: DataFusion writes them only when the sink is given a sort requirement, which would come from `sortBy`.
