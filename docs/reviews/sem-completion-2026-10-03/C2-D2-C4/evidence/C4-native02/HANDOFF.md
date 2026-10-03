# Current native C4 full-answer control

Source only. Root alone runs the prepared fresh-server pair. Source01 does not replace the historical
standalone original/compact struct-MIN controller or its allocation predicates.

## First semantic pair

Use the already admitted zero-extension native Python and existing bounded fixture01:

```sh
/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python -B /Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-native02/support/prepare_plans.py --kind c4 --count 1 --partitions 4 --fixture /Users/alexy/src/grust-benchmark-data/sem-completion-20261003/c2-d2-fixture01 --output /Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-native02/pair02 --run-root /Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/c4-pair02
```

This creates two fresh-server cells, tuple-MIN then min_by, each with its own first and repeated data
action. Later repetitions reverse pair order. Initial qualification is a bounded semantic/control pair,
not a statistically qualified timing contrast. Both use the same struct: DOUBLE(payload%7),
BIGINT(payload%3), BIGINT(dst), grouped by signed BIGINT src. MIN(struct) is compared with
min_by(struct,struct), preserving the same complete total ordering and all three raw output fields.
All ordering keys must be unique within each group; the independent oracle rejects duplicate total keys.
The prepared input has4096 signed groups and32768 rows. There is no million-group allocation extrapolation.

Run the owner with the isolated sibling bootstrap:

```sh
/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python -I -B -c "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')" /Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-native02/support /Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-native02/support/run_probes.py --config /Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-native02/pair02/config.json
```

Root must retain the actual owner wait/exit, then copy and hash all raw metadata/logs/answers before
final qualification. Failures retain owned locks for root review, with no stale-lock cleanup or retry.

## Required observed evidence and limits

The oracle requires complete exact raw src/BIGINT, distance/DOUBLE, hops/BIGINT, parent/BIGINT rows;
no adapters/casts occur after aggregation. It independently computes Python tuple minima over the
original finite integer-derived payload. Missing/duplicate groups, nonfinite values, wrong types,
wrong signed high bits and wrong fields fail. Both query forms require executed Partial and Final
aggregate plans, actual P-way exchange, and actual task attempts on both workers. A SinglePartitioned
plan is retained as unqualified, without weakening this requirement.

Lifecycle/source/client/binary guards are copied from reviewed C2 source03. Both registrations and
exec identities precede the first data action, with a separate recorded readiness interval. Worker
slots=P/2 each, process topology driver+two workers,16 software threads and10GiB greedy pools each;
there is no native OS16CPU/32GiB cap. Cold means first dataset action after readiness, with no OS-cache claim.
System evidence SQL runs after both timed actions. Sampled per-PID RSS/physical footprint is neither
PSS nor allocator state size nor an OS lifetime maximum. Standalone CountedSystem requested-allocation
qualification remains separate from Sail MiMalloc/RSS and is not promoted by this control.

The exact native9f source selects CompactStructMin for flat (Float64,Int64,Int64) and explicitly
serializes StructMin to workers. This is source inference until the actual factory/size gate runs;
compact_group_accumulator_observed remains false. Current min_by simplifies to ordered LAST_VALUE
with a nonnull ordering filter (max_min_by.rs), while its unsimplified fallback holds two ScalarValues.
The logs retain whether LAST_VALUE is named; absence is not relabeled as an observed implementation.
No claim of an O(rows) array or a measured per-group native state follows from a generic plan name.
No current method is labelled original generic struct MIN.

## Explicit metadata-only session creation

The prior readiness attempt preserved its failure: Connect SparkSession.create() created only a lazy
client, so no session or initial workers existed during its readiness wait. Source now explicitly
calls SparkSession.version before readiness. In the exact admitted client, that property sends
AnalyzePlan(spark_version); native9f server.rs:167–179 gets/creates the actual SessionContext,
and session_manager/actor/handler.rs:174–177 waits driver.activate() before AnalyzePlan returns.
The driver activation requests initial workers. AnalyzeSparkVersion returns version metadata without
JobRunner.execute or a data job. The receipt records this metadata bootstrap duration/version/log
offsets separately, then worker readiness separately. The unchanged job-log guard requires no
executed job before readiness; no SELECT1, data warmup, or fixture count was added. Cold remains the
first fixture data action after session metadata bootstrap and worker readiness, without an OS-cache
claim. Prior sources/failure remain unchanged. Root alone runs the new fresh attempt.
