# Graph Nuts handoff to Fable

## Current position

The active Morrobay campaign is already running against a defined artifact
set. Let that campaign finish before changing code, images, memory limits or
benchmark configuration. Its results are useful only if the campaign remains
internally comparable.

The `sail-large-graphs` checkout has been caught up to the remote branch:

- repository: `querygraph/sail`
- branch: `work/extensions-traversal-bench`
- remote tip: `b87fb27ac`
- local checkout: `/Users/alexy/src/sail-large-graphs`

The pre-catchup dirty worktree is preserved as:

```text
stash@{0}: preserve pre-catchup sail-large-graphs worktree 2026-09-28
```

Do not drop that stash until the current run’s inputs and any locally unique
host edits have been audited.

The canonical extension POC remains:

```text
/Users/alexy/src/sail-extensions-poc
branch: work/extensions-datafusion-graphs
commit: c51286326
```

The two documents intentionally left untracked for the next owner are:

- `grust/docs/SCALING-NUTS.md`
- `grust/docs/proposals/pyspark_graph_algorithms.md`

## First action: finish the current run

1. Do not rebuild, rebase, alter the container, or change the memory envelope
   while the Morrobay run is active.
2. Let every planned cell reach a terminal outcome.
3. Preserve passes, mismatches, refusals, unavailable samples, timeouts and
   errors. Do not replace a failed cell with a rerun in the same campaign.
4. Record the exact command, host, container limits, `ulimit -n`, source
   commits, image digest and output directory.
5. Run the existing evidence verifier and retain its manifest and audit logs.

This closes the current campaign as a coherent historical measurement.

## Second action: rebuild the next baseline

After the run is archived, create a clean build from the caught-up remote tip.
Do not mix artifacts from the older checkout into the new campaign.

1. Build Sail and all extension wheels from
   `work/extensions-traversal-bench` at `b87fb27ac`.
2. Build the native Nutmeg artifacts from their pinned source revision.
3. Record the Grust and controller revisions used by the build.
4. Run unit tests, extension tests, protocol tests and the existing local and
   worker functional tutorials.
5. Run the two-host functional check on Capitola and Morrobay before timing.
6. Verify that output vectors, WCC certificates and cleanup are correct.

If any gate fails, fix or qualify the failure before starting a new timing
campaign. Do not silently substitute an older wheel or stale build directory.

## Third action: implement Fable S0 before more performance runs

The next campaign begins with measurement separation, not algorithm tuning.
For each path and input, record separately:

- input loading and graph staging wall time;
- sort workspace: permutation, sort keys and sorted copy;
- retained staged batches;
- native projection and CSR allocations;
- transpose allocation, when present;
- staging peak PSS and RSS;
- temporary-file count, bytes written and descriptor high-water mark;
- kernel wall time, iteration count and certificate time;
- active vertices and active edges by PageRank/frontier round;
- kernel peak PSS and final output-write time.

Set and record the file-descriptor limit. For large runs, start with
`ulimit -n 30000` unless the harness documents a different qualified value.

The first S0 fixtures are:

- cit-Patents, approximately 3.7 M vertices and 16.5 M edges;
- Graph500-24 M-class, approximately 8.8 M vertices and 260 M edges;
- the existing Graph Kernels hub/uniform inputs for continuity.

Expected staging refusals remain valid outcomes. A Banda refusal before the
kernel starts must be reported as a staging admission failure, never as a
PageRank kernel failure.

## Fourth action: run Argentea only after the rebuilt gates

Argentea is on the caught-up `sail-large-graphs` remote tip. Run it after the
clean rebuild and functional checks, with the following boundaries:

- validate reference and residual PageRank first;
- validate BFS reference, frontier and direction-switching modes;
- validate WCC and weighted SSSP process-cluster paths;
- repeat the physical two-host functional checks on Capitola and Morrobay;
- keep bounded phase limits explicit;
- record worker participation, placement, retries, cancellation and cleanup;
- do not call functional qualification a performance result.

Argentea currently proves bounded distributed execution, not large-graph
throughput or unlimited continuation. Its next scaling question is whether a
run can continue across jobs without rebuilding worker-local state. That is
Fable S6 work and should be measured separately from the initial functional
qualification.

## Campaign separation

Keep the completed Morrobay run and the rebuilt Argentea campaign in separate
directories and manifests. Each publication row must name:

- repository and branch;
- exact commit and image digest;
- host and guest configuration;
- memory, disk, CPU and descriptor limits;
- command and timer boundary;
- every retained outcome.

Only after the rebuilt campaign passes its gates should its summaries be
promoted to Graph Nuts or used to update `docs/GRAPH-NUTS.md`.

## References

- `grust/docs/FABLE-ON-ASTRA.md` — ordered S0–S6 scaling plan.
- `grust/docs/SCALING-NUTS.md` — staging diagnosis.
- `grust/docs/GRAPH-NUTS.md` — repository, branch, document and evidence map.
- `sail-large-graphs/docs/development/extensions/argentea-validation/README.md` —
  Argentea evidence index.
- `sail-large-graphs/docs/development/extensions/pecan-nutmeg-large-benchmark.md` —
  Morrobay campaign protocol and retained results.
