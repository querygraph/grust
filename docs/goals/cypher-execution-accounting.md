# Execution accounting required for automatic routing

Status: implementation design, 2026-09-14. Extends
[the automatic execution goal](cypher-datafusion-execution.md); no completed
policy mapping or performance improvement is claimed here.

## Observed boundaries

`PreparedReadRequest` owns the admitted AST, parameters, policy and absolute
deadline. The reference executor installs its execution context through a
thread-local stack in `read_budget.rs`. That stack cannot carry limits through
asynchronous DataFusion partitions. `ExecutionContext` already supplies owned,
shared work charges, cancellation and memory reservations.

The reference intermediate limit is cumulative for ordinary bounded reads;
`read_budget_live.rs` separately supports lexical live-memory accounting.
DataFusion's retained-memory pool is a third boundary. Equating those counters
would silently change the caller's contract.

`collect_result` checks rows before decoding and exact JSON output size before
appending, but `decode_result_batch` already owns strings and vectors by then.
Thus output-byte admission alone does not admit materialization. Likewise, a
stream wrapper charging emitted batches cannot account for join candidates
that were inspected and discarded inside an operator.

## Implementation sequence and invariants

1. Admit portable result materialization before copying. Derive checked charges
   from the actual sliced Arrow arrays, null positions, string lengths, column
   names and row/value containers. Share type validation with decoding so the
   admitted representation cannot diverge. Unsupported types fail before row
   allocation. Keep logical-copy accounting distinct from allocator capacity.
2. Carry one execution-owned context from prepared request through input
   capture, planning, operators and consumption. Reuse the original absolute
   deadline; never construct a fresh budget per partition or fallback route.
3. Instrument candidate work before provider scans, joins and expansions, and
   cumulative copies before creating intermediate values. Optimizer rewrites
   must preserve accounting coverage. Unknown operator coverage must prevent
   automatic admission, even if its outputs have a bounded row count.
4. Bind route eligibility to snapshot/provider authority, supported semantics
   and every requested policy field. Preserve semantic errors and execution
   failures; only a pre-execution unsupported outcome may choose another route.
5. Qualify route costs using end-to-end measurements including capture and
   output materialization. Existing prepared-query profiles cannot establish
   those thresholds.

Tests must cover inclusive limits and one-unit excess, sliced UTF-8 buffers,
null versus empty strings, overflow before allocation, shared charges across
partitions, cancellation during pending input, errors without replay, and
optimizer plans whose rejected candidates exceed emitted rows. Independent
small-graph oracles remain required. A result-decoder test alone does not prove
full execution-budget coverage.
