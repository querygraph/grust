# F1: Linux x86_64 confirmation of Grust 0.24.0

Status: ACK; execution and the functional verdict belong to the root coordinator.
Expected evidence is `F1/Linux-v024/README.md` beneath this review directory.
This plan provides no Linux gate result, benchmark, crate publication or book
deployment verdict.

## Source and full gate

Fable's release update supersedes the original `fa49fbb7` request: release
source is `1cfd03be315e9b66afb6942c7e25d9a0a951f83a`; released `main` and
peeled tag `v0.24.0` identify
`d2668ec7c7dbd7dd728e3976bcfaba3ae51d14ad`, tree
`2674baf6d93109d5b6d1bf49a77a35b4bc7f115a`. Morrobay will confirm that exact
released commit on Linux x86_64. The earlier fa49 preparation and its failures
remain historical evidence; they do not qualify this released source.

Run the released, unmodified
[container gate](../../../../scripts/gate-linux-container.sh), with no `--fast`.
Its detached clone and per-commit target run the complete
[local gate](../../../../scripts/ci-local.sh): both formatting checks, locked
workspace build/Clippy/tests, graph-benchmark Clippy/tests and pinned sources,
separate Ladybug tests, locked workspace package verification and
[package attribution](../../../../scripts/verify-package-attribution.sh).
Require a clean detached source with the same HEAD/tree before and after and
the final `ci-local: PASSED every gate ... on Linux x86_64` line. This runs
functional tests and package verification, without publishing packages.

Root's plan is retained at
`/Volumes/Apo/graph-tests/results/sem-review-20261001/F1-linux-v024-run01/plan.json`
(1163 bytes, SHA256
`593c435f5244ac7feb74ec764c223b517d3dba39542cc5561af982f13f68be40`).
The source/driver checkout and private targets/registry are under
`/Users/alexy/gates-linux-f1-024-run01`; source copies match exact released Git
blobs. The complete logs, attempts, tool/image identities, source hashes,
closure and result receipt will remain on Apo.

| Released file | Bytes | SHA256 |
| --- | ---: | --- |
| `Cargo.lock` | 276409 | `7025c985a81e82b9b7107e6effbb976c2b35b8de8038c438ac60284b609e9596` |
| `scripts/gate-linux-container.sh` | 3346 | `84e7b3f48ff7390a33984c28316dc15684420a6e183e602e9597a50bcad7b2f6` |
| `scripts/ci-local.sh` | 3317 | `3ffb1a0c9cc53ca347a65b164544591082ed1a2c00b63496b4b6e95427573907` |
| `scripts/verify-package-attribution.sh` | 1063 | `f632390ca74d6d4940f05620cfb651fec62f492ed1b82fa7d6812df4f2c46924` |

## Tools, resources and ownership

The separate Colima profile is `grust-linux-f1-024`: 8 CPUs and 40 GiB VM
memory. Its gate container uses `--platform linux/amd64`, 8 CPUs,
`--memory 32g --memory-swap 32g`. These are configured limits; actual memory,
OOM events and the complete gate outcome must be observed. No benchmark or
native/VM timing comparison is part of this confirmation.

The image recipe starts from `rust:1-trixie`, installs the required build
packages, rustfmt, Clippy and protoc, and selects Rust 1.99.0. It sets
`ENV CARGO_BUILD_JOBS=2` in the image because the unmodified gate does not
forward a host setting. Record the actual resolved image/base identities,
Rust/Cargo/Clippy/rustfmt versions and package inventory. The planned
`image/Dockerfile` is 544 bytes, SHA256
`1f28d22ad21d3ee0c1ddfeba3d35520ae687874ea4282f80535156c03a3d6e64`.
Host free-space admission is at least 64 GiB; caches and targets are private.

Root selects only
`DOCKER_HOST=unix:///Users/alexy/.colima/grust-linux-f1-024/docker.sock` for this
job, removes a conflicting process `DOCKER_CONTEXT`, and uses profile startup
without activating it. The production default profile, configuration and
selected `colima` context are preserved; the active newspaper cycle remains
outside this job. Root owns serial locks, the full subprocess wait, container
closure, and stopping only the newly owned profile when the job finishes.
Failures, partial logs and disks are preserved before any follow-up attempt.

Native benchmarks remain the operator's policy. This additional VM is solely
for the requested Linux functional confirmation; it does not restore the
retired benchmark VM or authorize a release, crate push, or book deployment.
