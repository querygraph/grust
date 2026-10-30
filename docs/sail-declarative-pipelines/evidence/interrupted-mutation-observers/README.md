# Interrupted mutation observers before drainage

Sail `070caa80b6695942318dbc24c90dae6e6bc0dfd7` classifies interrupted
completed-value mutation observers and multipart Interrupted results as nonretryable
commit uncertainty immediately. Original typed observer errors remain present;
the scope's drain report still retains the actual typed JoinError independently.
Generic resource observers and normally returned factory/provider errors keep their
existing semantics. Scope admission failure still returns before provider invocation.
No dependency, registry, session or checkpoint routing change.

Control `a87df0bf96056a357d8db94a76520e0ae0631592` changes only two test
files on the wrapper-fix base a2cee8f00. Actual PUT and multipart publications
precede supervisor-runtime loss. Their interrupted observers are examined BEFORE
scope drainage, and both controls fail `mutation observer was retryable before
drainage` (two failed test targets, exit101). The exact same two regression blobs
pass after the fix; no assertion is weakened. The scope reports were already
nonretryable from9d83baa8b, which did not protect a direct observer before drainage.

Exact detached gates pass: formatting, strict all-target/all-feature Clippy,
**112 common-datafusion** and **198 execution** library tests. Optimized CPU-load
runs pass all112 common tests and6 execution multipart tests, ten owned workers
per run, all joined and both binary hashes checked before branch advancement.
A new generic-versus-mutation result-observer test preserves typed RecvError, checks
both classifications before drain, and checks the typed panic JoinError after drain.
Existing provider errors/Arc sharing and cooperative cleanup regressions pass.

This corrects observer policy; it does not make a failed drain clean, confirm
remote durability or join opaque provider work. Consumers still must drain the
owner before cleanup/termination. Returned PUT-provider error visibility and
runtime-wrapper child ownership remain separate qualification work. Latest public
CLI gate is exactly a2cee8f00 (300 selected public/67 upstream), not this later
component tree; the later unit changes owned-adapter/helper error policy that
remains unwired to checkpoint writers and is covered by the actual adapter/resource tests above. Full original
Spark SDP acceptance remains open.

Historical scripts/receipts use absolute coordinator and /tmp paths. Inspect/adapt
output paths before reproducing; preserve prior results and control failure logs.
