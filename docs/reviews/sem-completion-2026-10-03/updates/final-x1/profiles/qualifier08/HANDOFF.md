# Qualifier08: native-bound stock4b FFI cap

Original qualifier07 and its cap0 failure are unchanged. Its strict execution/Python cause classifier correctly refuses the actual RPC `unknown` tag. Stock4b explicitly converts `DataFusionError::Ffi(x)` to `CommonErrorCause::Unknown(x)` at `crates/sail-common-datafusion/src/error.rs:165`; native BFS first records its typed `BfsCapFailure`, then returns an execution error through this boundary. The actual driver session-removal marker is present; the original failure occurs before that check.

Fresh `native_bound_ffi_cap_text` handles only the exact sole unknown value `Execution error: argentea: BFS did not converge within max_levels`, with the exact task-error FFI message. It requires the actual signed cap0 request, complete native topology proof, failure membership, cap payload, operation/snapshot/generation, owner incarnation, job/session/stage/partition, physical worker/PID and worker-log identity. Existing same-worker native → execution failure → task failure → FAILED byte ordering and separate same-driver report → observed session removal ordering remain. FFI execution and task-cause text are exact. No cross-host clock or first-fault claim is made.

Witnesses preserve `typed_cause` verbatim and record `rpc_tag=unknown`, `error_boundary=datafusion_ffi_native_cap`, `rpc_common_execution_tag_preserved=false`. Audit records that this separate decoder was used. The existing `passed_typed_bfs_cap_control` outcome denotes the independently proven native domain cap; it does not assert an execution RPC tag. The original `cause_text`/`classify` bodies are unchanged and continue refusing all generic unknown causes. Plain host allocation classification and all producer/source/wait/closure/output guards are unchanged. Owner09, observer06, native source, binaries and wheel need no change.

All four offline source gates passed; 28 synthetic controls include exact positive native-bound FFI cap and refusal without native evidence, foreign request/owner/task/PID/phase/payload, changed/extra/transport wire cause, altered execution/task chain and log order. No engine, actual-log qualification, SSH, native import, process observation, or lock mutation was run by author.

Root executes the fresh retained-evidence qualification:

```sh
/tmp/sem-output-oracle-venv/bin/python -B /Volumes/Apo/graph-tests/results/sem-completion-20261003/X1-control-qualifier08/qualify_control.py --config /Volumes/Apo/graph-tests/results/sem-completion-20261003/X1-control-qualifier08/cap0-requalification-config.json
```

The configuration binds the same actual closed producer, original wait, canonical closure, and fresh qualifier08 helper Pins, with fresh output `X1-native-bfs-cap0-01-qualified-control02`. No future positive receipt is invented. Original qualifier07 failure must remain linked in the report. Root still records its actual qualifier wait and current group closure.
