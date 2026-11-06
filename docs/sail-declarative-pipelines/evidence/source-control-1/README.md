# Source-control qualification and design evidence

This directory preserves the source-control plans recorded before their dependent
implementation, the initial specialist analyses and the full request with subsequent
clarifications. It is optional implementation evidence, outside the primary design
reading sequence.

The recorded starting source is `b6d73d6a644dc04b1e6749e171100808c874d788`.
`plan-before-code.json` identifies the original plan. The later lifecycle receipt
distinguishes the encoder extraction already begun under that plan from core control
work that had not begun. These are historical records, not claims that no code has
subsequently been written.

## Qualified local implementation

Commit `bd1847d8e1afa7b8045799534b0e321f16c2a7f0`, tree
`60abc2c88c3e5a2cce786f549eb2865c04223661`, passed the immutable qualification
gate. Its parent is the starting source above; cumulative review used upstream
`b52144955b629314a000b1fe49eeea97fa3d0c5c`. Source remains local and unpushed.
The [qualification record](qualification.json) pins the receipts, artifacts and seven
final specialist reports. Initial reports in this directory remain design evidence;
they are not the final reports identified by that record.

The local job runner owns controls for its executing sources. Native rate sources
service idle requests, acknowledge markers in output order and revoke pending work
on cancellation, output termination or owner shutdown. Compiler and codec checks cover
source identity and plan reconstruction. A metadata-only binding preserves child
tracing without adding another traced operator; projection transport carries one
generic child rather than recursively duplicating it.

Qualification passed formatting, strict Clippy and Rustdoc, 2,145 workspace Rust tests,
and 51 selected public rate, streaming and projection tests against a freshly built
server reporting Spark 4.2.1. One unchanged upstream Rust test remains skipped.
Optimized concurrency stress passed 400 test invocations with ten owned load processes.
Deliberate omissions exercise lock-safe notification, revocation, child tracing and
encoding-before-acknowledgement; these are candidate controls, not upstream comparisons.

The shared-host performance diagnostic covers 168 samples. Ordinary local-runner
ready-poll median ratios against direct execution range from 1.0006 to 1.0055, with
every paired range spanning one. Controlled local-runner costs remain visible:
polling medians range from 1.1484 to 1.7356, and startup from 2.8358 to 2.9529. These are
bounded elapsed-time diagnostics with metric emitters disabled, not production
throughput or isolated CPU measurements. Mixed-marker fragmentation and broader
startup costs remain open.

Replay, distributed control, transport alignment, fencing and durable pipeline
recovery remain unbuilt. Seven specialist reviews and local qualification do not
establish maintainer agreement or production readiness.

The live rate ordinal describes one execution and is not a replay position. The
delivery plan separately proposes a Delta log source for the first real append path.
Its [descriptor, manifest and reader increments](../../DELTA-REPLAY-SOURCE.md),
authority durability and enforcement still require implementation and qualification.
