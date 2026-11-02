# Checkpoint registry closure and explicit cleanup recovery

Recorded 2026-10-30T06:43:30.162259+00:00. Sail commit
`cba833ae08a4844afcb4e5edef0cc894231d0d82`, based on
`ec8e74d57de51149a774cd4f9048d82039704d0c`.

This unit retains closed checkpoint descriptors when object deletion fails or its
awaiter is cancelled. A later explicit cleanup can retry the session prefix;
metadata is cleared only after storage cleanup succeeds. Closed descriptors are
hidden from public lookup. Insert and admission sealing take the same registry
write lock, and asynchronous deletion does not hold that lock. Removed descriptor
values are dropped after releasing the lock. Storage failures retain their original
typed error rather than being replaced by a combined string.

The five-file [source diff](commit.patch) changes the registry, adds four focused
tests and a controlled object-store fixture, and adds their dev dependencies/lock
entries. [sources.json](sources.json) records full commit, tree and blob IDs plus
byte hashes; the changed source files and base/control registry are copied under
[source](source/). No session-manager or physical writer implementation is changed.

## Validation preserved

| Evidence | Observed result |
|---|---|
| [Rust gate](gate.json), [raw library log](rust.log) | 9 sail-cache + 13 sail-physical-plan + 29 sail-session tests = **51 passed**; format and strict all-target/all-feature Clippy passed. |
| [Optimized receipt](release-sail-cache/receipt.json), [test log](release-sail-cache/test.log) | **4 registry tests passed**, optimization level 3, with one busy process per logical CPU (10). All ten owned workers were terminated and joined. |
| [Public receipt](public/receipt.json), [JUnit](public/pytest.xml) | **300 selected public cases passed**, no failures/errors/skips; exact selected identities and before/after source pins match. |
| [Upstream report](public/upstream.json) | **67 upstream Python executions passed, 63 unique IDs**; the inherited `ReusedConnectTestCase.test_assert_remote_mode` runs five times. |
| [Unchanged-production control](control/receipt.json), [raw failure](control/test.log) | **Expected failure**, exit 101: `cleanup discarded recovery metadata`. One selected test ran and failed. |

The four new tests cover partial deletion failure and explicit retry, a held
storage deletion with closed admission and an available registry lock, abandoned
cleanup with retained metadata and retry, and session-prefix isolation plus
idempotent successful cleanup. They use channels/manual polling for the held
phase. The paused-I/O test does not exercise every concurrent insert/seal
interleaving; that ordering also follows from their shared lock in the source.
The optimized run is a stress check, not a performance measurement or proof of
all schedules. Raw compiler/linker warnings remain in the logs.

The public CLI and its server both come from this candidate. The client and server
reported Spark **4.2.1**, and the upstream runner pins Spark source
`617618396087429b5627a86ce933bb0f5d6645cb`. The owned server exited with code 0 and
no remaining listener. [binary-verification.json](binary-verification.json)
records an additional archive-time byte check of the actual CLI and optimized
test binary against their receipts; binaries are not copied into the packet.
The harness checks the installed PySpark version and pinned source, not a hash of
the complete installed wheel.

The frozen public selection and its original input receipts are preserved in
[public-harness](public-harness/). Its preparation commit is the earlier
`e8c47f2d9ccd3383ce03fe0a4b33ba20707ff33b`; this is selection provenance, not the
candidate run's source pin. The candidate receipt names `cba833ae` and verifies all
35 frozen helper/test source hashes. The 300-case selection includes the two
corrected nested-materialization cases and excludes the withdrawn flow-config
assertions. This adds no newly qualified original Scala registration and does not
change the canonical 462-registration inventory.

## Control and scope

Control commit `9bbe418025665a87caff3ab6ec27c147c50e5b43` has the same parent as
the candidate. Its registry implementation is byte-for-byte the base production
file plus only a `cfg(test)` module declaration. It includes the candidate's test
files and dev dependencies; the sole file differing between control and candidate
is `remote_checkpoint.rs`. The [control patch](control/control.patch), exact
[harness](control/run.py), source pins and raw failure are retained. The selected
test first proves partial deletion and the original typed storage failure, then
fails at test line 105 because the old implementation discarded the descriptor.
The candidate passes the same assertion; neither subject nor assertion was
weakened. The control is retained as `refs/sdp/controls/checkpoint-registry-recovery`
in the Sail repository.

This registry is **not an object-store effect fence or a full session lifecycle**.
A resolved relation path is not a storage lease. Earlier admitted/detached writes
can still mutate storage after an awaiter is dropped. The cancelled-cleanup test
uses a fake store whose held request stops with its future; it explicitly makes
no such claim about a real provider. Retained descriptors are in-memory recovery
metadata, not durable restart recovery. Callers must retain the registry owner
and invoke retry; this unit does not add a retry supervisor. Concurrent cleanup
attempt ownership, session Closing/Deleted acknowledgement, outer Spark/pipeline
operations, cluster shutdown and writer/commit quiescence remain separate work.
The public regressions demonstrate compatibility, not these missing guarantees.
Iggy streaming, CDC execution/recovery and complete Spark SDP acceptance remain
outside this unit.

## Rechecking the archive

[verify.py](verify.py) performs only byte/source/receipt/count/identity checks; it
does not run a gate, server, test or build. It checks the archive against immutable
Sail Git objects and works from a detached Grust checkout:

```sh
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python /tmp/sail-sdp-verify-checkpoint-registry.py /Users/alexy/src/grust-sdp-review-gate --sail-repo /Users/alexy/src/sail-pipelines-proposal
```

The same script is copied as `verify.py` for later use. Raw input receipts/logs
are unchanged. [provenance.json](provenance.json) hashes every other packet file;
its own hash is intentionally not recursive. Absolute paths in historical
receipts/harnesses describe the recorded runs, not a portability guarantee.

Archive validation used the Sail Python 3.12 environment. The initial system
Python 3.15 invocation failed loading Expat while parsing JUnit, before a verifier
verdict; this host interpreter failure is recorded in
[archive-validation.json](archive-validation.json). It is not a failed product gate.
