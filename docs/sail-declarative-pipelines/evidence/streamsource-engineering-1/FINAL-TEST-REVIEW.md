# Final test evidence review

Verdict: no must-fix findings from the Test Case Generation review of this
documentation candidate. This is not a production implementation or target
qualification verdict.

Baseline: `f23da50ccdf4ac1258fa1c6803aeb54df042a03e`.

Initial cumulative patch reviewed:
`2a619d67564fa3090733def44d5cf97c5ac4437ca0d8accc6abcf258a250a05c`.
The retained `candidate-0-documents.patch` and `candidate-0-files.json` identify
that candidate.

Final cumulative patch reviewed:
`8dd7bac1e54a6b463f74f91c37b9cb604e15872b4c30772b5fba6089ee7e57b9`.
The final `candidate-files.json` identifies all twenty-two documents. The full
cumulative diff was reviewed within this specialty, followed by the three-file
addendum described below.

## Evidence checks

- All thirteen numeric prototype-result table rows are byte-for-byte unchanged
  from the baseline. The file-sink crash simulation, separate Delta cases,
  broker cases and fixed-event-order state restoration retain their boundaries.
  They are not presented as new integrated qualification.
- The marker receipt and raw output contain exactly twenty-nine expected error
  cases: five empty-schema decode failures, sixteen Decimal marker encoding
  failures and eight strict-expression failures. Schema metadata loss is one
  separate assertion. The successful harness exit is described as reproduction
  of defects, with success controls, rather than a correctness pass for Sail.
- The expression probe's scope remains precise: actual unchanged event modules
  and DataFusion expression/filter calls, without Sail SQL planning or distributed
  execution. It does not establish mixed-batch safety, arbitrary-function behavior
  or comprehensive Arrow type coverage. Both setup failures remain retained.
- The semantic model's twelve distinct valid-input order/partition cases and
  twenty-four conflict cases are model evidence. Its unbounded fingerprint map
  does not establish the proposed bounded current-version implementation. The
  chosen Spark tie result is permitted behavior, not a guaranteed winner.
- The configuration research retains nine parser cases: six accepted and three
  rejected. Its Python body and stdout match their recorded SHA256 hashes.
  Claims distinguish direct YAML/project-parser execution from inspected option
  and settings-merge paths. No Spark session, Sail job, Dhall compiler or CUE
  integration is inferred from those cases.
- Fencing tests are required against actual acceptance and publication paths.
  Existing reference test bodies and source inferences are not promoted into
  managed-Delta, Iceberg, external-writer, worker-transport or multi-host authority
  qualification. Accepted-before-takeover publication is distinguished from
  obsolete ownership authorizing a new effect.

The proposed failure checks discriminate the relevant alternatives: marker
expression isolation, preserved prepared identities, replay versus saved output,
ordinary table-version checks versus owner enforcement, original-row validation
versus winner-only validation, and strict frontend equivalence versus permissive
parsing. Resource and concurrency checks remain proposed where not executed.

## Final addendum

Only CHANGE-CAPTURE-ON-STREAMSOURCE.md, CHANGE-CAPTURE-SEMANTICS.md and
REDESIGN-PLAN.md changed between the recorded candidates. Their clarification
requires checking original event versions against a pinned durable-state snapshot
before reduction can discard evidence.

The example is a useful discriminating regression: durable `8:A`, followed by
incoming `8:B` and `9:C`, must expose the version-8 conflict even though version 9
wins reduction. Binding the snapshot to the commit precondition, then reconciling
or revalidating the same immutable normalized input if state changes, closes the
winner-only-check ambiguity. It does not claim exhaustive superseded-history
verification or a completed implementation. No new runtime test is claimed.

## Validation and limits

Read the exact saved request and reread AGENTS.md, LAKESAIL.md, SHEHAB.md,
CLARITY.md and WRITING-RULES.md. The latest engineering directive takes precedence
over compatibility defaults. Governance compliance was confirmed for this review.

Ran `python3 docs/sail-declarative-pipelines/evidence/streamsource-engineering-1/validate_review.py`
without `--write` or `--staged`. It passed against the final patch hash, including
candidate identity, reverse application, source pins, retained marker/source
integrity and unchanged semantic-model output. Independent read-only checks
verified the historical count rows, marker case totals and parser artifact hashes.

No Rust, parser, Spark, broker, storage or fencing suites were rerun during this
final document review. No performance measurements or optional-frontend compilation
were performed. No main document, source worktree, test artifact or prior receipt
was changed. Only this review record was added.
