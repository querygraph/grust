# Facade feature forwarding qualification

Clean source `407ce61` on Capitola, four nice jobs. Both commands exited zero:

```sh
nice -n 10 cargo test --locked -p grust-graph --no-default-features --features cypher,datafusion --test datafusion_cypher -j 4
nice -n 10 cargo clippy --locked -p grust-graph --no-default-features --features cypher,datafusion --test datafusion_cypher -j 4 -- -D warnings
```

One end-to-end test passed using only facade imports for native Arrow capture,
typed Cypher execution and exact portable output. This isolated feature set
avoids workspace-wide feature unification masking missing forwarding. Cypher
alone still uses a weak optional-dependency feature and does not enable DataFusion.
