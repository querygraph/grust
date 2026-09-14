# Queue component qualification at 870cf42

The isolated production queue and its six deterministic cancellation/error
regressions passed on Capitola: six passed, zero failed, zero ignored.
`component-tests.log` retains all compiler warnings and results. The harness
excludes only the backend-dependent test module; `SOURCE.json` records the
production source hash. It uses the qualified Ostracod core at `28d2471`.

The retained Cargo manifest has its original absolute native core path; adjust
that path to an equivalent checkout when reproducing elsewhere. Dependencies
are pinned in the retained lockfile. Command: `CARGO_BUILD_JOBS=1 nice -n 10
cargo test --offline`. No timeout or sleep-based race test is used.

The original failed handoff schedule remains in
`../lancedb-0176718-reproducer`. These results qualify only the queue component.
Full LanceDB adapter tests and warnings-denied Clippy are running separately
against branch source `870cf42`; integration against current main and complete
release qualification remain outstanding. No benchmark pin changed.
