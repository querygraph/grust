# Defer arithmetic errors until evaluation

Producta49082801e79a6a9cea545186fecb7171d54a4b5 removes eager literal-zero
failure/typeless NULL returns from /, DIV and %. All contexts now lower operands
without evaluating; the constant-context arithmetic-deferral exception and literal
zero helper are removed. Type-only parents and inactive branches can discard the
operation while preserving its type.

The existing numeric divisor guard now uses two internal immutable nullary error
kinds, with Spark's DIVIDE_BY_ZERO/REMAINDER_BY_ZERO,22012, ANSI config parameter,
native SparkArithmeticException and measured six-class hierarchy. The worker
codec uses the existing StandardUdf envelope and two names, with no new protobuf
fields or dependencies; a decoded function is invoked in the native test. Generic
user raise_error is unchanged. Full query-origin/message-summary parity remains
required and is not established here.

A first otherwise-green candidate exposed a signed-zero regression in two
existing public tests. The corrected guard treats float +0/-0 equally: ANSI uses
abs after widening only the predicate; non-ANSI uses nested typed NULLIF calls,
so the operand occurs once in that expression tree. The original divisor/result
type remains intact. Native tests cover signed literals, float/double, all three
operations, ANSI modes, late failures and typed NULL results. The public negative-
zero tests are unchanged and now pass.

Detached fmt, strict Clippy and909 Rust tests pass (229execution+394function+
106plan+180Connect). Restoring ordinary eager evaluation makes two unchanged
arithmetic tests fail while the signed-zero test passes (1 pass/2 fail); removing codec
decode support fails its unchanged test0/1. A fresh CLI passes300 selected public
cases+67 upstream Python executions+4 existing parameter tests.

The40-case Spark4.2.1 oracle improves17→40 outcome/row/condition matches, with
matching public metadata and raw native reason/hierarchy/metadata fields on all
40 comparisons. All33 successful-query schemas match. Earlier48 catalog-phase
outcomes stay33; arithmetic14 improves8→10 (metadata5→7);20 provenance observations
are unchanged. No earlier positive comparison regresses. Transient IDs, full JVM
stacks and query origins are excluded from the raw field comparison. No data writes.

This does not close arithmetic runtime semantics. The separate12-case oracle and
runtime-gap-check.py retain six required ANSI failures: NULL dividend over input
for /,DIV,%, a volatile NULL dividend, a window NULL dividend, and pmod zero.
The check exits1 until these are fixed. Its six legacy-mode cases pass, including
all schemas after this change. A proposed duplicated-dividend null check was
rejected because it changes volatile evaluation cardinality; operand materialization
or a whole-operation evaluation design is the next user-notified checkpoint.
A separate deterministic volatile-divisor Rust probe is appended only on an
unadvanced test commit; it fails0/1, measuring six invocations where one is required
and an arithmetic error where the first divisor value is nonzero. Its initial
error-propagation fixture and corrected counter-first fixture are both retained.
This confirms an additional evaluation-cardinality gap; stage-specific diagnosis
is required. The existing ANSI CASE also references its divisor twice. A proposed
unary divisor guard can preserve the native arithmetic kernel and avoid that
syntactic duplication, while NULL-dividend/right-first semantics still need the
larger design. No window deviation is accepted as the final goal. Full original Scala SDP-suite
acceptance, bare catalog phase rules and intrinsic annotations remain open.

attempt-01 retains the initial test import failure; attempt-02 retains the wrong
empty-codec-payload fixture, corrected to assert StandardUdf. attempt-03 retains
the908-test passing candidate, controls and real298/300 public failure. None was
advanced. Source/JAR hashes, original row-only observations, schema-bearing replay,
server teardown and all failed receipts remain visible. verify.py and SHA256.json
check immutable source identity, logs, unchanged test blobs, probes and the required
runtime failure check; orchestration snapshots preserve the executed helpers.

The additional two-row floating-DIV domain oracle rejects the inputs during Spark
analysis in both modes; Sail currently raises DIVIDE_BY_ZERO under ANSI and returns
NULL outside it. input-domain-check.py fails0/2 until that mismatch is fixed. The
native floating signed-zero fixture is corrected separately to use Spark-supported
/ and % operators; integer DIV remains covered. That correction changes tests only
and does not establish input-domain parity or change runtime behavior. The retained
collection-failure log records an initial evidence-copy path error, corrected by
moving the uncommitted artifacts from the product checkout into this Grust packet.
