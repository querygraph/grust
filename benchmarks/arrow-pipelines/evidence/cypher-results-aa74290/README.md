# Portable result conversion qualification

Clean source `aa74290` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

34 tests passed, zero failed or ignored. New decoder checks cover exact Int64
limits, Boolean values, UTF-8/empty strings, nulls, duplicate column names,
sliced/empty batches and rejection of Float64. All 28 relationship differential
queries now use the production decoder against portable columns/rows. This
qualifies result semantics for the admitted scalar domain, not memory/output
policy enforcement, complete query routing or performance.
