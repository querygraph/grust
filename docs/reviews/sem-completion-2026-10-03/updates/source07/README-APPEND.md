# X1 incremental diagnosis — dated partial appendix

Snapshot generated at `2026-10-04T18:48:44.725064+00:00`. This appendix retains the closed Tiny05 admission failure and native network diagnostics. Later native controls and scale24 evidence are separate; this packet contains no graph or final completion verdict.

## Tiny05 and partial process observations

Tiny05 reached both host inspections, a driver and a client. The original owner and retained self-SSH outer waiter exited 1. The client action records `RetriesExceeded()` and `stage inventory: RetriesExceeded()`, with empty worker/stage inventory and no levels, reached count, convergence or output. The independent closer observed current source/process absence and released exactly the owned locks while preserving the original failed flags and errors. It records `native_server_started=true`, `native_graph_algorithm_started=false` and `engine_qualified=false`. Closing the failed case did not create a canonical successful algorithm result. See the [original producer](evidence/tiny05-original-producer.json), [retained action](evidence/tiny05-retained-client-action.json), [negative closure](evidence/tiny05-independent-failure-closure.json), [direct owner wait1](evidence/tiny05-original-owner-wait1.json) and [outer wait1](evidence/tiny05-original-outer-selfssh-wait1.json).

The samplers observed real driver/client processes and were interrupted after this failed case closed. Both actual original sampler waits are 1, with groups absent and no forced cleanup. These are partial observations; no full memory peak, graph memory bound or numeric result is reported. The [partial observer closure](evidence/tiny05-partial-observers-closure.json) preserves both waits and its explicit scope.

## Native local-mode RPC observations

The root's diagnostic scripts start a native local-mode Spark server and query metadata. A zero from a diagnostic means its observation/closure procedure completed; it does not mean every requested RPC succeeded. [diagnostic-table.json](diagnostic-table.json) keeps the full original observations and wait fields.

| Diagnostic | Observed scope/outcome | Retained evidence |
|---|---|---|
| 01 | LAN `192.168.4.61:50161` deadline; loopback version RPC succeeds | [observation](evidence/diagnostic01-remote.stdout), [wait0](evidence/diagnostic01-ssh.wait.json) |
| 02 | Fresh locally copied/ad hoc signed native CLI comparison: same LAN deadline/loopback success; original artifact is separate | [source](evidence/diagnostic02-remote-source.py), [observation](evidence/diagnostic02-remote.stdout) |
| 03 | Alternative port49192: same LAN deadline/loopback success | [observation](evidence/diagnostic03-remote.stdout), [wait0](evidence/diagnostic03-ssh.wait.json) |
| 04 | Alternating loopback/LAN on50161: both loopback calls pass, both LAN calls hit deadline | [observation](evidence/diagnostic04-remote.stdout), [source](evidence/diagnostic04-remote-source.py) |
| 05 | Optional `python -m pysail` launch fails before server readiness, native/SSH1; no RPC result | [failed observation](evidence/diagnostic05-remote.stdout), [wait1](evidence/diagnostic05-ssh.wait.json), [independent failure closure](evidence/diagnostic05-failure-independent-closure.json) |
| 06 | Loopback health and version succeed, nonexistent method is UNIMPLEMENTED; all three LAN methods hit deadline | [observation](evidence/diagnostic06-remote.stdout) |
| 07 | Loopback HTTP/2 response observed; LAN raw HTTP/2 and same-host/cross-host RPCs time out | [observation](evidence/diagnostic07-remote.stdout), [retained stderr](evidence/diagnostic07-remote.stderr) |
| 08 | After scoped application firewall add/unblock, alternating loopback/LAN version RPCs all four pass with matching sessions | [observation](evidence/diagnostic08-remote.stdout), [wait0](evidence/diagnostic08-ssh.wait.json) |

Diagnostic05 remains a separate failed optional-module comparison. Its current independent closer reports the missing optional `pysail` module and native1, proves current group/source closure and releases its own marker; this is not a native engine success. The [initial closure stderr](evidence/diagnostic05-initial-closure.stderr) and [corrected current observation](evidence/diagnostic05-current-closure.stdout) are retained independently.

## Scoped firewall action and limits

The [public firewall producer](evidence/scoped-firewall-public-producer.json) records `socketfilterfw --add` and `--unblockapp` for the exact original fat native CLI path, both return0. Exact application listing changes false to true, the native original payload is unchanged, and the record reports global firewall enabled (State1). It contains no separate pre-action global-state field or original outer add-command waiter. The [actual public SCP wait0](evidence/scoped-firewall-public-copy-wait0.json) binds the local retained public record; it does not substitute for an unavailable original outer add wait.

The following diagnostic08 observes successful metadata RPCs on both endpoints. This is a current, scoped before/after observation. It does not certify distributed BFS, typed control semantics, a full physical oracle, scale24, or the initiating cause of historical X1/X2 failures. No broad firewall disable or modified native payload is claimed. The earlier source06 public-MinIO route observations remain distinct from these native Spark RPC probes.

## Preserved scope

Source05/source06 remain dated immutable packets. Their C2/C3 evidence and failure history are not rewritten here. F2a's additional rerun remains paused by the user. `all_Sem_work_complete`, historical initiating-cause proof, this appendix's scale24 oracle and full memory-peak qualification remain false. This report includes no private credentials or credential hashes. [external-payload-pins.json](external-payload-pins.json) retains payload identities as references; the author did not open binary, wheel, native library, Parquet or memory-sample payloads.

[claims.json](claims.json), [evidence-pins.json](evidence-pins.json) and [snapshot.json](snapshot.json) provide queryable exact aliases and scope. This preparation performs local explicit metadata copying only; root owns runtime, SSH, repository edits and publication.
