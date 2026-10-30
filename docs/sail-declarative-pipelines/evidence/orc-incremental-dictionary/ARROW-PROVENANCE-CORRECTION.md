# Arrow dependency provenance correction

Recorded: 2026-10-30T01:07:55.872424+00:00.

The native dictionary gate and Sail vendor gate both used **Arrow 59.2.0**.
Two earlier source attributions were incorrect; they are retained unchanged so
this correction does not rewrite the evidence trail.

- The [original proposal](DICTIONARY-PROPOSAL.md) cited Arrow 58.4.0 sources.
  That version was not the dependency used by the dictionary gates.
- The [first follow-up audit](arrow-provenance/historical-first-audit.json)
  inspected the native implementation worktree's ignored, untracked Cargo.lock.
  Its Arrow 59.3.2 reader dependency and separate 58.4.1 development dependencies
  were incorrectly described as the actual native gate resolution. That lock is
  retained as [non-gated worktree evidence](arrow-provenance/non_gated_native_implementation_worktree.Cargo.lock).

The [corrected receipt](arrow-provenance/receipt.json) establishes the actual
identities:

| Input | Identity | Arrow version |
| --- | --- | --- |
| Native detached gate | `5937e8a8f1154aff333818dc365ffc6367c84d5f` | 59.2.0 |
| Retained dictionary package | VCS pin `5937e8a8f1154aff333818dc365ffc6367c84d5f` | 59.2.0 |
| Sail tracked lock at vendor commit | `43fe0dc841ec18b2a0e666f0bb05d01a95007852` | 59.2.0 |

The native gate's [lockfile](arrow-provenance/native_detached_gate.Cargo.lock)
and the Cargo.lock inside the retained [package](orc-rust-0.9.0.crate) are
byte-identical, SHA-256
`29dd0ca91217b64ca2d56f25db1993a889ceb20961233fa2c60009339a06338e`.
The [Sail lockfile](arrow-provenance/sail_detached_gate.Cargo.lock) matches the
tracked file at the named vendor commit, SHA-256
`92c572736928f7708fe3749254e08f6ebcf60eba5a7b6615cfb444d2f98cf572`.
The frozen receipt records the contemporaneous gate and implementation copies;
those local paths are provenance, not prerequisites for inspecting this archive.

Actual Arrow 59.2.0 source excerpts and full-file hashes in the corrected receipt
confirm the design's API claims. StringArray uses i32 byte offsets with a usize
entry count. OffsetBuffer requires nonempty, nonnegative, nondecreasing offsets
without an i32 entry-count ceiling. DictionaryArray validates non-null keys
against the dictionary length and accepts all-null keys. String validation checks
UTF-8 and offset boundaries. These source findings do not claim execution of a
huge dictionary or general allocation safety.

The [frozen correction manifest](arrow-provenance/MANIFEST.sha256) covers the
original correction files. The historical first audit was added beside them
without modifying that manifest; the packet's [provenance](provenance.json)
covers the exact combined fileset. Both the original proposal and first audit
retain their original SHA-256 identities.

This correction changes dependency attribution, not code or runtime results.
The existing 357 native tests (eight ignored), 236 no-default tests and 192 Sail
data-source tests remain the separately recorded gate evidence. No new build,
test, Spark process or service action was performed for this correction; the
parent owns the documentation gate. Public ORC and complete SDP acceptance are
unchanged.
