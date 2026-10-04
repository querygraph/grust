# Hardened WCC outcome follow-up audit

Recorded: 2026-09-30T19:13:44.353793+00:00.

**PASS within the requested consumer-protocol scope** at Sail
`c8fe857848f3ba1698ee0f9d1daf000790d691d4`, tree
`70c92d35bc3dfc6f023dadf6655084e5208ffbea`. No blocker remains from this bounded
independent audit. Source hashes and HEAD were checked before and after.
This follows the completed refutations of `f63f992`; it does not overwrite them.

[Final matched-fixture receipt](audit-matched-receipt.json),
[executable controls](audit.py), [source identities](source-receipt.json).
The controls verify:

- A valid legacy passed receipt with exit 0 becomes partial in the new
  classifier and remains partial when its newly generated summary is audited.
- Explicit partial receipts require exit 1; old passed receipts require exit 0.
  Missing and unexpected exits retain mismatch outcomes.
- Five missing/malformed component-count markers and ten malformed arguments/
  correctness objects produce invalid receipts and summary integrity errors.
- Planned reference/certificate mode mismatches are rejected in both directions.
- Explicit partial receipts receive symmetric binary, native-file and dataset
  identity audits, and cannot contribute to exact-pass statistics.
- Existing mismatch/error/timeout/nonconverged outcomes and OOM/outer-timeout
  precedence remain distinct.
- Resume retains missing/malformed receipt and exit-status failures without
  rewriting the original summary or receipt. The valid control's complete
  receipt identity is first checked against its planned command/configuration.

Only local Python consumer functions ran. The resume control stubs preflight
and replaces container execution with an immediate assertion failure. There
was no Sail server, graph workload, Docker call or remote operation. The owner
separately runs the full Python and local SQL integration gates; this audit
cannot supply a Linux or distributed qualification.

The initial independent run also passed its outcome checks but reused a
resume receipt whose engine/mode/output metadata came from another synthetic
cell. Its receipt, script and local files are retained as attempt 01. The final
run uses matching engine/mode/output/admission metadata and asserts the complete
summary identity check before varying the resume evidence. Both attempts are
consumer controls, not observed benchmark measurements.

The separate certificate identity helper was read here. Its author reports
42 focused tests using real tiny traversal/imported writers and a synthetic
Graph500 producer-shaped manifest; this audit did not rerun those tests or
claim a generator invocation. Live input rehash remains the producer's duty.

Other malformed receipt fields and arbitrary unrelated matrix corruption are
outside this bounded follow-up. No implementation or default was edited by the
independent reviewer.
