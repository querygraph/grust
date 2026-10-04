# `DataFrameWriter.sortBy` fails to resolve a column that exists

**Kind:** misleading error; `sortBy` unusable.

## Summary

Any write that uses `sortBy` fails with

```
attribute ObjectName([Identifier("k")]) is missing from the schema: cannot resolve attribute
```

although `k` is a column of the frame. It happens for Parquet and Delta, with and without `bucketBy`, for `save` and `saveAsTable`.

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

The frame has columns `k` and `v`.

| Write | Result |
|---|---|
| `write.bucketBy(4, "k").sortBy("k").saveAsTable(...)` | `attribute ... "k" is missing from the schema` |
| `write.bucketBy(4, "k").saveAsTable(...)` | `bucketing for writing listing data source` (a clear "not supported") |
| `write.sortBy("k").parquet(path)` | `attribute ... "k" is missing from the schema` |
| `write.format("delta").sortBy("k").save(path)` | `attribute ... "k" is missing from the schema` |

## Expected

The sort column resolves. The write then either sorts, or reports plainly that bucketing or `sortBy` is not supported, as the second row does.

## Cause

Inferred from the code, not confirmed by a fix: `crates/sail-plan/src/resolver/command/write.rs:240` resolves the sort columns against the write input after that input has been renamed to user-facing column names (`write.rs:550-558`), while the resolver state knows the columns by their internal names.

## Possible fix

Resolve the sort columns before the input is renamed, as the partition columns are, or resolve them against the renamed schema by name.

## Related upstream items

Searched in `lakehq/sail` issues and pull requests on 2026-10-02.

No existing issue or pull request found.

## Notes

- Both sinks already accept a sort order (`crates/sail-data-source/src/formats/parquet/write.rs:36`, `crates/sail-delta-lake/src/lake_source.rs:602`), so only the resolution stands in the way.
