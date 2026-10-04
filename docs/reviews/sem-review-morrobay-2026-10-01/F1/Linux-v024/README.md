# F1: Grust 0.24.0 Linux x86_64 confirmation

Status: DONE. Full functional gate passed on Morrobay.

```text
ci-local: PASSED every gate at d2668ec on Linux x86_64 in 3904s
```

The tested commit is `d2668ec7c7dbd7dd728e3976bcfaba3ae51d14ad`, tree
`2674baf6d93109d5b6d1bf49a77a35b4bc7f115a`: peeled `v0.24.0` and the released
main observed at admission. The original request for `fa49fbb7` was superseded
by Fable's release update. The async-trait lockfile fix is in release source
`1cfd03be315e9b66afb6942c7e25d9a0a951f83a`; the tested tag includes subsequent
book distribution files. This verdict covers the exact tested commit.

## Command and coverage

```sh
GATE_DIR=/Users/alexy/gates-linux-f1-024-run02 \
GATE_IMAGE=sha256:add46de4d6bc510d9261a6eb88c399d01b61a03e298c13b68c6d6a11f8887bf2 \
GATE_CPUS=8 GATE_MEM=32g \
DOCKER_HOST=unix:///Users/alexy/.colima/grust-linux-f1-024/docker.sock \
bash /Users/alexy/gates-linux-f1-024-run02/driver/scripts/gate-linux-container.sh \
  d2668ec7c7dbd7dd728e3976bcfaba3ae51d14ad
```

The driver and gate clone were separate, clean, detached copies with that HEAD
and tree before and after. The released scripts were unchanged; `--fast` was
not used. Both formatting checks, locked all-feature workspace build and
Clippy, graph-benchmark Clippy, workspace tests, separate Ladybug tests, pinned
LSQB source fetch, graph-benchmark tests, locked workspace package verification
and third-party package attribution passed. The full script's actual waited
exit code was 0. [Complete original log](evidence/attempt-02/05-full-linux-gate.log)
and [source identities](source-identities.json) preserve the evidence.

The CI scripts use their ordinary development/test profiles with line-table
debug information. No optimization override was added. This is functional CI;
no VM benchmark or native/VM performance comparison was run. The script's
elapsed seconds are retained in its exact verdict and are not a performance
result.

## Environment

| Setting | Observed value |
| --- | --- |
| VM | Separate Colima `grust-linux-f1-024`, native x86_64 VZ, 8 CPUs / 40 GiB |
| Container | Linux amd64, 8 CPUs / 32 GiB; memory-swap limit also 32 GiB |
| Rust / Cargo | 1.99.0 / 1.99.0 |
| Clippy / rustfmt | 0.1.99 / 1.10.0-stable |
| protoc | 3.21.12 |
| Cargo jobs | 2, baked into image; incremental compilation disabled |

Resolved base: `rust@sha256:5d05167b28cef0fa3a6c781cd77949386848191f3382e82cf53bd1277a47a98f`.
The image recipe installs the Trixie compiler/build dependencies, Clippy,
rustfmt, protobuf compiler and `libprotobuf-dev`. Its 613-byte Dockerfile has
SHA256 `5c1081f0a45904d28ecbd077846b918a367d7f25faa167a608dbbf4bff9ff594`.
The protobuf-header compile control passed before CI. The gate does not forward
host Cargo job settings, so the image supplies `ENV CARGO_BUILD_JOBS=2`.

The actual [tool versions](evidence/attempt-02/04-verify-toolchain.log),
[container inspection](evidence/attempt-02/container-cc2c269fa8fc.json),
[image inventory](evidence/attempt-02/package-image.json) and
[Docker events](evidence/attempt-02/docker-events.jsonl) are retained. Container
`cc2c269fa8fc` emitted exit code 0 and a destroy event. No OOM event was observed
in the retained event stream; peak memory was not measured. This does not
establish native benchmark fit under a 32 GiB OS limit.

## Preserved attempts and operational closure

Attempt 01 failed during workspace build with exit code 101: its image lacked
`google/protobuf/empty.proto`. Its cleanup also raised `PermissionError` while
closing the event watcher. The original [failed receipt](evidence/attempt-01/receipt.json),
[build log](evidence/attempt-01/05-full-linux-gate.log),
[traceback](evidence/attempt-01/failure-traceback.txt) and
[manual closure](evidence/attempt-01/manual-closure01.json) remain unchanged.
Root stopped the owned VM successfully before attempt 02.

Attempt 02 added `libprotobuf-dev` and verified that header with protoc. It
reused the stopped owned profile and moved the replaceable Cargo target and
registry caches from attempt 01, for the same commit and Rust toolchain;
[cache record](evidence/attempt-02/cache-reuse01.json) names the moves. The entire
unchanged gate then ran again and passed. These were environment changes;
no source fix or assertion change was made on Morrobay.

After CI passed, attempt 02's controller stopped its VM successfully but
returned 1 because its strict cleanup check found that the selected Docker
context had changed. Its original [receipt](evidence/attempt-02/receipt.json)
and [waited owner exit](evidence/attempt-02/owner-exit01.json) still record that
failure: the production-preservation flag is false. This is separate from the
full Linux script's exit code 0 and exact verdict. The recorded error is
`cleanup ValueError: production Docker context changed`.

During the gate, the production newspaper cycle completed and stopped its
own VM. Its [lifecycle excerpt](evidence/attempt-02/production-lifecycle-excerpt02.log)
shows a stop at 15:55:25 UTC, matching Docker config's observed modification
time. This supports the inference that its normal shutdown removed the
`colima` context; no process-level attribution is claimed. The production VM
configuration retained its original SHA256.

Root's first context selection failed because `colima` no longer existed.
Root then recreated the socket context at
`unix:///Users/alexy/.colima/default/docker.sock` and restored the original
selection, without starting or stopping either VM during this recovery.
[Manual recovery](evidence/attempt-02/manual-closure02.json) preserves the failed
selection, both successful repair commands, unchanged production configuration,
unchanged tested sources, absent owned PIDs/process groups and released locks.
Both the graph and production profiles were observed stopped before and after
recovery. The [root audit](evidence/attempt-02/root-final-audit02.json) binds the
functional verdict, resources, image, source identities and closure records.

## Retention and handoff

[Inventory](inventory.json) lists each portable evidence member with size and
SHA256. Copies preserve original bytes; attempt directories stay separate. The local
`.gitattributes` keeps terminal logs as raw data, including carriage returns and
ANSI sequences, while authored text receives the whitespace check.
The full local results are under
`/Volumes/Apo/graph-tests/results/sem-review-20261001/F1-linux-v024-run01` and
`F1-linux-v024-run02`. Cargo targets, registry caches and VM disks are outside
this portable evidence.

The earlier [ACK plan](../LINUX-v024-PLAN.md) describes attempt 01; its recipe
and planned paths remain historical. This report identifies the corrected
attempt and actual outcomes. No crates.io publication or book deployment was
performed on Morrobay. Native benchmarking policy remains in force.
