# Grenada weighted follow-up

`run_grenada_gate3.py` prepares exactly two fresh-container cells, base `ffcfbd569`
then candidate `edc2c7c8`, using `--engine nutmeg-datafusion --algorithm sssp
--variant frontier`. This checks Grenada's schema adapter feeding the same Pecan
controller. It is one output/memory crosscheck per controller on a shared host,
with no statistical timing conclusion and no additional warmups.

The launcher reads the completed Pecan suite's `plan.json` and uses its exact
runtime, native package, resources, connection settings and fixture path. The
8-CPU/12-GiB envelope, two workers, four partitions/threads, 16 task slots per
worker and 3-GiB per-process Sail pool remain the same. It does not change or
copy any running-suite script, source, dataset, wheel, or binary. It requires
all 14 prior cells to have terminal outcomes before executing; prior failures
remain failures and are copied into the follow-up plan.

The 16,384-vertex, 529,723-edge weighted fixture is reused at the original
`pecan-gate3/datasets/weighted16k` path. Precheck compares its full manifest with
the preceding suite's collected manifest. Each `graph_cell.py` invocation
checks the file inventory/hashes and certifies complete distance output and
parent trees against the existing independent reference. Each returned
manifest must still match the prior one. There is no fixture preparation step.

Copy only the new `run_grenada_gate3.py` and `test_grenada_gate3.py` beside the
already-copied, unchanged `run_pecan_gate3.py` on Morrobay. Inspect the dry plan:

```sh
python3 -m unittest -v test_grenada_gate3.py
python3 run_grenada_gate3.py \
  --matrix /absolute/path/to/existing/diagnostic/harness \
  --prior-plan /Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/pecan-gate3/plan.json
```

After the preceding suite is done, use the same command with `--execute`.
Default output roots are `/targets/sail-stream-experiments-20260930/grenada-gate3`
in the VM and
`/Users/alexy/src/sail-extensions-gates/stream-experiments-20260930/grenada-gate3`
on the host. They must be new paths. Override `--root` and `--output` for another
attempt; keep the same `--prior-plan` to reuse the same source/fixture setup.

Every outcome, correctness receipt, native/binary identity, execution memory
peak and VM steal fraction is preserved. Full data/staging/results remain in
the VM; collection is restricted to the same flat diagnostics as the Pecan
launcher. RSS/PSS/cgroup boundaries and the 50-ms requested sampling interval
are unchanged. Per-cell execution and verification limits are each 600 seconds,
with a 1,350-second outer cap, so the pair's combined outer cap is 45 minutes
plus setup/collection. An otherwise idle VM may finish in minutes; this has
not been measured. Precheck requires 4 GiB VM and 2 GiB host free.

The preparation gate tested orchestration and the two exact dry commands only.
No Grenada remote cell was launched during preparation. Results cannot be
called passed, faster, or lower-memory until the actual receipts are reviewed.
