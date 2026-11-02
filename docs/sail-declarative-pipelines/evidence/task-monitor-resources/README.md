# Distributed task-resource drainage

Recorded 2026-10-30T03:54:50.229850+00:00. Sail `e02e4f712f2b597d2aba0d0f49138da60b40e5d3` creates a fresh
resource-scoped TaskContext inside the admitted-attempt loop, before TaskPreparation.
The distributed monitor waits for registered supervisors before terminal reporting.
Success seals admission without canceling supervisors; failure/cancellation seals
and requests cancellation, then waits for completion/cleanup reports. StopTask
remains effective after stream EOF while drainage is pending.

Execution polling and canceled-stream destruction panics enter the same cleanup
path. The outer monitor supervisor retains the resource scope for its panic
fallback. Cleanup failures produce Failed rather than clean Canceled/Succeeded;
primary typed causes and secondary diagnostics survive. An uncertain commit from
execution or cleanup takes nonretryable precedence, following Sail's existing
CommonErrorCause policy, so a cleanup error cannot make a potentially committed
mutation automatically replayable.

All183 sail-execution and85 sail-common-datafusion library tests pass, together
with formatting and strict all-target/all-feature Clippy. Eight new tests use
explicit channel handshakes, with no elapsed-time ordering assertions. They cover
successful resource completion, cancel and closed cancellation channel, StopTask
after EOF, sibling drainage, structured errors, uncertain-commit precedence, failed
resources after successful execution, and stream poll/Drop panics. The exact three
source-file patch and raw logs are included. The test linker emitted an unwind-table
size warning, retained in rust.log; the test process exited successfully.

This is the distributed monitor portion of W2b, with no new dependency, wire-format
or public SDP coverage claim. It does not provide LocalJobRunner ownership,
CloseJob/driver cleanup acknowledgments, graceful actor shutdown, process-loss
reconciliation, native allocation accounting, or an ORC upload supervisor/sink.
Forced monitor cancellation still uses the preexisting no-report path. Registered
supervisors must fulfill the scope's completion/cleanup contract; this unit does
not prove arbitrary providers' cleanup or bound cancellation latency.

A read-only peer review found no blocking issue in the implementation or fixtures.
Its optional suggestion to add a generous test watchdog is retained in review.md;
channel handshakes establish test ordering independently of machine speed. These
library tests do not execute the full original Spark Scala SDP suites.
