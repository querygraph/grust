# Handoff, 2026-09-25

Written at the end of a long session so the next one can pick up without
re-deriving anything. Read this, then `AGENTS.md`, then whichever of the
documents below the work actually touches. Everything here was true when
written; check the repositories rather than trusting a line that matters.

## Where the work stands

**Grust 0.23.0 "Langoustine" is released.** Twenty crates on crates.io, verified
from outside the workspace; tag `v0.23.0` at `6504c0c`; the book is in the
FirstPair library as `0.23.0-6df869e2`; the release post's TextPack is in
`~/icloud/blogs` awaiting the operator's Ghost import. `main` carries the
release plus documentation added afterwards.

**Nutmeg 0.1.0 is released** as a tagged GitHub release (not crates.io: it
compiles Sail's crates into itself and Sail does not publish). Tag `v0.1.0` at
`58a120e`, release at `querygraph/nutmeg/releases/tag/v0.1.0`. `main` is
`f267b03`, carrying the release post and its cover. Grust dependencies are
crates.io `0.23.0`; Sail dependencies are pinned to git rev
`f1cf1729b1d083f2b97f1ce6e68a0d92c5ccee8f`. A clean clone builds with no sibling
checkouts — that was proved, not assumed.

**The kernel benchmark is published.** `https://adversari.al/graph/kernels` is
live (deployed from `~/src/adversarial-site` `master` `cb85d7c`), restructured so
the outcome precedes the apparatus. The post is on
`adversarial-graph-algorithms` branch `work/simple-rust-algo-bench-b9`
(`70d231b` in the `~/src/aga-b7` worktree), stamped `0.1.0-e6486d` and delivered
to `~/icloud/blogs`. **Two TextPacks await the operator's Ghost import**:
`simple-rust-algo-bench (0.1.0-e6486d)` and `nutmeg-0.1.0 (0.1.0-06d8b0)`, plus
`grust-langoustine (0.23.0-6df869)`.

**The PageRank loop is where measurement left it.** Campaign B9 on quegee timed
the whole kernel stack: of sixteen like-for-like per-sweep cells, twelve are at
or below the `neo4j-labs/graph` participant's cost, one is inside its margin, and
three are above it — `uniform-65536` by 14.7%, `hub-65536` by 10.8%,
`uniform-16384` by 0.4%, all at one thread on protocol-size fixtures, with no
cause established. Work accounting is now within noise of no accounting on the
pull kernel where it used to cost measurably; the push kernel's meter went the
other way, also unexplained. The loop's standing instruction — iterate until the
per-sweep cost is at or below the reference on every cell — is unfinished.

## What is in flight

| Item | State | Next step |
| --- | --- | --- |
| Sail extension proposal, fifth revision | `~/src/grust` branch `work/proposal-v5`, `6b7b7ff` | The operator reads it; nothing is posted to lakehq/sail#2001 without him |
| CSV nanosecond fix for Sail | `querygraph/sail` branch `csv-nanos-followup`, `d60b73d9` | Wait for lakehq/sail#2522 to merge, rebase onto merged main, then `OPEN_PR.sh` |
| eigentimes local publishing | Running on morrobay; `~/src/eigentimes` branch `work/local-publishing`, unpushed | Operator must fill `~/.eigen-post.env` (mode 600) before social posting resumes |
| Nutmeg post | Merged to `main`, pack delivered | Operator's Ghost import |

## The machines

- **This Mac** — the coordinator. Arm64.
- **morrobay** — Intel Xeon W-2191B, 18 cores, 128 GB, macOS, x86-64. Reached as
  `ssh morrobay`. Runs the eigentimes nightly (launchd `com.eigen.nightly`,
  hourly, keyed on the UTC hour) and is the Linux gate host via colima:
  `scripts/gate-linux-container.sh` runs `ci-local.sh` on x86-64 Linux there.
  Its `GATE_DIR` must be under `$HOME` (colima shares only that), the image must
  be `rust:1-trixie` plus clippy, rustfmt, protoc and the workflow's package set
  — `rust:1-bookworm` fails on GCC 12 lacking C++20 `<format>`.
- **quegee, grust, eigen, lakecat** — the four AWS hosts, **stopped**, to be
  terminated. Everything unique was taken off them; see
  `LAKESAIL-AWS-QUERYGRAPH.md` for the full record, and `~/handoff-2026-09-25/`
  for the rescued files (395 MB: host bundles, all four hosts' agent memories and
  transcripts, B8's unbundled evidence, gate logs, strain-run provenance).
  Absolute timings came from quegee alone; with it stopped, **no publishable
  timing can be produced** until a dedicated host exists again.

## Standing rules that cost something to learn

- **`AGENTS.md` binds every benchmark sentence**: no contest framing anywhere,
  every outcome kept distinct, a faster or slower number reported with its
  boundary. The operator asked for a post about "how we beat neo4j"; what the
  evidence supports is narrower and is what was published.
- **Nothing reaches lakehq/sail without the operator seeing the full draft.** He
  is on the Sail team; Heran Lin is the lead maintainer and his boss.
- **Maintainers will not push to an external contributor's branch**, to preserve
  their credit. Follow-ups are separate PRs against `main`.
- **Publishing routes are three and do not mix**: adversari.al pages are rendered
  from hash-verified evidence bundles by a script that fails the build on a
  hand-typed number; blog posts become TextPacks through FirstPair and land in
  `~/icloud/blogs` for the operator's Ghost import; books go through
  `npm run library:publish`. **FirstPair must be left committed and pushed after
  every publication** — its preflight refuses the next one otherwise, and that
  rule is now in its `AGENTS.md`.
- **`adversarial-site` does not deploy from git.** Pushing publishes nothing;
  `vercel deploy --prod` from the repository does.
- **Ghost renders Markdown escapes literally.** Write `A*` as a code span.
- A blobless partial clone cannot serve its own history; to move commits out of
  one, use `git format-patch`, fetch the base from upstream, and `git am`.

## Documents worth reading before touching their subject

- `AGENTS.md` — the authoritative rules, including the Working Discipline
  section, where each rule names the failure that produced it.
- `PUBLISH.md`, `RELEASES.md`, `CHANGELOG.md` — release operations.
- `GRUST-SAIL.md` — every Sail change Grust needs or has proposed, and §7 on why
  cluster mode is unsupported.
- `SAIL-2522-CSV-TIMESTAMPS.md` — the CSV timestamp finding.
- `LAKESAIL-AWS-QUERYGRAPH.md` — what the retired hosts held and where it went.
- `docs/proposals/sail-extension-api.md` (on `work/proposal-v5`) — the fifth
  revision, built on the Spark Connect protocol.
- `docs/reviews/briefing-2026-09-22.md` — the briefing written for an external
  reviewer; the fastest way to understand the whole project.
- `~/handoff-2026-09-25/spark-connect-extensions.md` and
  `sail-connect-internals.md` — the research the fifth revision rests on, each
  claim with a file and line at a pinned revision.

## Open decisions for the operator

1. Whether the fifth revision goes to lakehq/sail#2001 as it stands, is trimmed
   (a prioritised cut list is in the agent's report), or gains a one-page summary
   so the thesis is not buried.
2. Whether to terminate the four AWS instances or keep them stopped.
3. The Ghost imports of three TextPacks.
4. `~/.eigen-post.env` on morrobay, without which eigentimes builds but does not
   post.
