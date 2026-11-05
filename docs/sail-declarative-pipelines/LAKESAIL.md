# How we do software for Sail

What this project learned, from the first milestone through the maintainers'
feedback and the redesign, about building for Sail and offering work to
LakeSail. Each entry is a practice and the reason it exists. SHEHAB.md holds
the maintainers' own rules verbatim; WRITING-RULES.md holds the writing
standard. This file is the rest.

## Working with the maintainers

- **Design agreement comes before code.** The maintainers review architecture,
  not finished systems; a large body of code arriving for review is "too late
  for human intervention". Present each design question as a one-page note
  with options and a recommendation, in their discussion threads, and build
  only what a note's answer allows.
- **A few large reference PRs, then a gradual path.** Forty PRs exceed their
  bandwidth. Offer the work as reference material and let them choose which
  pieces move to `main`, piece by piece, with a design conversation before
  each.
- **Only propose what you understand.** Read the code before cutting a PR and
  assess by hand how it fits `main`. A PR the author cannot explain line by
  line is not opened.
- **Their streaming foundation is the continuous flow-event model**, with
  stream sources, retractable batches and markers. Bounded microbatches are a
  direction they will not take. Build on their model, add what it leaves room
  for, and change none of its contracts without asking.
- **Engineering quality governs; Spark conformance is not a design constraint.**
  Retain Spark behavior only when it serves the intended contract. Reverse
  compatibility choices that introduce nondeterminism, weaker durability,
  brittle configuration or needless architectural cost. Explain and verify
  intentional differences. Build missing fencing for every admitted durable
  target; neither catalog serialization nor an external single-writer
  convention replaces commit-time ownership enforcement.
- **Verify semantics at Spark's source**, not from memory and not from test
  names: the 4.2.1 source is the reference, and a document states what was
  read, what was run, and what remains uncertain.
- **Dependency ownership is a design choice.** When a dependency must behave
  differently, copying the upstream code into Sail with a `[CREDIT]` line and
  a pinned source beats a workaround layered around it; the diff against
  upstream holds only the needed change. A vendored crate is never proposed;
  fixes go upstream first.
- **Every outward document is read once, end to end, as the maintainers
  will read it**: no internal names, every concept defined before use, the
  situation before each decision, under two thousand words. The maintainers'
  agent rules add a seven-role adversarial review of any cumulative patch
  before it is offered.

## Integration discipline

- **One integration branch, one gate, one landing path.** Every unit lands
  through a full gate on an immutable detached commit with its own target
  directory: format, strict clippy, library tests, a CLI build, the frozen
  Spark ports, the pipeline suites, the CLI and metastore profiles, and the
  Delta suite compared name by name against its baseline. Landing refuses a
  commit whose tree or parent differs from what was gated. This rule came
  from two faulty landings.
- **Check the build line.** A gate's binary step must print its "Finished"
  line and the gate must fail if it does not. Our scripts once passed a
  cargo flag as a single shell word; cargo refused, and the suites ran for a
  whole unit against the previous build in the gate tree. Never reuse a
  gate-tree binary across units; copy the binary the moment it is built.
- **Build what the wheel builds.** Optional cargo features that the branch
  wheel keeps on (`iggy`, `orc`) must be on in every binary the gates run,
  including the one the frozen harness builds for itself, and the receipt
  records the feature set.
- **Snapshot everything a unit touches.** The landing snapshot lists the
  paths it copies; a root file left off the list (`Cargo.toml` once,
  `.gitignore` and `pyproject.toml` later) silently drops part of a unit.
- **Never share a target directory between two checkouts** of the workspace;
  artifacts contaminate each other. Each worktree gets its own.
- **Watch the disk.** Cargo targets grew to three hundred gigabytes and a full
  disk produced a hundred and seventy spurious test errors. Clean the product
  tree's target before gates; keep only the gate binaries that evidence
  references.
- **Honest records.** Failed runs are kept and never relabelled; a recorded
  incompatibility is never counted as a match; no upstream assertion is
  removed, no expected failure added, no table swapped for a view to obtain a
  pass. A test is called a Spark difference only after it ran on Spark alone
  in a fresh session with an empty warehouse. A fix counts only when a
  control run without it fails the new tests.
- **Compare the whole tree against upstream**, not only against the last
  root, so a regression outside the suites under work is seen.
- **Evidence travels with the unit.** A unit that changes behavior carries
  its receipts: counts, commits, hashes, the command, and what was not run.
  Binary evidence bundles are gitignored by the root's `*.gz` rule; the rule
  must be negated for the review's bundles or only their checksums land.

## Two lanes, one log

- **Coordinate through one append-only log**, written only through its
  locking helper, with message ids and a seen-through mark. Post scope once;
  after that only shared-interface questions, blockers, and gated offers.
  Declare an overlapping shared-file change before making it. One writer per
  file: a reviewer sends findings, the owner folds them.
- **Integration stays with one lane**, which gates every offer on the
  combined tree and never rewrites offered history. The other lane never
  moves the root.
- **A fresh session is briefed in one self-contained post**: root, state of
  every open item, the documents to read, and the ask. The peer's model may
  change mid-project.
- **Prototypes are one-test claims**, local and unpushed, each answering one
  decision note; what each showed is folded into the note the same day, and
  a results document says what the set establishes and what it does not.

## Sail itself, as we found it

- **Local mode has no driver.** The local job runner executes the plan in
  the session's process; only cluster modes start a driver, and a stream
  source's scan is rebuilt on a worker by the plan codec. Anything that must
  reach a source in cluster mode goes through the task that runs it.
- **The flow-event model has the pieces but not the machinery.** Four markers
  exist (latency, watermark, checkpoint, end of data) and the end-of-data
  marker already defines a run that ends; the native rate and socket sources do not provide recoverable checkpoint
  participation. Marker encoding, expression isolation, transport alignment
  and completion need repairs. Windows, aggregates, joins and repartitions
  remain unsupported by the streaming rewriter. Persist a fixed prepared
  boundary before output effects and reconcile each effect afterward; recording
  positions alone does not establish recovery.
- **The session lifecycle is a state machine** (creating, running, deleting,
  deletion failed, deleted, failed) with one cleanup record for every delete
  and shutdown path, and a tombstone for a deleted session. Effects are owned
  by the operation; a prefix is deleted only after its effects settled.
- **The data-source options generator** builds option structs from YAML at
  build time and emits `crate::options` paths; a format moved into its own
  crate re-exports those paths. The host registers formats in one place,
  which is where a feature-gated format gets its named refusal.
- **A feature-gated optional crate is the pattern** for anything a default
  build should not carry (a broker client, a file format): optional
  dependency, forwarded feature on the CLI and Python crates, the leaf under
  `cfg`, a refusal that names the feature, the branch wheel keeping the
  feature on.
- **The extension host identity is derived from `Cargo.lock` at build
  time**, and a package's declared versions are refused on mismatch before
  anything binds. Native memory is funded through a small C lease. The
  Arrow-only C scalar boundary (Sedona's, adopted by Comet) is small enough
  to carry without either project's crate.
- **Delta's idempotent writes** (`txnAppId`, `txnVersion`) are the native tag
  for an exactly-once checkpoint commit; the table skips a version it already
  holds.
- **An external client's dependency floor can keep a crate off `main`.** The
  Iggy client needs newer HTTP and QUIC crates than upstream's lockfile
  holds; moving two hundred packages is not a reviewable change.
- **The product venv must stay on PySpark 4.2.1.** The examples' lock pins
  4.0.1; installing it into the product venv removes the pipelines client.

## Tooling pitfalls

- In zsh, `${X:+--features $X}` is one word; use an array. A word starting
  with `=` is a command lookup. A glob with no match aborts the command
  unless the nomatch option is off.
- The session's permission classifier refuses to build or run downloaded
  code; read it, restate it with attribution, and let the owner build the
  external fixture.
- Upstream's docs site formats Markdown with its own Prettier plugins; run
  Prettier from a checkout that has them, or CI fails on a blank line.
- A gate killed mid-run leaves its servers and suite processes alive; find
  them before starting the next gate, or they collide on output directories.
- Read a file with the tool before overwriting it with the tool; a file
  edited through the shell is "modified since read".
