# Logging02 closed worker-loss audit

Recorded 2026-09-30T22:07:04.092713+00:00. Local inspection only; no workload, resource or remote process changed. The original collected cell and closure records remain unchanged, checked by [input hashes](input-manifest.json).

**This replay has direct cgroup OOM evidence.** In the same captured VM boot, the kernel names the exact logging02 cgroup and kills both mapped Sail worker PIDs. The original sampler then omits both workers. The driver subsequently records a Flight body read failure from worker 2's advertised endpoint with the original broken-pipe cause. This explains the observed worker-loss boundary in logging02; it does not identify the allocation site, establish a particular operator as the memory cause, or explain the twelve earlier zero-OOM failures.

The [machine-readable analysis](analysis.json) binds the source identity, counters and boundaries. [Kernel excerpts](kernel-target-events.json) retain original line numbers and the complete decoded-kernel hash; full kernel/SSH bytes remain at the private location recorded by the [closure receipt](../logging02-host-closure.json). Earlier OOM events from other cgroups are excluded from this attribution.

| Event | Original evidence |
|---|---|
| Worker identity | Startup server lines 17–18 map worker 2 to namespace PID 167 and worker 1 to PID 169. Same-boot host PID/NSpid/start-tick captures map these to 183782/14376781 and 183784/14376782. Driver is host PID 183665, namespace PID 50, start tick 14376571. Prior live executable hashes match runtime 289 binary `40a78182…ac3497`. |
| First target OOM invocation | Kernel line 3708, monotonic 150579.892738, a `tokio-rt-worker` thread invokes the OOM killer. The thread name does not identify its allocation site. |
| Worker 1 killed | Kernel lines 3804–3805, exact cgroup `277559…fab16`, victim 183784, kill monotonic 150579.928398. |
| Worker 2 killed | Kernel lines 3901–3902, same exact cgroup, victim 183782, kill monotonic 150580.000884. |
| Reaping | Worker 1 at 150583.293254; worker 2 at 150584.054685. |
| Sampler crosses both kills | Original JSONL line 6805 scans 150578.563161076–150584.218392978. Its 5.655-second scan includes both workers' earlier RSS/PSS values and a later, much lower cgroup reading. |
| First sampled worker absence | Line 6806 scans 150584.269802670–150584.296372949 and contains only namespace PIDs 1, 7 and 50. Both worker PIDs were present in every recorded row after their initial appearance and before this row. |
| First terminal runtime error | Server line 20250, 21:58:03 UTC: driver PID 50, Flight body, job 31, stage 5, partition 0, attempt 0, channel 0, gRPC Unknown, peer 127.0.0.1:43503, broken pipe. Server startup lines 53 and 57 directly identify that endpoint as worker 2. |
| Teardown | Session removal and worker stop requests at 21:58:03; server stopped at 21:58:04. Container exited 1 at 21:58:06.310953881 and removal succeeded. |

The kernel and sampler ordering above uses native monotonic coordinates. The post-closure guest UTC/uptime anchor places both kills at approximately 21:57:58 UTC; that is a derived clock conversion, not a kernel-recorded event UTC or a claim of sub-second cross-clock precision. Kernel records supply PIDs and cgroup, not worker roles/start ticks/executable hashes; prior direct identity captures and continuous sampled namespace PID presence support the association, without claiming continuous process tracing. See [selected original sampler rows](sample-boundaries.json) and [startup/error/teardown server lines](server-target-events.json).

The complete timestamp-filtered server scan finds two matching records: the startup DEBUG preface-close at 20:05:13, and the terminal Flight error at 21:58:03. The earlier startup record is preserved and is not treated as the terminal failure. A lexical scan is not a proof that every conceivable failure format is absent.

Terminal `memory.events` is `max=5359`, `oom=14`, `oom_kill=2`, `oom_group_kill=0`; before execution all were zero. Kernel memory usage is at the 100 GiB cgroup boundary. Recorded peak is 107,374,235,648 bytes against 107,374,182,400 maximum. The outer outcome is `oom`, producer outcome `error`, container exit 1 with `OOMKilled=true`, and `outer_timeout=false`. These labels remain distinct.

The controller completed iteration 1, bucket 0, then recorded iteration 2 start at elapsed 873.254836 seconds; no iteration 2 end or correctness result follows. Error elapsed is 6815.326034 seconds. These are diagnostic elapsed values on a shared host, not qualified performance results. Sampler `step` is null throughout, so task/iteration progress cannot be reconstructed from that field. The recorded iteration 2 plan uses partitioned join plus partial/final `min(struct(...))`; this does not prove which allocation triggered the kill.

The sampler requested a 50 ms interval but actually produced 6,836 sequential scans with median 0.523 seconds and maximum 62.490 seconds. Its peak RSS/PSS row crosses the kills. Process readings, shared-page accounting and separately sampled cgroup values must not be treated as a simultaneous decomposition.

Cleanup was attempted after an explicitly uncertain write. `cleanup_errors=[]` is not deletion proof. The last directory scan is line 6821, cleanup phase, 150585.318966472–150585.343799575, and reports 27 staging files totaling 8,257,432,359 bytes while driver PID 50 was still sampled. The driver disappears only in the later final sampler row. This is **not a post-shutdown inventory and does not show 8.257 GB retained at final exit**. The receipt has no `staging_files_after_shutdown` field. Later root-owned volume-space observations or a dedicated path inventory are separate evidence.

[Audit source](audit.py) performs no remote operations, verifies the private kernel bytes against the public closure digest, checks exact boot/cgroup/PID associations and original row boundaries, and hashes all inputs before and after. Outputs were created with exclusive new-file writes. This is an evidence audit, not a new Sail runtime gate.
