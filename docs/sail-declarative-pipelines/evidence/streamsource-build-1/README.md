# StreamSource foundation implementation evidence

This record qualifies a local source implementation, not an upstream offer or
the durable pipeline replacement. The final immutable gate passed on commit
`2c9fa84994d317aade0d1c69faa9a378c780127d`, tree
`5d67cdc81cdd9ba7eb18a74eda17d84b9e5d30c7`. Its complete 19-file binary-capable
diff against `b52144955b629314a000b1fe49eeea97fa3d0c5c` has SHA-256
`bda65fdba075378f3088a2b00681fdf63f57b9d9a66722ec78c8e1f688220163`.

The local branch is `work/streamsource-foundation-20261105`. The detached gate
worktree is `/Users/alexy/src/sail/tmp/streamsource-build-20261105-b52144955`.
Its `review-logs/` directory retains full logs, source patches, rejected
experiments, probe sources and copied binaries. No source branch was pushed.
The existing pipeline and prototype worktrees were preserved.

## Designs preceding implementation

| Design | Documentation commit | Local implementation commit |
| --- | --- | --- |
| Event fidelity | `4e2c40e7` | `60b98ba03692e91289c6a009d635e64dfe2be3c0` |
| Data-only expressions | `207e715e` | `e432a464f03f8b4567d429fc44ad3e5b15c04143`, filter subset only |
| Failure propagation and atomic terminal publication | `b8af1d2e`, `2192b091` | `d57946ee24199b3287386aebd64c87cf9ee68211` |
| Lossless exception protocol | `70c6a7c6` | Included in `d57946ee24199b3287386aebd64c87cf9ee68211` |
| Preserve existing console lock scope and active-list allocation costs | Corrections within the preceding failure design | `2c9fa84994d317aade0d1c69faa9a378c780127d` |

The notes are concrete review material, not a claim of maintainer approval.
The new filter-batching note records a decision before any coalescing implementation.

## Final gate and environment

`logs/immutable-gate/receipt.json` records every command, exit status, source
pin and unchanged-source check. `logs/immutable-public-receipt.json` records
the public test invocation against the freshly copied command-line binary.
Raw logs and CSV inputs retain their original whitespace and line endings.
Documentation whitespace checks exclude those exact copies; their hashes are verified.

- Workspace nextest: **2,017 passed, one skipped**. The ignored test is
  `untyped_limit_parameter_remains_inferable_after_coercion`, already ignored
  in the upstream base. No new skip was introduced.
- Strict workspace Clippy: all targets and all features passed with warnings denied.
- Nightly Rust formatting and Hatch formatting for the changed Python files passed.
- A fresh default-feature `sail-cli` build completed. **Ten live server tests and
  nine PySpark client fixtures with mocked transport passed**, 19 tests in total.
  Binary SHA-256: `6d236fdb26ca14dc892ee84f882d8db9db2d81793aded534d8f3b39c13e18112`.
- Before the first three local commits, 232 affected Rust tests and 19 public
  tests passed. After the cost correction, 134 affected Rust tests and the same
  19 public tests passed. These are overlapping runs, not additional unique tests.

Rust was 1.98.1 on `aarch64-apple-darwin`, using the locked Arrow 59.2.0 and
DataFusion 55.2.0 dependencies. Each worktree owns its target directory.
Incremental builds were disabled. Detailed environment and lock hash are in
`logs/immutable-source.json`; that earlier snapshot says the final gate was
running, and the completed receipt supersedes only that status.

The unchanged product virtual environment supplied PySpark 4.2.1 and PyArrow 26.
Upstream development configuration declares PyArrow 24, so this is an environment
difference, not full wheel qualification. A correctly featured Maturin wheel
provided the native module needed by test fixtures. The ten live tests connected
remotely to the freshly built standalone server, not that fixture module’s runtime.
The other nine fixtures exercise the actual client’s protobuf and exception decoding.

The full integration-branch pipeline, frozen Spark-port, metastore/profile and
name-by-name Delta qualification was not run on this upstream-based reference.
No integration landing or upstream readiness is claimed. The unresolved dense-marker
performance regression also prevents a general readiness claim.

## Controls and retained failures

| Control | Observed result |
| --- | --- |
| New fidelity tests with original production code | 13 failed, two passed; original 62 tests passed |
| Initial filter tests with original filter | Five failed, one passed |
| Rate public tests with baseline server | Two failed, five passed |
| Query failure tests with original manager | Four failed, one normal-completion test passed |
| Console failure tests with original sink | Two failed |
| Public failure test with baseline server | Failed because termination did not raise |
| Split terminal-state candidate | Two deterministic publication-order tests failed |
| Repaired manager with original wire format | One live test failed with client `IndexError`; nine client fixtures passed |

The final tests pass without weakening those assertions. The split-publication
counterexample remains a separate local patch, not production code. Producer and
client tests cover plain, colon-containing, Unicode and empty causes; condition
names remain distinct from exception classes.

Setup failures remain in separate local logs listed in the artifact manifest: default Rust
1.97.1 was below the dependency floor; missing native fixtures and an incorrectly
featured raw extension prevented fixture import; an absent Maturin path was
corrected. An initial test selector selected zero tests and was rerun correctly.
Formatting failures were repaired. None is counted as a semantic counterexample.

## Performance and review boundaries

The two filter comparisons use the same 12 cells, seven alternating-order paired
samples per cell, exact ordered-output checks and an unoptimized build. All cells,
including slowdowns, appear in the copied ratio summaries. Raw samples, source
snapshots and harnesses remain local and are hashed in `artifact-manifest.json`.
These shared-host diagnostics have no CPU isolation or steal measurement and
establish no absolute production throughput or memory envelope.

The final data-only median ratios were 0.9915–1.0052. Alternating-marker ratios
were 17.8927–141.1032, with 65,536 output batches. Source review closed unnecessary
input retention, per-batch dispatch, stdout-lock and inactive-query allocation
costs. Dense-marker fragmentation remains unresolved.

All seven required specialty reports in this directory identify the final source
pin or its exact reviewed cumulative patch plus correction. Their pending-gate
statements record their review time; the final immutable receipt supplies the
completed execution verdict. Reviewers distinguish inspection from tests executed
by the integration owner.

Spark 4.2.1 source was inspected at
`617618396087429b5627a86ce933bb0f5d6645cb`. Actual PySpark client behavior was
tested against Sail. No fresh Spark-engine differential run was performed.
Projection, asynchronous expressions, planner simplification, distributed
checkpoint alignment, durable preparation, target fencing, change-capture merges
and strict configuration/Dhall remain unimplemented in this increment.

The saved request and all governing files were read and distributed to the seven
specialist roles. The lead reread them after compaction. Reader-facing documents
were reviewed against `CLARITY.md` and `WRITING-RULES.md`. Artifacts were retained;
no cleanup, remote source mutation or maintainer communication was performed.
