# Prepared post-closure physical-output check

This is local preparation only. No Docker, SSH, result read, staging, or execution
has occurred. Logging03 must finish and its collected evidence must pass the
pinned closed-cell integrity verifier before a bundle can be prepared. The
original producer outcome remains separate, including errors or mismatches.
This check supplies physical Parquet value/domain evidence; it does not compute
shortest paths, certify parent edges/chains, qualify timing, or replace the
producer's validation.

`prepare.py` admits only the exact reviewed logging03 configuration
`b28132996612b11edb77bb02019288e4a562db5e4d22c4430a6a8815a220aea0`, its
original cell namespace, 16,777,216 vertices, and source 13,507,776. It requires
operator-supplied SHA256 pins for the locally collected producer receipt and
closed-cell audit. No completed receipt or output inventory is fabricated for
the still-running cell. It copies the unchanged physical verifier
`4c5fe87d0eb0b3f4aec3e70841bc7db968017f952dda6978840d101d2f2f7872` and
small evidence files into a new private bundle; it does not copy result Parquet.

After closure, on the local evidence workstation (substitute actual pinned
paths/hashes; this command does not run Docker):

```sh
python3 -I -B prepare.py --receipt /absolute/collected/diagnostics/receipt.json \
  --receipt-sha256 ACTUAL_RECEIPT_SHA256 --closure-audit /absolute/closed-audit.json \
  --closure-sha256 ACTUAL_CLOSED_AUDIT_SHA256 --bundle /private/tmp/NEW-physical-log03-bundle
```

The printed request hash seals the exact bundle. Review it, then transfer only
that bundle to a new directory on Morrobay. Staging and execution require the
parent's later authorization; neither is part of this preparation. On Morrobay,
with the reviewed bundle and a new output directory outside it, first inspect
the dry command (no Docker contact):

```sh
python3 -I -B /absolute/NEW-bundle/supervise.py \
  --request /absolute/NEW-bundle/request.json --request-sha256 ACTUAL_REQUEST_SHA256 \
  --output /absolute/NEW-physical-log03-evidence
```

Only after the graph run and all other Docker work have stopped, explicitly
launch using the same command plus `--execute-after-closure`. It returns a host
supervisor PID and creates `launch.json`. The child has a new session and closed
stdin, with stdout/stderr going to files; loss of the initiating SSH/tool session
does not intentionally terminate it. No polling loop, SSH command, automatic
workload continuation, or automatic retry is included. Losing the host/daemon
or supervisor itself can leave only the durable initial outer receipt; absence
of a final receipt is incomplete evidence and never a pass.

The supervisor checks zero running containers before creation and again before
start, the exact existing image ID, and the existing named volume. These are
point-in-time checks, not a global lock: the operator must keep this serial with
all other Docker work. The check receives one CPU quota, 2 GiB RAM, zero allowed
swap, 64 PIDs, no network, a read-only root filesystem and dropped capabilities.
`/targets` and the bundle at `/work` are read-only. Only the new evidence output
is mounted writable at `/evidence`; normal Docker bookkeeping remains external
to those mounts. No result/staging tree is copied, deduplicated, modified or
removed. The original Sail runtime and native wheel are hashed but never run or
imported.

The reader checks the VM boot, cgroup limits, original native hash and exact
compact561 binary hash. The configured original venv, pinned image and previously
observed Python 3.12.14 / PyArrow 21.0.0 / NumPy 2.5.3 versions are required.
Current interpreter and selected package files are newly hashed in its admission
receipt; those are not a claim of earlier full-venv byte identity. PyArrow's
internal threads and BLAS thread settings are one. The frozen verifier separately
admits at most 2 GiB of recorded compressed results and 256 MiB per row group's
reported uncompressed bytes. These bounds do not guarantee decoder peak memory;
the outer 2 GiB limit may kill the checker, which is retained as an incomplete
physical audit, without changing the original benchmark outcome.

The supervisor retains every Docker command's stdout/stderr, timeout or OS error,
then captures exited Docker state including `OOMKilled` before removal. It uses
no `--rm`. On a timeout it kills only its own exact container ID after verifying
both request and unique execution labels. An uncertain create response is
recovered by the unique name and both labels. If ownership or state cannot be
verified it records incomplete cleanup and does not remove an unverified
container. The 1,800-second wait is followed only by bounded state/log/cleanup
commands; it is not a precise overall wall-clock cap. The outer receipt, admission
receipt, and physical report remain distinct. Exit zero requires a physical pass
and successful lifecycle checks; it still is not a benchmark pass.

`test_preparation.py` contains tiny local mocks only: closed-input admission,
namespace/domain/runtime rejection, failed-producer preservation, exact command
caps, busy-Docker rejection, OOM, timeout, uncertain create, malformed inspect,
OS errors, foreign execution refusal, and state-before-removal ordering. It does
not prove that Docker or the original venv runs successfully with these limits.
There is no six-cell pair execution support in this bounded first preparation.
