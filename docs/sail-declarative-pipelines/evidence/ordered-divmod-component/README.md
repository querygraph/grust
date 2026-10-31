# Ordered DivMod component evidence

Sail candidate c1befda7a8f29937c9bbc32d3f516379732e9eae, parent
b857dabb74da0484b781c096f9a9cd6a78daaa5c. This is a pure internal component
and a shared zero-mask extraction, with six native regressions. Arithmetic
lowering, SQL function registration, worker protobuf and codecs are unchanged.
There is no fresh public runtime or original Scala SDP-suite verdict on this unit.
The [last public arithmetic qualification](../numeric-divisor-guard/README.md)
remains pinned to b857; its six runtime and two DIV-domain gaps remain required.

## Behavior qualified here

SparkDivModLazy takes three lambdas: right thunk, left thunk, native operation
on their already evaluated values. It orders rows and operands in one pass,
skips left for null/legacy-zero right, skips operation for null left, and leaves
ANSI error checking/native arithmetic to the operation body after both operands
are known. It does not replay failed evaluations. It accepts numeric/Null right
fields; metadata and result nullability are preserved. It is not activated.

The detached gate passes402 sail-function libraries, formatting and strict
all-target/all-feature Clippy. Tests cover call traces and null/zero skips,
first-row errors, signed zeros, NaN/infinity, captured columns/operation parameters
used without a prefix, empty batches, admission, metadata, optimizer handling of
a skipped failing operand, and separate volatile evaluation of identical calls.
The CSE fixture returns8 and4 with exactly two volatile divisor invocations,
zero during frame construction. It is evidence for this fixture, not a proof of
all nested lambda/window/aggregate transformations.

The unchanged right-first regression fails0/1 when only production evaluation
order is changed to left-first; its test blob is identical. Candidate and control
pins, log hashes and the single mutated source path are verified.

## Why selected-batch evaluation alone is insufficient

A fresh Spark4.2.1 source617618396087429b5627a86ce933bb0f5d6645cb oracle runs
eight queries with effective ANSI/codegen settings recorded: whole-stage codegen
on/off,1/4 Range partitions, ascending/reversed two-row inputs. A first-row left
raise_error followed by a later-row right invalid cast reports
USER_RAISED_EXCEPTION. Reversed inputs report CAST_INVALID_INPUT. Single-partition
observations demonstrate that public error metadata distinguishes the order;
these finite multi-partition observations do not establish scheduling guarantees.
Fable independently corroborated the result and withdrew its earlier
same-partition non-observability claim (review710d0b73).

The unadvanced test-only selected-batch prototype changes the same callback
fixture's surfaced error from left-row0 to right-row1. It confirms the design
hazard; no selected-batch mode is shipped or accepted as final parity.

The same prototype checks equal successful outputs and records one unoptimized
shared-host diagnostic (1024 rows,20 evaluations after warmup): row-major/native
ratio about80.3, selected-batch/native about2.94. These are diagnostic ratios,
not optimized production estimates or performance promises. They establish that
a blanket per-row activation needs a better cost argument. Optimized representative
measurements, common-subexpression effects and safe fast-path classification are
still required before activation. No absolute timing is published.

## Failed attempts retained

- attempt-01: a test import and LambdaVariable String-constructor compile error.
- attempt-02:397 passed/4 failed; exact all-lambda signature lacked explicit
  empty value-argument coercion. Fixed component admission, not assertions.
- attempt-03:397 passed/4 failed; test operation parameter names collided with
  captured input fields and a typed variable's nullability mismatched its input.
  Fixtures now use distinct names and the actual field nullability. Activation
  must generate names fresh against input columns and enclosing lambda variables.
- checkpoint-01/02: passing401-test candidates before the final CSE regression;
  neither advanced the source branch. First control is kept with its own test pin.
- batch-probe-attempt-01: the callback fixture examined only its first batched
  row, so it did not induce the intended later-row failure. Corrected callback
  visits every supplied row; the expected error-order assertion is unchanged.
  This is a fixture failure, not an engine or component verdict.

## Remaining design and verification

[Operand evaluation design](../../OPERAND-EVALUATION-DESIGN.md) remains active.
Next reviewable units are codec support and lowering, after constant/foldability,
CSE, fresh variable names, nested lambdas and extracted operands are qualified.
A deterministic selected-batch fast path followed by ordered replay on suitable
data errors is under investigation (Fable e30236fe). It requires a justified
replay-safe classifier and error allow-list. Volatile/stateful evaluation must
never be replayed; I/O, resource, cancellation and internal failures must remain
unchanged. A blanket UDF Execution error category is not automatically evidence
of a pure reproducible data error. No such mode or flag is added here.

Generic CASE planning evaluation, query-wide ordering across projection columns,
non-numeric domains, decimal precision, and the full original SDP suites remain
unqualified. The coverage inventory stays462 sites/97 reviewed/61 partial/401
unmapped. Passing a component gate does not close the overall goal.

Run `python verify.py` in this directory using Python3.12. It checks the complete
manifest, source/test pins, exact402 gate/control results, unadvanced prototype,
Spark oracle, retained failures and unchanged lowering/codec blobs. Existing Sail
Git objects are required. Historical scripts retain original absolute paths and
fresh-output assumptions; do not rerun them in place or reuse an unrelated CLI.
