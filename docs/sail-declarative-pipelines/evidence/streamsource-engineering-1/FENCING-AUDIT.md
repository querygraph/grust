# Fencing source audit

Scope: current upstream Sail `85c6cca01` and bounded pipeline reference
`99dc47788`. Paths in the table below refer to the latter unless labeled
upstream. This is source inspection and protocol analysis, not a new execution
of the fencing or crash suites. Source hashes are in fencing-source-hashes.json.

## Findings

| Finding | Source evidence | Consequence |
| --- | --- | --- |
| Managed Delta and Iceberg bypass fenced execution | `autocdc/execute.rs:119-130,654-677` explicitly treats catalog ordering as sufficient and calls `run_plain_flow` | Replace this assumption with required enforced ownership at commit acceptance |
| Existing Delta fence has narrower scope | `sail-delta-lake/src/physical_plan/commit_exec.rs:1032-1038` refuses catalog-managed and newly created tables | Generalized fence is new adapter work, not a metadata flag |
| Fenced effect acceptance binds exact staged bytes | `commit_exec.rs:1043-1077`; `autocdc/authority.rs:106-158`; `sail-sdp-control/src/control.rs:567-632` | Reuse stable request, expected head, prepared digest and staged-entry ratification |
| Publication is independently recoverable | `sail-delta-lake/src/fenced.rs:140-222`; `control.rs:614-632` | Accepted bytes may be published after takeover; new unratified effects must fail |
| Existing property covers cooperating Sail writers | `fenced_commit.rs:66-72`; `commit_exec.rs:92-123`; `fenced.rs:96-120` | No evidence that another engine honors `sail.autocdc.authority`; table property alone cannot claim universal fencing |
| Worker token transport is not authority transport | `sail-execution/src/proto/codec.rs:1153-1202` carries JSON token; `session_factory/worker.rs:39-70` installs no FencedCommits authority; `commit_exec.rs:76-84` rejects token without authority | If a fenced commit stage runs on a worker, placement or authenticated authority access must be supplied. This path inference is not an executed cluster failure |
| First auxiliary commit is an explicit exception | `autocdc/durable.rs:245-269`; `authority.rs:40-45,85-99` | Creation/enrollment must be included in the new protocol; no unfenced birth escape |
| Current authority backend is qualified for one process | `sail-sdp-control/src/turso_store.rs:1-5`; local builder at `:81-85` | Do not promote local database reopen tests to multi-host takeover or power-loss evidence |
| Warehouse state marker is not an atomic ownership primitive | `autocdc/execute.rs:175-273` reads then uses unconditional put for initialization/adoption | Preserve detection intent, but use atomic reservation/shared authority for distributed ownership. Concurrent first initialization is an unexecuted race inference |
| Catalog interfaces are useful integration seams, not a fence proof | upstream `sail-catalog/src/lakehouse.rs:23-36,126-154`; reference `provider/mod.rs:148-159` | Capability and request/outcome types should carry typed fencing semantics; raw requirements/payload alone do not enforce them |
| Iceberg requirements validate metadata state | `sail-iceberg/src/physical_plan/commit/commit_exec.rs:303-437,456-467` | A stale owner can reload current metadata; snapshot CAS must be combined with ownership enforcement |
| Registry lock failure is fail-open in its enumeration | `sail-common-datafusion/src/fenced_commit.rs:94-106` returns empty on poisoned lock | Fail closed on unavailable authority discovery; the durable table property may still protect an already marked table, so this is not a universal bypass claim |

`autocdc/...` expands to
`crates/sail-spark-connect/src/pipelines/autocdc/...`; other crate paths start
with `crates/`. Line references identify inspected definitions, not execution receipts.

## Required replacement contract

Every durable target must expose an enforced commit capability. Its acceptance
operation serializes current authority/owner/generation, table incarnation,
expected head, prepared effect identity and content binding. It returns an
idempotent result for an identical request, rejects identity reuse with changed
content, and distinguishes definite rejection from unknown acceptance.

A lease only permits takeover. A preflight check followed by a normal CAS is
unsafe: an old writer can reload the newest head and successfully commit after
its successor. Conversely, publishing an effect durably accepted before takeover
is allowed only for those exact bytes and must be reconciled before later work.

Cover every visible mutation, including creation, enrollment, append, merge,
overwrite, deletion, schema changes, no-op completion, recreation and refresh.
Cleanup respects all pending accepted artifacts and recovery references.
No fallback to external single-writer convention remains in the design.
Unsupported targets are temporarily refused while their required adapters are
built; refusal is not a substitute for implementing the requested support.

Prefer the existing catalog commit authority. For a backend without an atomic
ownership condition, an enforced commit service may be necessary, with exclusive
publication permissions and explicit deployment costs. A custom Delta property
is insufficient for non-Sail writers. A protocol feature is a separate
interoperability change, not something this review assumes exists.

## External protocol references

The official [Delta protocol](https://github.com/delta-io/delta/blob/master/PROTOCOL.md)
requires supported writer features and directs catalog-managed writers through
the catalog. It does not define Sail's owner generation. The official
[Iceberg specification](https://iceberg.apache.org/spec/)
requires atomic metadata replacement while leaving the atomic mechanism to the
catalog. The need to combine those mechanisms with ownership is this review's
engineering inference, supported by the local request/commit paths above.

## Existing test coverage and new checks

Reference source contains `a_stale_owner_cannot_publish`,
`another_session_refuses_a_write_to_an_enrolled_table`,
`a_replayed_merge_does_not_publish_again`, authority takeover tests during
ratification/preparation/completion, and durable recovery after ratification.
These bodies establish intended coverage; they were not rerun here.

Require actual target-path tests for stale owner after latest-head reload,
preflight/takeover race, accepted-but-unpublished recovery, timeout reconciliation,
changed request content, creation race, target recreation, refresh, metadata
mutation, worker authority loss, authority restoration and another permitted
client. Run against each admitted backend and transport, not a generic fake
whose CAS is assumed to fence ownership.
