# Immutable graph snapshot qualification

Clean source `41afc40` on Capitola. Sequential commands, four nice jobs:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

Both exited zero: 28 tests passed, none failed or ignored. Regression covers
multi-batch/partition edge ordinals, loops, parallel/repeated/missing external
IDs, isolates, catalog replacement and shared UTF-8 values buffers. The earlier
failed offset-pointer assertion is retained: sliced offset buffers can advance
their pointer while retaining shared storage. The corrected assertion checks
the shared values buffer. No automatic routing, join execution, complete policy
admission or throughput conclusion is established by this qualification.
