# Explicit Cypher execution qualification

Clean source `95cb7c8` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test --locked -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy --locked -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

36 tests passed, zero failed or ignored. The end-to-end text entrypoint compares
parameterized node, directed and undirected results with the portable executor.
It separately checks unsupported paths, parse errors, semantic errors, row-limit
and byte-limit errors. The initial parser diagnostic conversion build failure is
retained. This is explicit DataFusion execution with output limits, not automatic
cost-based routing or complete read-policy admission.
