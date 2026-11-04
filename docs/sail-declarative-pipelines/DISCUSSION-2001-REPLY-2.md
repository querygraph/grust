# Draft: second reply in Sail discussion #2001 (to the Sedona maintainer's reply of 2026-11-04 01:54 UTC)

Status: draft, not posted. Facts checked on 2026-11-04 against
`apache/sedona-db` at `a4072db5` (`c/sedona-extension/Cargo.toml`: no
`datafusion-ffi` dependency; the table provider, execution plan and stream
exchange are its own C definitions over the Arrow C Data Interface) and
`apache/datafusion-comet#4459` (merged 2026-10-06: `comet-udf-sdk` depends on
`arrow` only; ABI version probe at load; panic containment at every
`extern "C"` entry; stale libraries refused by the version check).

---

You're right about sedona-db#1004, and I had it wrong: `sedona-extension` does not depend on `datafusion-ffi`. Its table provider, execution plan and stream exchange are your own C definitions over the Arrow C Data Interface. That changes what I should have said, and it makes the case for the Arrow-only route stronger than I made it: the whole Sedona surface, relations included, already crosses a boundary with no DataFusion type in it.

"Declared-and-refused" in one sentence: every native package states, in its manifest, the versions of the boundary it was built against; the host compares that to what its own `Cargo.lock` resolved and refuses to load a mismatch before anything binds, quoting the declaration. Nothing is probed at runtime and nothing is assumed compatible.

What we'd do with your two points:

1. **Adopt the Comet C scalar ABI as the scalar channel.** Since your functions import through it with no code changes, and since it carries no DataFusion type, the host would resolve scalar functions from that ABI first and keep the `datafusion-ffi` scalar wrapper only as a fallback while both exist. The loader gets one more declared field, the scalar ABI version, under the same refuse-before-bind rule. If the header moves to DataFusion or Arrow we follow it there; until then we implement against Comet's and say so, as Comet does.
2. **Look at your relation boundary before proposing ours.** For table providers and execution plans we had assumed `datafusion-ffi` was the only practical boundary. If `sedona-extension`'s C definitions are the shape you'd want other engines to consume, the bounded-relation dispatch in our contract (pass the children, get a plan back) could sit on them instead; the dispatch itself doesn't care which boundary carries the plan. We'd rather converge on one relation boundary than ship two.

The PRs will come in the order in the plan: the memory-lease C ABI, the session-owned loader, relation dispatch, then scalars; the scalar PR is where (1) lands, and we'll ask you to look at it. Thanks for the correction.
