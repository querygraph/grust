# X1/X2 evidence and remaining causal work

Source audit: exact Grust `1bfdf7c37e49c3de09113aeacfb89a6d377cca64`.
Sources and byte hashes are in `vortex-preparation01/source-evidence01.json`.
This review reads source and retained small evidence only. Root owns execution.

## Findings supported by existing evidence

| Case | Evidence and result | Limit |
| --- | --- | --- |
| X1 Argentea two-host scale24 | The merged log has 651 failures. First FAILED is line2305 at06:12:10Z; the h2 reset-limit warning is line2748 at06:12:11Z after443 failures. | Initiating peer/cause remains unexplained. Seconds-resolution merged logs do not prove causal ordering across hosts. |
| X2 original relational cells | `docs/STREAM-LOSS-STATUS.md` lists12 rows with zero recorded cgroup memory events,11 with sampled PSS20–66GiB; one peaks91.9GiB. | No recorded cgroup OOM does not exclude pool refusal, host pressure, uncaptured memory events or another fault. |
| logging01 BFS frontier replay | Same full Docker cgroup in kernel OOM evidence; one `oom_kill`, Docker OOMKilled true. | Worker2 as kernel victim is inferred because live namespace mapping was absent. This replay does not explain the original zero-event cases. |
| logging02 SSSP replay | Live PID mappings, same-boot kernel/cgroup records and two worker kills prove OOM for this replay. | Later Flight/body-read messages are consequences here; no retrospective diagnosis of earlier cells. |
| logging03 compact replay | Independent scan of all16,777,216 output rows and producer certificate pass; zero OOM events; lifetime cgroup peak35,481,849,856B. | A completed later profile, not proof the original fault was repaired; peak exceeds32GiB. |
| h2/Tonic controls | Ordinary cancellation does not consume h2's error-reset budget. Tonic DEBUG exposes a deliberately induced keepalive timeout. | Reset-cap, keepalive/starvation and flow-control explanations for historical faults remain hypotheses. |

The exact pinned `RESULTS.md` and `STREAM-LOSS-STATUS.md` already preserve these
distinctions. Later Argentea completion-count, inbox-allocation, input/lease
lifetime and parent-certificate changes have their own scoped controls. Their
passing tests do not establish a historical HTTP2 root cause.

## Current local prerequisite

The existing optimized runtime9f retains the bounded worker/Flight diagnostics:
`crates/sail-execution/src/diagnostics.rs`, 4,206B,
SHA-256 `25ea6431b187f80230a12778b375f9802db81b76017caecc92b981c015dbf43a`.
It preserves PID, task/stream/peer context and bounded typed error sources before
conversion. Limits are4,096B and32 nested errors, not a global first-fault ledger.
The scheduler's selected returned error is not a first-fault timestamp.

Peer `graph_storage_setup` prepares the runnable separately named
`stream-logging` case in `C2-D2-native01`: a fresh native server, two process
workers, successful real-exchange aggregate exported to full checked Parquet,
then a deliberately induced task error:

```sql
SELECT raise_error(concat('sem-stream-diagnostic-sentinel', ':', cast(count(*) AS STRING)))
FROM range(0, 128, 1, 2) GROUP BY id % 2
```

Root must require both workers actually register/execute, retain executed
exchange/task metadata and raw logs, compare all successful result rows with
the independent arithmetic fixture, and establish sentinel visibility in the
client plus attributable typed worker/driver failure records. The failed query
is expected; failure of the successful oracle, log proof or owned closure is not.
Direct PID waits, final group absence and retained pin/inventory closure are
required. This is diagnostic qualification on a new profile. It closes neither
X1's two-host cause nor X2's original large-cell cause.

## Original replay admission and first discriminating step

The staged handoff at
`/Users/alexy/src/sail-extensions-gates/argentea-two-host-debug-20261001-handoff`
is historical experiment material. Its reproducer is not a qualifying
supervisor: no full input admission/watchdog/output certificate/independent
remote closure is supplied. Never call its old `qualified_completion` a new
full correctness/resource/archive verdict.

X1 originally used runtime/nativeffcf, prepared source837 (Python-only settings
delta), scale24 input generation16,777,216 vertices/268,435,456 undirected edge
tuples, BFS source13507776/reference/cap8, P32,8threads/process,48task slots,
32GiB ordinary pool/process,16GiB native quota, stream creation900s/idle86400s.
Its runtime binary/native and original physical inputs must be admitted on both
hosts. Official LDBC Graph500 files and new9f are different inputs/profiles.
The old custom worker launcher omitted HTTP2 settings: inherited/default
settings and any later explicit-forwarding control must remain distinct.

As reported by root, its current direct Capitola SSH attempt was rejected by
authentication. Restore access and establish a durable owner/lease per host,
then first run a tiny two-host Argentea BFS fixture with full oracle and actual
work on both hosts. Include signed/highbit IDs, loops, duplicate edges and an
isolate. Admit exact runtime/input/native pins and independent host-specific
resource/disk/closure evidence before a single scale24 diagnostic replay.

For X2, select the original zero-event Grenada reference BFS shape (reported
failure108s into iteration2, sampled42.8GiB), not the frontier replay which later
OOMed. Its exact original runtime/controller/input receipt and encompassing
100GiB Linux-era profile must be pinned. Current native execution is a separately
declared platform/profile; macOS RSS must not be labelled PSS/cgroup memory.
If only32GiB is admitted, the historical shape is `not_admitted` rather than a
shrunk-pool reproduction. The user forbids VM benchmarks; no historical Linux
benchmark VM is restored by this plan.

For every replay, capture first complete typed failure before cancellation and
shutdown, actual per-process nonsecret environment, endpoint/PID mapping,
pressure/OOM/pool refusal counters appropriate to the host, and raw logs. Full
BFS distances must cover every unique original ID including0, with exact source
and unreachable policy; preserve declared parent/hops semantics and a rooted
tight-predecessor/edge certificate. Retain failed writes and final namespace
inventory. Hash and verify the archived copy before disposing of raw evidence.
Choose one next repair/control from an observed initiating fault; retain
`unexplained` if only cancellation is observed. No automatic retries or broad
matrix is justified by the generic h2 body-read error alone.

## Sem scope

X1/X2 causal investigation and D1's Vortex alternative are assigned evidence
work. Native/local versus process-cluster measurements and resource admission
are explicit protocols. Optional server-side graph execution, parked
optimizations and PR35's billion-node design draft are separate proposals.
This preparation does not implement or mark them done.
