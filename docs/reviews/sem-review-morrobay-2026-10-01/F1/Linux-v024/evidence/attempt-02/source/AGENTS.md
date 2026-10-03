# Agent Notes

## FirstPair Book Delivery

`FIRSTPAIR.md` is the required contract for this repository's unified book
build and FirstPair library deployment. Read and maintain it before changing or
delivering the book; it owns the catalog slug, shelf, and all source-side
handoff guidance. The shared implementation and authoritative operational rules
live in `~/src/firstpair`. Do not duplicate that deployment procedure here.

## Release Workflow

The step-by-step operational runbook is [`PUBLISH.md`](PUBLISH.md); the rules
below are authoritative.

- **Every release is named and fully documented.** Release names come from `RELEASES.md` (the crustacean list), assigned in order; mark the chosen name as the current release there. Each release MUST be accompanied by fully updated documentation — this includes rebuilding the Grust book (`docs/book`) so it reflects the released surface, and writing a release blog post at `docs/blog/grust-<release-name>/post.md` (e.g. `docs/blog/grust-crab/post.md`), with any diagrams under a sibling `diagrams/` directory. The post leads with the generic backend-neutral property-graph story (the Rust graph API and the multiple backends), links to the repo docs and the book for detail, and highlights the release's key innovations — it is not narrowed to any single backend or language feature.
- After substantial changes that affect any publishable Grust crate, do not stop at committing or pushing the repository. Verify the workspace and publish the affected crates to crates.io as part of the same release workflow.
- When substantial crate changes add, remove, rename, or materially change public APIs, examples, dependency-facing behavior, or release-facing prose, update the Grust book and rebuild the book artifacts as part of the same work.
- Before publishing, run the appropriate tests and `cargo package --workspace --allow-dirty` to validate the crate tarballs.
- Maintain `CHANGELOG.md` for every release-facing change. Add a dated version entry before committing a release, and keep entries grouped by logical user-visible changes rather than raw commit lists.
- Publish workspace crates in dependency order. Publish `grust-core` first, then backend and adapter crates such as `grust-memory`, `grust-cocoindex`, `grust-falkor`, `grust-helix`, `grust-lancedb`, `grust-pggraph`, `grust-sail`, and `grust-surreal`, and publish the facade package `grust-graph` last.
- After publishing, verify the released versions from outside the workspace with `cargo info <crate>@<version>` so local path dependencies cannot mask registry state.

## Benchmark Neutrality

- The benchmarks in this repository (`benchmarks/lsqb`) and the companion
  strain benchmark (`querygraph/adversarial-graph`) are neutral at every
  level: workload design, harness code, evidence, documentation, commit
  messages, and site prose. They measure and report; they do not pursue an
  outcome for any system, including Grust.
- Do not write, commit, or publish strategy about making one system look
  better or worse than another, in any file or commit message, at any time.
  State targets as engineering properties (exact answers, admitted queries,
  disclosed execution classes, resource envelopes, protocol parity), never as
  a contest against a named engine.
- Comparisons are evidence: same dataset, protocol, envelope, and execution
  class, with every outcome (pass, mismatch, unsupported, unavailable,
  timeout, error, not applicable) kept distinct and every failure retained.
  A faster or slower number is reported with its boundary, not framed as a
  win or a loss.
- If a document is found to violate this, fix the document and remove the
  violation from history; do not leave it in place with a disclaimer.

## Working Discipline

Every rule below was written after the failure it prevents happened here, to an
agent that knew better. The failure is named with each rule, because a rule
without its scar is forgettable and a rule with one is not. Most were the
coordinator's.

### Gates, and what a verdict covers

- **Make the commit conditional on the gates, in one `&&` chain.** Running gates
  and `git commit` on one line separated by `;` pushes code whose tests failed,
  and silently skips whatever else was downstream in the chain. This happened
  twice in one session: once pushing a branch with a failing test, once pushing
  with failing clippy and an unwritten changelog entry.
- **Run a gate in a detached worktree with its own target directory.** A gate in
  a checkout that also receives commits finishes on a different `HEAD` than it
  started on, and its verdict then names a commit nobody tested. A worktree *on a
  branch* is not enough: it cannot check out a branch another checkout holds, so
  it stays on the previous one and gates the wrong commit quietly. Use
  `git worktree add --detach <sha>`.
- **A verdict is valid only if the commit it names is the head it claims to
  verify**, and it covers that commit and nothing else. A branch verdict is not a
  verdict on the merge: two branches can each pass and their union fail. When a
  standing "verify main" task is posted, name the commit main had when the run
  started and recheck it against main's head before posting.
- **`scripts/ci-local.sh` enforces the first half of that** — it refuses to print
  a verdict if `HEAD` moved while it ran. Keep it and
  `.github/workflows/workspace.yml` in step: a gate added to one goes into the
  other in the same commit.
- **Before a long gate, check free disk; after it, expect none back.** One
  `target/debug` reached 320 GB, of which 39 GB was incremental state a gate
  never reuses. Set `CARGO_INCREMENTAL=0` for gate runs and clean between them.

### Concurrency

- **Do not believe a zero from one machine.** A work meter passed 360 runs on a
  laptop and CI twice, and still refused work that fitted; a second defect of the
  same kind passed everywhere except a starved CI runner. Stress a concurrency
  test in release with every core saturated (`yes > /dev/null` per core, or a
  container capped to a fraction of a CPU) before treating a passing run as
  evidence.
- **A test that races the clock must hold its window on the fastest machine as
  well as the slowest.** A deadline test gave a fixed 300 ms to a projection build
  followed by a PageRank "that never converges". It passed on a laptop and failed
  the Linux gate, because the build alone overran 300 ms on a loaded burstable
  host. It was then fixed by measuring the build and allowing twice that, which
  passed the saturated laptop, the gate and quegee's first run, and then failed on
  16 cores. There the "endless" kernel reached an exact floating-point fixed
  point in 264 iterations, inside the window. Saturating cores tests only the slow
  end. A window that must fall after one event and before another needs both ends
  argued: prove the second event cannot happen on test timescales at any width,
  by arithmetic about its work, rather than observing that it usually does not.
  Tolerance 0 is a stopping rule PageRank can meet, not a guarantee it never will.
- **A test that passes because its fixture is too small is not a test.** A
  determinism test had become vacuous: its graph sat below the threshold at which
  the kernel goes parallel, so it verified the sequential path at every thread
  count. Check that a fixture reaches the code it claims to exercise.
- **Partition by the input, never by the worker count, wherever a float sum is
  formed.** Combining partial sums in index order fixes their order, not their
  grouping; change the chunk length and the low bits change with it. Fixed
  partitions for reductions, width-dependent partitions for disjoint writes.

### Claims

- **A name inside a repository is evidence about naming, not about lineage,
  language or provenance.** A Rust workspace whose crates are called `icebug-*`
  is not Icebug; the names were kept for compatibility, and its own README says
  so one directory up. A benchmark column was labelled backwards from a
  directory listing before anyone opened the file that states the answer.
- **Do not publish an inference in the register of an observation.** "One
  correction, for the record: this host is c5-class" was read off a core count
  and a memory size, was wrong, and contradicted an agent who had it first-hand.
  If a claim was not checked, say which part was inferred, or check it.
- **Check the premise of an argument before shipping the argument.** A design
  document argued for its central choice on the grounds that the alternative
  "breaks every caller"; counting the call sites showed it would break one. The
  conclusion survived on its other reasons, but the document would have carried a
  false premise into every later decision that cited it.
- **Run the cheapest experiment that could refute a cause before reporting the
  cause.** Two agents independently produced coherent accounts of the same five
  error messages, endorsed each other's, and called a release blocker. The true
  cause was in neither: a stale build directory. One clean-directory run, thirteen
  minutes on an idle box, would have shown it, and an idle box was free
  throughout. **A failure that fits a plausible story is the most dangerous
  kind**, because the story ends the search. Say "unexplained" when the control
  has not been run.
- **Generate a timestamp in the same command that writes it.** Hand-written times
  agreed with each other and drifted a day from the clock, which is worse than no
  time at all: two agents corroborating one wrong number.
- **A deferred edit is a failing test or it does not exist.** A `// when X lands,
  add the guard here` comment survived X landing. The catalog test caught it; the
  comment did not.
- **When a test fails, fix the subject or the fixture, not the assertion.**
  Loosening an assertion until it passes destroys the evidence. Where a bound is
  genuinely too tight — comparing a value formed by summation against a literal
  quotient, for instance — state in the test why the looser bound is the right
  one and what stronger property is pinned elsewhere.

### Coordination between agents

- **Name the repository in any task that is not this one.** An agent rewrote
  three commits another had already pushed to a second repository, because every
  task until then had been about Grust. Fetch every repository a task touches
  before starting it.
- **Append to the coordination log; never rewrite another agent's entry.** Check
  for conflict markers before pushing it:
  `! grep -nE '^(<<<<<<<|=======|>>>>>>>)( |$)' codex-to-codex.md`. Removing a
  stray marker is the one edit to another's text that needs no permission,
  because a marker is nobody's words.
- **Post `ACK` on starting, `DONE` with evidence, `BLOCKED` with the specific
  need. Do not post heartbeats.** Silence between those means work is running.
  Fewer appends is also fewer conflicts.
- **Evidence, not adjectives.** For code: branch, commit, and the gate's verdict
  line. For timing: host, commit, command, and every cell, including the ones
  that got worse.

### Measurement on shared hosts

- **Steal on a burstable instance tracks the credit balance, not the hardware.**
  The same box read 0.0% steal after eight idle days and 15.8–33.1% under a long
  sweep. A quiet reading is evidence of credits, not of dedicated cores, and a
  sweep that exhausts them measures its later cells on a throttled machine and
  its earlier ones on a fast one — biasing a before/after ratio by sweep order.
- **Dispersion does not detect steal.** Sub-percent deviation held while a third
  of busy CPU was being taken. Report the steal figure with any timing.
- **Publish timings from a dedicated host only**, and label every other host's
  numbers as ratios on a shared box, never as absolute results.

## File Discipline

- Prefer keeping source and documentation files under 500 lines, and try to keep
  them under 1000 lines when practical. Do not treat either number as a hard
  limit when splitting would harm the logic or make the code harder to follow.
  If an existing file is already over the practical limit, prefer adding new
  related code to a focused module/file instead of making the oversized file
  larger.
- When a change genuinely belongs in an oversized file, keep the edit tightly
  scoped and avoid opportunistic reformatting or refactors.
