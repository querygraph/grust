# Typed Cypher binding qualification

Source: `1c9475a`, clean Capitola checkout. Commands executed sequentially with
four nice Cargo jobs:

```sh
nice -n 10 cargo test -p grust-datafusion --all-features -j 4
nice -n 10 cargo clippy -p grust-datafusion --all-features --all-targets -j 4 -- -D warnings
```

Both exited zero. 27 tests passed, zero failed or ignored. The new executed
multi-binding cases cover literal dotted columns, nullable predicates, distinct
count, count, extrema and explicit unknown-variable/type rejection. This is
compiler qualification, not relationship-join, automatic-route or performance
evidence. Full workspace/release qualification remains pending.
