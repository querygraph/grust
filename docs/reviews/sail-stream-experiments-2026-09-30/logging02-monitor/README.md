# Logging02 supplemental observations

Recorded 2026-09-30T20:25:40.387932+00:00.

Read-only observations of the existing `sail-stream-log02-1` cell. The root agent owns its execution, cleanup and full diagnostic collection. These observers create no container or workload, change no resource setting, and read no process arguments or environment. Only local evidence files are written.

`identity-audit.json` binds the original process capture, later same-boot PID mapping, worker startup log and all three live Sail executable hashes. The first supplemental executable capture failed because the non-login SSH PATH could not locate Lima; its original source and failure receipt are retained beside the successful explicit-PATH retry.

`observation-*.json` retain original bounded sampler/log excerpts, exact container identity, cgroup counters, boot context and observer source hash. Full process mappings occur about every five minutes. The authoritative execution evidence remains the original memory sampler and complete server log collected by the root runner. A lexical log match is not itself a runtime failure: the initial preface-close DEBUG message and SQL plan `raise_error` expressions are retained without causal claims. After SQL expressions filled the twenty-match excerpt cap in the 20:20 observation, the supplemental filter was narrowed to timestamp-prefixed log records; both earlier observer sources remain retained. Scanned byte windows, omitted gaps and truncation markers delimit what each excerpt covers.

No historical failure cause, whole-workload result, performance measurement or proof of absence of errors is supplied by these live observations.

## Observer suspension and one-shot follow-up

Recorded 2026-09-30T20:52:26.140188+00:00.

The local repeated observer was stopped at 20:42 UTC after delayed and timed-out SSH reads. Local timeout does not prove remote child termination. The later host-only process inventories found no additional surviving host Python or Lima observer beyond the pre-cell inventory and the current collector; they cannot exclude VM-side readers. No remote process or workload was signaled. Failed observations and both local stop attempts remain retained.

[Host comparison](host-memory-comparison.json) records the original pre-cell and fresh host snapshots. Used swap fell while compressor occupancy and cumulative swap counters grew substantially. These are global host observations; swap counts are not physical disk-byte measurements, and neither VM ownership nor workload causation follows from executable names.

One additional VM read was explicitly authorized after that host check and completed at 20:51:32 UTC. [Its summary](one-shot-2051-summary.json) binds the raw receipt, same-boot process identities, sampler phase, cgroup counters and exact log offsets. No repeat loop is scheduled. Process presence, sampler activity and HTTP/2 ping acknowledgements do not establish algorithm progress.
