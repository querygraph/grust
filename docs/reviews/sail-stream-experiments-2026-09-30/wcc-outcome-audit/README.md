# Independent WCC outcome consumer audit

Recorded: 2026-09-30T18:55:27.144963+00:00.

Scope: exact committed Sail `f63f992766fe17ee2163a1187373449e79192be6`.
The owner was editing its checkout concurrently, so the final reproductions use
[byte-pinned committed source copies](source-receipt.json). They are pure Python
consumer checks, not a Sail execution or server test. No remote operation or
implementation edit was performed. The owner is correcting the findings; this
receipt does not review or gate the replacement candidate.

## Additional findings

1. **P2: malformed certificate metadata can remain an exact pass.**
   `validation_outcome.py:13–16` downgrades only when
   `component_count_verified is False`. With WCC certificate arguments, certificate
   policy and explicit `partial_wcc_partition` scope, absent/null/0/string-false
   markers all return `passed`; even boolean True can contradict the partial
   scope without rejection. `run_matrix.classify` also returns `passed` for an
   exit-0 receipt. No current WCC certificate producer verifies connectivity.
   Derive the scope from the actual certificate protocol and reject contradictory
   or malformed metadata; an unsupported exact-certificate claim must not be
   manufactured from one flag. Broad malformed-receipt acceptance predates this
   patch; the new downgrade does not yet close it.

2. **P2: receipt validation mode is not checked against the planned command.**
   `summarize.py:113–131` omits `ranking_validation`. Several new tests in
   `test_wcc_outcome_consumers.py:13–52` obtain reference-command records and
   change only the receipt to certificate mode. This mismatch is accepted with
   no integrity error. Combining it with finding 1 makes all three synthetic
   cells exact passes, with three metric samples. The missing argument audit
   predates the patch, but the new tests rely on a configuration that could not
   produce those receipts. Use matching certificate configurations and separate
   exact-reference controls; audit the effective final CLI validation flags.

3. **P2: resume can retain a legacy exact pass without its receipt.**
   `run_matrix.py:488–493` reclassifies a legacy summary only if its receipt file
   exists. A matching certificate-mode configuration, legacy passed summary and
   missing receipt produces exit 0 and `matrix-results.json` outcome `passed`,
   while the new cell expectation is `partially_verified`. The independent
   summary auditor later rejects a missing receipt, but the matrix result itself
   remains wrong. Preserve the original summary and classify its in-memory
   resumed result as missing/invalid evidence. Trusting a summary without a
   receipt predates this patch; the new reclassification path leaves that route
   uncovered.

The parent separately identified the explicit-partial integrity-audit bypass
and exit-status mismatch; this audit does not duplicate those findings.

## Evidence

[Executable reproduction](reproduce.py) and [observed outcomes](counterexamples.json)
retain all three counterexamples. The fixture factory is extracted unchanged
from the committed test source to avoid an unavailable optional pytest import.
For the resume check only, preflight is stubbed and `run_container` is replaced
with a function that raises if called. The resulting local artifacts are retained
under `resume-missing-receipt/`. This is a unit-level protocol reproduction.
Two earlier preparation attempts failed before running a counterexample
(optional pytest absent; active source checkout mid-write); both are disclosed
in the source receipt and are not counted as product failures.

Expected historical compatibility: actual `graph_cell` receipts serialize
`vars(args)`, so `ranking_validation` includes its parser default. Historical
WCC certificate correctness has policy `certificate` and boolean false count
verification, but no scope field. Exact reference correctness need not contain
an explicit policy field. Do not weaken those real producer boundaries solely
to accommodate incomplete synthetic fixtures.
