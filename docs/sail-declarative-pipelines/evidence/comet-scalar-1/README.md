# Standalone Comet scalar work and human-review compendium

The goal remains active. `HUMAN-REVIEW.md` is the maintained, self-contained overall
compendium for SDP, existing Extensions, the Comet C route and performance work.
The seven specialty reports here review that compendium/design; they do not yet
constitute final cumulative adapter source approval.

The unique detached implementation worktree is
`/Users/alexy/src/sail/tmp/comet-scalar-20261105-2c9fa8499`, based on
`2c9fa84994d317aade0d1c69faa9a378c780127d`. It ports standalone prototype
`ef7286ca2` and repairs callback-code lifetime and argument fields. Committed
E1/E3/E4 and extension integration plans preceded the port. The focused standalone
plan further records admission, ownership, field agreement and verification.

## Recorded source and execution

`candidate-snapshot.json` records staged tree
`d8e9633355f2bac78ab9470e49aceda1992d2388`, the twelve changed files and their
hashes. Increment patch SHA-256 is
`0561254aaed99782dd50a4901f4c28162f799748cfcdac7dd6f5f6ea08676d64`.
The cumulative patch against upstream `b52144955b` has SHA-256
`59706bb772a2ef606b2bab5657fbe2fe8f18507661110eb0baf53dac50caa376`.
Both full patches remain local in `review-logs/`; source is uncommitted and unpushed.

`negative-controls.json` describes the original UDF plus compatible loader API
with retention disabled. The lifetime test failed deterministically. Cargo stopped
after that test binary; no claim is made that this run executed all metadata cases.
`metadata-negative-control.json` records a separate original-UDF run with the fixed
loader: six metadata tests failed and two passed. Both scripts restored candidate
source in `finally` and retained the exact control source files locally.

`candidate-focused-checks.json` records the fresh fixture build, thirteen passing
tests and strict affected-crate all-target/all-feature Clippy. Formatting also
passed before staging. These checks cover the WIP candidate, not an immutable
source commit or the whole pipeline integration gate.

The independent producer uses pinned Comet commit
`0f7f8e45399847715093b3d3affdfa97614b39dc`. Its unchanged SDK/test sources and
member manifests were built in a minimal isolated workspace with inherited fields
from the original parent manifest and Arrow 59.2.0. `comet-producer-build.json`
records hashes, command and successful build. This is not a full Comet build.
Fetching the top-level `LICENSE` path returned 404 after source acquisition; it
was an acquisition-path failure, not a producer compile or runtime failure.

The explicit temporary producer probe passed two tests, covering ordinary results,
nulls/order, retained output and SDK containment of initialization/execution panics.
It was preserved under `review-logs/comet-producer/staged-interop-probe.rs` after
execution, outside the ordinary test tree because it requires the independently
built library. Its log and source are hashed in `artifact-manifest.json`.

## Remaining qualification

Final seven-role cumulative source review, required gates on an immutable source
commit, and source readiness remain pending. The explicit unsafe producer contract
and numeric version probe do not establish arbitrary-library safety. Standalone
process retention is not an admission bound or a package identity mechanism.
Worker/package integration, Spark SQL runtime behavior, durable replay, checkpoint
alignment, fencing and C relations remain later work under the full objective.

The existing runtime, prototypes and foundation worktrees were preserved. The new
worktree owns its target directory; no product environment was modified. Raw logs,
patches, producer sources, manifests and binaries remain local. Selected receipts
are copied here and local artifacts are hashed. No cleanup or remote source action
was performed. Earlier documentation pushes returned GitHub's
`fatal error in commit_refs_rules`; a later retry successfully published the
compendium and preceding documentation through `d5bc76fb`.
