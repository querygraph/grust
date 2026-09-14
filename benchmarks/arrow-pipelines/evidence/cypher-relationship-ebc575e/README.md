# Directed endpoint-join qualification

Clean source `ebc575e` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

29 tests passed, zero failed or ignored. Executed endpoint-join rows are checked
against source edge ordinal/from/to tuples, covering parallel edges, loops,
reverse edges, isolates and empty input. Dotted variable names resolve to
independent physical columns. The initial missing collection-type build failure
is retained. This establishes operator correctness for these cases, not parsed
relationship-pattern support, automatic routing, resource-policy parity or speed.
