# Parsed fixed-length path qualification

Clean source `2e97234` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test --locked -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy --locked -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

37 tests passed, zero failed or ignored. The relationship differential test now
checks 35 parsed queries against portable columns/rows. Added paths include two
and three hops, repeated-node cycles, undirected paths, mixed directions,
labels/types, parameterized property maps, identity predicates and grouped
endpoint counts. Existing exhaustive trail tests retain physical edge-uniqueness
coverage. Unsupported-entrypoint tests now use variable-length bounds, since
fixed two-hop queries are supported. This does not qualify variable-length paths,
automatic cost routing, complete policies or path throughput.
