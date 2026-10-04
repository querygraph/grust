# Native MinIO store03 continuation

Source only. Root owns copying, actual old-store closure, private credential
access, service launch and final engine/service shutdown. The old store02
failed timeout and all original helpers remain unchanged.

## Admission and plan

Copy the six production helpers listed in `freeze01.json` byte-exact to one
fresh Capitola helper directory. Root constructs `ContinuationPlan` from the
actual original store02 public plan, retaining binary/build receipt,
address, ports, bucket, disk and RSS bounds. Override only:

```text
root = /Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x1-minio-store03
data_root = /Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/x1-minio-store02/data
timeout_seconds = 43200  # accepted range 28800..86400
prior_configuration = actual Pin of original store02 plan
prior_ready = actual Pin of original store02/ready.json
prior_producer = actual Pin of original store02/receipt.json
prior_wait = actual Pin of original x1-minio-store-wait02/wait-receipt.json
prior_root_closure = actual Pin of root's independent expired-store02 closure
```

The private root stays `/Users/alexy/.local/state/querygraph/x1-minio-store02`.
Do not copy, print, pin or hash `credentials.json`. The original SecretStr
reader opens it only at runtime, requiring an owned regular nonsymlink 0600
file. This helper creates no credential file and no data directory.

`PriorClosure` uses the same field names as the actual expired-store01 root
closure, with outcome `closed_failed_expired_native_store02`:

```text
producer, original_wait, server_wait: actual public Pins
owner_pid, owner_pgid: actual original owner
actual_wait_completed, owner_group_absent, source_unchanged,
immutable_closure, all_recorded_owned_processes_absent, locks_released: true
returncode: 1
observed_absent_pids, observed_absent_groups: actual current identities
private_credential_contents_or_hashes_observed: false
forced_cleanup: false
signals_sent: []
```

It must include original server, owner and generic waiter IDs/groups, plus
server-observed child PIDs. The helper binds these to original ready/wait
records, observes all listed numeric IDs/groups absent, verifies old public
source/config records, requires the MinIO lock absent, then acquires that same
lock exclusively and repeats old-store admission. It sends no signals to old
IDs. It does not require the still-running graph owner to have closed.

Existing data/private directories must be same UID, nonsymlink and not group
or other writable. Endpoint/bucket/binary are fixed at the original
`192.168.4.61:49190`, `qg-x1-native-20261004b`, and ad30fd8d CLI. GOMAXPROCS=4,
GOMEMLIMIT=2GiB and FD soft limit8192 are unchanged. Only the original tiny
probe key is put/read/deleted, without bucket creation.

## Root launch

Use the original native Capitola Python and actual generic waited launcher.
Its argv must bootstrap the copied helper directory before running:

```text
PY -I -B -c "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')" HELPERDIR HELPERDIR/store_minio.py --plan ACTUAL_PLAN
```

The generic wait timeout must exceed the declared store lifetime plus startup
and cleanup (for43200 seconds use at least43800). Use a fresh public waiter
root, retain real owner/server/waiter PID, actual wait/return code and no-force
fields. Purge inherited GIT_* only in the child environment. Root starts only
after its actual independent store02 closure and old-lock release.

The same backend/credentials make later access possible; this helper does not
claim that an in-flight graph export would survive an outage. Original graph
and service failures remain distinct and preserved.

## End after actual engine closure

Keep the existing `StopRequest` contract: root writes fresh
`store03/stop-request.json` only after all case owners/groups are closed and
their source/config closures are pinned. `reason="engines_closed"`,
`all_engine_owners_closed=true`, and actual `closure_receipts` plus
`owner_wait_receipts` are required. Copied public proof paths are allowed only
with byte-identical content and current Pins. A live engine or changed source
proof is refused. Normal shutdown reuses the original OwnedChild/redactor/
actual wait/force classification and releases only its own store lock.

Hard deadline or forced shutdown remains failed, never normal lifecycle
qualification. No graph math, full memory envelope or historical cause is
qualified by service readiness/lifecycle.

## Source checks

Four pure controls cover backend/lifetime refusal, existing-directory
symlink/write-mode refusal, live-engine stop-proof refusal and scalar proof
refusal. Final isolated Ruff/format on three changed sources, strict mypy on
seven files and all four pure controls pass. Initial invalid Ruff-config
invocation is retained under source-gates01; it launched no service. No
private file, data payload, SSH, process observation, native or server action
was performed by the author.
