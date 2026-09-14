# Common snapshot planner qualification

Clean source `ef54c92` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

32 tests passed, zero failed or ignored. Common-entrypoint regression verifies
node/relationship shape selection with executed counts, explicit rejection of
multi-hop shape and propagation of semantic errors. Existing compiler tests
remain passing. This selects a compiler, not a cost-based executor; automatic
ordinary Cypher routing and complete resource-policy admission remain pending.
