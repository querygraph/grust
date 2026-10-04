# Compact replay closure and SSSP buffer reuse

Recorded UTC: 2026-10-01T01:52:28.505671+00:00

The scale-24 compact-runtime replay completed and passed its producer certificate.
A separate bounded reader has now checked the physical output values. The SSSP
buffer-reuse component is independently gated and pushed. These are distinct
results: the replay used Pecan and the earlier installed native wheel, while the
new buffer change applies to Argentea and has local core/native qualification.

## Closed scale-24 replay

The frozen `logging03-compact` cell used runtime `56194b170155`, controller
`3a9028057`, and native wheel source `ffcfbd569`. It ran Pecan SSSP DeltaStar on
16,777,216 vertices and 268,435,456 input tuples, with two worker processes,
32 partitions and a 100 GiB container cap without additional swap. It converged
in 60 iterations. The producer recorded 16,777,216 unique output vertices,
8,862,601 reached vertices, a passing all-edge/rooted-tight-edge certificate
with 22 witness rounds, and a passing parent-tree check. The certificate uses
relative edge tolerance 1e-12 and reports a conservative accumulated absolute
distance-error bound of 9.326049224058808e-05; it is not a precomputed full-vector
oracle. [Independent closed review](logging03-closed-review/README.md).

Whole-container cgroup peak was 35,481,849,856 bytes (33.05 GiB), with zero OOM
or OOM-kill events and clean producer/container exit. This includes the container's
processes and charged cache; it is not worker RSS. Sampled process PSS, sampling
gaps, VM steal and host pressure are retained in the review. The VM reported
zero steal, while the macOS host recorded substantial swap activity. This shared
host supplies no dedicated-host absolute performance result. The earlier
logging02 run ended in two worker OOM kills at its 100 GiB cap, so it supplies
neither a completed timing denominator nor an uncapped peak-memory denominator.
No speed or peak-memory reduction ratio is asserted for that pair.

The original diagnostics and receipts are available in a
[lossless evidence package](logging03-publication/README.md). Its single
13,848,616-byte gzip reproduces the exact 413,644,800-byte diagnostics archive;
the restoration helper reconstructs all 14 original collection files byte for
byte. The full server log is retained. The standalone wrapper-exit record and
recovery's unknown lost-session attribution are both preserved; the producer,
container and collection evidence independently establish closure.

## Supplemental physical-output check

The independent PyArrow scan checked all four recorded Parquet files against
the producer inventory, with unchanged file hashes and footer identities before
and after reading. It found 16,777,216 unique IDs, no missing or duplicate IDs,
one valid source row, 7,914,615 unreachable rows, and no NaN, infinity, negative
finite distance, invalid ID, or invalid null/parent/hop metadata. Reached count
matches the producer. [Independent execution audit](logging03-physical-execution/independent-final-review.json),
[physical counts](logging03-physical-execution/attempt03/evidence/physical-output.json).

The checker had one CPU, a 2 GiB memory cap without additional swap, no network,
read-only graph inputs and a separate writable evidence directory. It exited
zero, without OOM, and was removed after its state was captured. This is a
physical-value/domain check; it does not recompute shortest paths or independently
prove parent-edge chains, and does not replace the producer certificate.

All preparation failures remain: the default host Python lacked a required
hashing function; the first checker could not enter a private helper directory;
the next identity could not execute the reader under `/root`; and an initial
permission probe inherited an incompatible working directory. The corrected
control established actual interpreter and mount permissions before the final
scan. Executor v4 uses container UID/GID 0:20, no added capabilities, and a new
host-owned 501:20 evidence directory with mode 0770. Earlier evidence and result
files were unchanged. [Prepared changes and controls](physical-output-execution-preparation-v4/README.md).

## Argentea SSSP buffer reuse

Commit `fc094a0c25a49edeac2f9f0195aa973421a21a43` is pushed to
`work/sssp-candidate-buffer-reuse` and `work/stream-review-followup`. Non-Done
publication reuses the incoming candidate vector for successor labels while
preserving the prior immutable snapshot, charged merge order, parent tie rules,
DeltaStar bucket carryover and final publication checks. Its reservation remains
live through producer-array teardown. The full vertex scan still occurs.

All 36 allocation cells (18 matched pairs) are retained. At 65,536 local vertices
in one measured owner with three configured partitions, one dense allocation is
removed and measured finish-window requested/admitted peaks fall by 2 MiB.
Allocation volume falls by 2,097,144 bytes, including the additional eight-byte
reservation slot. Metered work and retained admission are unchanged; Done cells
are unchanged. These are local allocation/admission observations, not RSS or
cluster timings. [Boundaries, controls and all cells](sssp-candidate-buffer-reuse/README.md).

The exact detached gate passed 141 core and 55 native tests (49 Argentea), both
ordinarily and with all ten local cores saturated; independent review passed.
The delivered commit is the exact tested descendant, with no intervening merge.
[Exact gate](sssp-candidate-buffer-reuse/exact-gate/receipt.json),
[verified fork delivery](sssp-candidate-buffer-reuse-delivery.json).
No combined Linux build, new worker-loaded wheel, Flight or multi-host scaling
verdict is added by this component.

The historical zero-OOM stream failures remain unexplained. The prepared
[cluster program](CLUSTER-PREPARATION.md) still needs fixed-resource placement,
strong/weak scaling, skew and exchange measurements. Full scans, high-degree
owner imbalance, partition-count control traffic and repeated checkpoint I/O
remain structural limits. Near-linear scaling has not been demonstrated.
The six-cell runtime comparison and its later physical scans are outside this
closed update; their observations will retain a separate measurement boundary.
