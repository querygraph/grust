# D2 native05: executed checkpoint hash-layout control

Source only; no native engine, fixture generation, build, or process probe was run by the author. Native04 and its failed main attempt remain unchanged.

This separate profile uses the already qualified optimized native9f binary, its zero-extension Python3.12.6 client, and the existing signed/nonmonotonic4096-vertex fixture. The only checkpoint preparation is `repartition(P,key).checkpoint()`, without a sort or generated monotonic IDs. Fresh server configuration sets `SAIL_OPTIMIZER__PREFER_HASH_JOIN=false`; runtime sorts are allowed. This tests generic RemoteCheckpoint's recorded hash declaration, not the historical Nutmeg17 sorted-scan extension API.

## Storage and bounds

Native04's main failed when its300-second helper alarm interrupted repeated serialization of a growing114MB action history. Native05 writes each full returned action answer/schema once to `actions/<name>.json`; the small receipt retains its SHA/bytes/path and explicit retention time. The outside oracle resolves/rechecks every file and exact file inventory, requiring all seven full-answer actions per repetition. System execution metadata is collected once after all measured actions and filtered to actual workload job IDs. It remains outside action clocks. RSS history remains in the small receipt; observed RSS/footprint are per-process samples, not deduplicated physical memory or OS peaks.

The declared600-second worker deadline covers the complete183-action helper for20 repetitions, including setup, schema resolution, raw retention and post-action metadata. This is separate from `collect()`/write action spans. A120-second outside-oracle deadline and14400-second serial-owner deadline remain bounded. The new storage design is the correction; an increased deadline alone is not used to replace it.

## Required actual qualification

Every round must have one executed SortMergeJoin on a worker stage with exactlyP partitions and actual tasks on both registered workers. Expected hash exchanges strictly below that join are path/path2, checkpoint/path1, checkpoint/checkpoint0. HashJoin, collected/broadcast join inputs, extra/missing join exchanges or task evidence fail. Aggregate repartitions above the join are retained separately and do not count as join-input rehash. Runtime SortExec occurrences are reported. No hash reuse claim is made before this actual-plan predicate passes.

Full signed integer answers, all20 repetitions, source/helper/client/input identities, waited normal shutdown, two worker identities and complete owned-group absence remain required. Forced cleanup cannot pass. Pools remain10GiB per process, driver plus two workers,16 software threads each, P/2 task slots per worker; no native CPU/32GiB OS cap is claimed.

## Root commands

Use the actual admitted client at `/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python`.

Generate only the P4 three-repetition smoke first:

```sh
/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python -B /Volumes/Apo/graph-tests/results/sem-completion-20261003/D2-native05/support/prepare_plans.py --kind d2 --count 1 --partitions 4 --repetitions 3 --timeout-seconds 600 --fixture /Users/alexy/src/grust-benchmark-data/sem-completion-20261003/c2-d2-fixture01 --output /Volumes/Apo/graph-tests/results/sem-completion-20261003/D2-native05/d2-smoke01 --run-root /Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/d2-v05-smoke01
```

Owner bootstrap (root retains the actual waited launcher/owner exit):

```sh
/Volumes/Apo/graph-tests/results/sem-review-20261001/native-optimized-build01/venv/bin/python -I -B -c "import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')" /Volumes/Apo/graph-tests/results/sem-completion-20261003/D2-native05/support /Volumes/Apo/graph-tests/results/sem-completion-20261003/D2-native05/support/run_probes.py --config /Volumes/Apo/graph-tests/results/sem-completion-20261003/D2-native05/d2-smoke01/config.json
```

After actual smoke qualification, prepare fresh main roots with `--count 1 --partitions 4 16 32 --repetitions 20 --timeout-seconds 600`. This means three fresh servers,20 repetitions per partition count; not20 fresh servers each running20 repetitions. Both shared locks must be absent. Root owns all execution and failed-lock review. No retries or reused IDs.

## Source gates

`source-gate02.json` retains repository Ruff, strict mypy14files, and five independent pure executed-plan parser controls. These are source gates, not engine qualification. All source/helper bytes are frozen in `freeze01.json` and the source-only archive.
