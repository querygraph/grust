# Wave 2 native gate

Observed 2026-10-06T21:55:12.235375+00:00. Source commit:
`a82a952943929bf780c8b197a27cd861c09a1a2b`.

**Wave2: PASSED native macOS x86_64 at a82a952943929bf780c8b197a27cd861c09a1a2b.**

Morrobay, Darwin x86_64, Rust/Cargo 1.98.1. Detached checkout:
`/Volumes/Apo/graph-tests/workspaces/grust-v2-wave2-20261006/gate`;
independent target `../gate-target`, incremental disabled, four build jobs.
The checkout was clean and its HEAD unchanged after the source gate. The
published Git tree exactly matched the locally gated candidate tree
`aba793a2c2736588071e46fe81744b46828537d3`.

| Check                                                                           | Outcome                     |
| ------------------------------------------------------------------------------- | --------------------------- |
| `cargo fmt --all -- --check`                                                    | Passed                      |
| `cargo clippy --workspace --all-targets --all-features -- -D warnings`          | Passed                      |
| `cargo test --workspace --all-features --release`                               | 35 unit tests passed        |
| `cargo test --workspace --release`                                              | 31 unit tests passed        |
| `cargo run --release -p grust-programmatic --example people`                    | Compiled and ran            |
| Prettier on changed Markdown; `git diff --check`; coordination conflict markers | Passed before source commit |

The Cargo commands ran in `docs/reviews/grust-v2/wave-2/sketch`.
[Full source gate log](evidence/native-source-gate.log).
Each test suite includes all six sketch crates; there are no doctests yet.
All tests construct small metadata/plans or exercise an inline executor fixture.
No concurrency runtime, graph execution, benchmark or Linux build is qualified.
The production Grust workspace was not changed or released by this gate.

Review: [draft PR #40](https://github.com/querygraph/grust/pull/40).
The receipt is a later documentation commit; the verdict above names the exact
source commit, not that later report commit or a prospective merge.
