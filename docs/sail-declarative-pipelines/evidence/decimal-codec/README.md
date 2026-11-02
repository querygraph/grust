# Decimal cast worker serialization

Sail `b48162de9c9ee9cf4f386fa7eb3ebf683601a64d`, parent8a7bf8ca4.
Three source paths add ExtendedScalarUdf tag43, encode/decode support and focused
tests. All existing tags1..42 are preserved. SparkStringToDecimalUdf carries
uint32 precision, int32 scale, bool fail_on_error and bool allow_negative_scale.
Decode validates the function name, checks u32→u8 and i32→i8 narrowing, then
runs the callable component's Decimal128 constructor validation.

Policies are reconstructed from the payload, with no worker session lookup.
Proto3 omits false bools; round trips cover both absent/false bits as well as
true. fail_on_error=false represents legacy/TRY behavior, not Spark's default
ANSI setting. Negative scales retain their sign. Valid negative target-scale
support in this pure component does not bypass the later resolver/config guard.

All243 execution libraries, formatting and strict Clippy pass. Four tests cover:

- All four captured fields, signatures and actual scalar/array results for
  targets(5,2)/(38,10)/(5,-2), both policies and three Arrow string layouts.
- Three typed error kinds with complete class/condition/state/parameters after
  decoding, including policy-dependent1e39 and NULL in null-on-error mode.
- Full physical higher-order expression round trips: captured text columns,
  typed lambda parameter, skipped bad cast under rightNULL, NULL left/right0,
  successful values, empty batches and a decoded cast that actually raises on
  non-NULL right. The operation returns the left value to isolate casting;
  this is not a SQL division/coercion parity assertion.
- Invalid function names, malformed/truncated bytes, constructor bounds and
  checked integer ranges. Values257/258/-256 would wrap into valid native
  precision/scale values, making the narrowing checks observable.

Five production-only controls remove each policy bit, erase scale's sign and
replace each checked narrowing with a wrapping conversion. Each fails0/1 with
the same test blob. All control patches, receipts and logs remain. The initial
passing243-test checkpoint is also retained; additional bad-wire/error cases
were added before the final gate. There were no failed candidate gates.

Fable independently [accepts this unit](peer-review.md), with no blocking
findings. verify.py checks its exact commit extract, source/test hashes, counts,
controls, tag preservation and unchanged scalar/resolver/config/folding code.

This qualifies direct worker-codec APIs and decoded physical expressions, not a
live remote worker RPC or new public SQL path. The CLI remains qualified at63f5;
no fresh public300/67 run or original Scala SDP acceptance is claimed. Scalar
component qualification remains in the [parent packet](../decimal-scalar/README.md).

Next is the user-notified design checkpoint for generic config capture and
source/conditional-aware folding before resolver activation. New NUMERIC_* raw
error vocabulary/admission, ordered SQL arithmetic activation, streaming/CDC and
full Spark SDP acceptance remain required. No new execution mode/default,
provider/ownership authority, push or release was introduced.

Archived control and advance scripts use original absolute worktrees and /tmp
paths. Inspect them before reuse. Gate verification does not advance a branch;
the exact receipts and unchanged source must pass before conditional advancement.
