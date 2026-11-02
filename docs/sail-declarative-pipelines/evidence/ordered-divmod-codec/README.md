# Staged lambda decoder and ordered DivMod wire evidence

Two reviewable Sail units:

| Commit | Scope | Exact gate |
| --- | --- | --- |
| 04f1e8cc79e73932829dd6130a67b280792ebfe9 | Generic staged decoder + five focused regressions; two files | 235 execution libraries, fmt, strict Clippy; three unchanged0/1 controls |
| 036dc6dde5e5111dbfcae94ec8a3afb9f323c84b | DivMod higher-order wire variant + four round-trip tests; five files | 239 execution libraries, fmt, strict Clippy; unchanged mode0/1 control |

Parent c1befda7a8f29937c9bbc32d3f516379732e9eae provides the
[ordered component](../ordered-divmod-component/README.md). These units add worker
representation and decoder support. Arithmetic lowering, constant validation,
SQL registration and the component's evaluation policy are unchanged. No public
SQL activation, fresh public-suite result or original Scala-suite acceptance is
claimed. The [b857 public qualification](../numeric-divisor-guard/README.md) and
its known runtime/domain failures retain their original source and binary pins.

## Generic decoder

The previous converter required lambda_parameters to return Complete on its
first call with unknown lambda output fields. The three-lambda evaluator needs
its two thunk output fields before it can type the operation parameters; the
initial round-trip gate exposed this with230 passed/3 failed, all new positives
reporting partial lambda parameters. General staged support belongs in Sail.

The decoder now infers known bodies' fields and calls lambda_parameters again.
Partial None means no new information: prior body/field information survives.
Partial vector lengths must match present lambdas. Complete can include unused
trailing parameter sets, preserving the existing physical constructor/decoder
contract for optional lambdas. The DataFusion logical resolver is stricter;
Fable a683b52d independently confirmed the deliberate distinction. The native
prefix fixture constructs HigherOrderFunctionExpr to prove the physical contract.

Resolution includes step0 through the signature's limit, matching DataFusion's
logical resolver. Limit0 still permits its initial call; nonconvergence errors.
Declared parameters beyond available fields and missing sets are rejected.
Output-field inference for another pass happens only on Partial, avoiding unused
extra inference on the existing Complete-in-one-pass path. The helper builds
nodes and requests fields; it does not directly invoke lambda bodies. Tests
verify decoding known failing scalar bodies without invoking them. This does
not prove all DataFusion field inference side-effect-free: the separate generic
CASE nullable/predicate issue remains required work.

Native fixtures cover retained prior fields, inclusive bounds, nonconvergence,
invalid Partial/Complete counts, valid optional Complete tails, and failing-body
metadata. Three production-only controls independently regress retention, make
the limit exclusive, or reject optional Complete tails. Each corresponding
unchanged test fails0/1 with identical test blobs and one changed source file.

## Wire variant

HigherOrderUdf appends tag13, SparkDivModLazyUdf with bool ansi_mode at field1.
No existing tag changes; no fast-path/replay flag is introduced. Operator/error
kind remains in the serialized native operation lambda and existing unary guard.
The existing converter represents bodies, captures, parameter names and indexed
LambdaVariable fields. Encoding downcasts the implementation; decoding rebuilds
its mode. Older workers cannot interpret the new oneof variant and reject it.

Four tests encode, decode and execute complete physical expressions:

- Both modes ×divide/remainder: null-left/zero-right suppression, nonzero values,
  null right, legacy zero nulls, and ANSI typed errors. Native class, condition,
  SQLSTATE22012 and quoted ANSI config parameter survive the round trip.
- An operation uses only the second bound parameter plus a captured offset,
  including a null-left row; capture/parameter projection stays correct.
- A failing left thunk is skipped on a real one-row input when right is NULL,
  or zero in legacy mode. Empty input would not prove this property.
- Missing third lambda and overdeclared operation parameters are rejected.

A mode-only production control decodes ANSI as legacy. The unchanged round-trip
execution test fails0/1. These integer native-kernel fixtures qualify wire
semantics, not complete Spark SQL coercion/result-type parity.

## Retained attempts and limits

Codec attempt01 is a test API compile failure (Arrow schema.fields(), not
field_ref()). Attempt02 is the230/3 partial-decoder failure. Two later integrated
234-test drafts and their controls passed but were not advanced: review then
identified partial-None retention and iteration-bound gaps outside those tests.
They are retained as codec checkpoints01/02. The generic unit has its own initial
unlinked test-import failure and a passing235 checkpoint before strengthening
the retained-field fixture to construct a real physical HOF. No failed evidence
is relabeled as a passing final source verdict.

Fable reviews d5b1d8cc,5a5ff593,a683b52d were consumed; the distinction between
logical and physical Complete counts was checked against both pinned DataFusion
layers. [Design](../../OPERAND-EVALUATION-DESIGN.md) stays active: scoped constant
validation, folded literals, fresh bound names, nested/extracted operands, CSE,
optimized performance and safe fast-path/error policy precede SQL lowering.
Volatile/stateful replay and resource/I/O/cancellation error replacement are not
authorized by these codec changes. Streaming/CDC admission/effects are unchanged.
Full SDP coverage remains462 sites/97 reviewed/61 partial/401 unmapped.

During this unit both repositories were fetched. Local Sail main was safely
fast-forwarded fromac4690078021cf2a5402dc5c7b38a886f1916c73 to
35d4d2f2d58890567c2a7b56372b12c9a4092c57 after checking no worktree held main
and verifying ancestry. SDP was not merged/rebased; no combined-main verdict is
claimed. Original Sail files were untouched. CLI remains the parent5a binary
from the earlier comparison; rebuild/qualify before any further runtime probe.

Run `python verify.py` with Python3.12. It validates all hashes, both commit-parent
chains, source patches, exact native counts, four causal controls and unchanged
lowering/constant/component blobs. Existing Sail Git objects are required.
Historical scripts preserve absolute paths/fresh-output assumptions; do not rerun
them in place. SHA256.json covers every other packet file.
