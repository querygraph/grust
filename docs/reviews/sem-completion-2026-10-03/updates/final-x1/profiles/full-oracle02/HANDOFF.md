# Full physical X1 BFS certificate

Source preparation only. Root owns all engine, full input/output hashing and oracle invocations. Revision 02 preserves frozen 01 and corrects original input schema admission. Its author read one original Parquet footer, recorded in `original-footer01.json`, without reading batches, hashing its payload or changing any original file. No native engine, build or large oracle was run.

## Interface

`bfs_models.Config` is defined by `config-schema.json`. CLI:

```text
ORACLE_PY -B ABSOLUTE_HELPER_DIRECTORY/bfs_oracle.py --config ABSOLUTE_CONFIG
```

For isolated Python, add this exact frozen helper directory before `runpy.run_path`; direct `-I` script invocation removes sibling import paths. The oracle requires NumPy, PyArrow and Pydantic; it never imports the engine, extension wheel or Spark. Root supplies exact client/helper pins and a fresh output directory separate from result/source. All four helper filenames and actual module origins are checked.

Input vertices and edges are lists of regular-file `Pin` records. The vertex schema is exactly `id:Int64`. `edge_schema_profile=endpoints2` is the explicit/default tiny-input profile: exactly paired `src,dst:Int64` or declared `source,target:Int64`. `edge_schema_profile=original_weight3` requires exactly `src:Int64,dst:Int64,weight:Float64`. The original generated scale24 dataset must select this latter profile; its unchanged three-field files are never rewritten or regenerated. Missing/extra columns and wrong physical types fail admission. BFS deliberately ignores the weight values: the certificate streams all original endpoint rows, while recording the complete physical input schema, full original-file Pin, endpoint columns read, and deliberately unused `weight` column in `input_edge_physical_files`. Selecting endpoint columns for the reader does not project or rewrite the original files; full-file hashes still cover the retained weight bytes.

Original vertices must be unique/non-null; endpoints must name them. This independent validation is outside the algorithm timer. Actual footer and streamed row counts must match the configured V/E. No original endpoint row is dropped or sampled. A chunked full comparison against `0..V−1` admits the identity-domain direct-index path with explicit signed bounds checks, recorded as `identity_domain_verified`; arbitrary signed domains keep sorted `searchsorted` lookup. The fast path is observed from the original full domain, never selected from a dataset name.

Result `ResultSet` binds a directory and the complete relative regular-file byte/SHA inventory, including sidecars. Symlinks and extra/missing files are refused. All `.parquet` members are scanned. Default `native13` is exactly the ordered physical Int64 fields:

```text
id distance hops parent owner worker_id pid adjacency_id
incoming_adjacency_id phase levels reached converged
```

Distance/hops/parent preserve physical nulls; every other field must be present. No float ID conversion or null-to-infinity adapter is used. Every row repeats the same observed terminal counters; phase must be K+1, converged 1, reached equal the full computed reached count. Owner must be signed `id % P`; each observed owner keeps one worker/PID/outgoing-adjacency identity and reference incoming-adjacency ID 0. These are physical checks, not proof of actual process closure or worker scheduling.

The explicit `projected4` profile accepts only `id,distance,hops,parent` plus a pinned `ProjectedTerminal` actual-materialized attribute receipt bound to the exact result inventory, source, cap, partitions and an admitted producer evidence pin. Its terminal `converged` is the recorded integer diagnostic 1, not a guessed flag. Native13 is the intended profile and supplies repeated counters in raw data.

`source_contract` requires exact clean detached Sail `4b88c8fb4504ab1d2a896c9e49e4a09df4905bbb` and root-supplied tree/source pins before/after. Input, client, helper, producer metadata, configuration and complete raw result hashes are checked before/after. No untyped producer receipt is interpreted as a per-call wait. Whole producer/process/build/ABI/history qualification remains root-owned and explicitly false here.

## Proof and outcomes

All V physical rows must map uniquely and exactly to the sorted original signed-ID domain. Source distance/hops are 0 and parent equals itself; no other reached vertex has distance 0. Reached distance is a nonnegative integer below V and equals hops. All three unreachable fields are null.

For every original edge `(u,v)`, the oracle considers both directions without duplicating the whole edge set. A reached endpoint requires the other to be reached, and reached levels differ by at most 1. It uses `np.minimum.at` to retain the minimum signed original neighbor ID at level `d(v)-1`. Every reached non-source row must name that predecessor. A separate presence bitmap distinguishes a legitimate Int64MAX predecessor from an absent candidate.

Each parent path strictly decreases its integer level and must terminate at the unique source-zero row, proving a source path of length d. All-edge inequalities along any source path prove d is at most that path's length; reachability closure rules out omitted reachable vertices. These upper/lower bounds prove exact shortest distances and exact minimum numeric predecessor parents. Duplicates and loops do not alter the certificate. This is a full-edge mathematical certificate, not a queue/CSR replay.

The final empty-expansion proof requires reported `levels = max_distance + 1 <= K`. Full raw phase/counter agreement is checked separately. An isolate source needs levels 1. Cap 0 cannot receive a positive full certificate. A cap failure/error with no output is retained and qualified by the separate owner/failure oracle, not this positive full-output checker.

Positive `Receipt.outcome` is `passed_full_undirected_BFS_certificate`; `full_domain_passed`, `all_original_edges_examined`, `parent_paths_and_minimum_parent_passed`, `all_edge_lower_bound_and_reachability_passed`, `terminal_empty_expansion_cap_passed`, `full_physical_certificate_passed` and `own_identity_closure_passed` must all be true, errors empty and every `failures` counter zero. Wrong results, missing rows and inconsistent caps remain `mismatch`, `partial_output` and `cap_unqualified`. Invalid source/input/schema/identity/deadline conditions remain `error`. Failure counters can overlap predicates and are not distinct affected-row counts.

## Memory, deadlines and retention

Six retained arrays use exactly 34V bytes by `.nbytes`: sorted IDs, distances, parents and minimum parents (8V each), output seen and predecessor presence (V each). For original V=16,777,216 this is 570,425,344 bytes = 544 MiB. Hops are compared in output batches rather than held as a seventh vector. Endpoint lookup, masks, winner reduction and output duplicate handling use configured batches; no E-sized array, adjacency dictionary or full-domain advanced-index copy is requested by the helper.

`declared_batch_array_allowance_bytes=512*batch_rows` is an advisory allowance for visible batch buffers, not a proved total allocator/Arrow decoder/physical peak or OS limit. Sort implementation scratch, parquet decode buffers, metadata, Python/native runtime and other headroom remain outside that array count; root must preserve actual RSS observations. `use_threads=False` and `pre_buffer=False` avoid explicit read parallelism/prefetch but are not memory caps.

Work and immutable-final-audit have separate cooperative monotonic deadlines. Source Git requests also have bounded subprocess waits. Root's waited owner must bound the whole work+audit process; a batch codec call or filesystem stall can exceed a cooperative check window. Hashing uses 4 MiB chunks. Progress/final receipts fsync file contents then rename; no parent-directory/power-loss durability claim. Inputs/raw output are never deleted or rewritten.

## Controls and scope

Eighteen small controls include the fifteen unchanged mathematical/physical controls plus the retained three-field input certificate, missing/extra/wrong-type profile rejection, and the original dataset's explicit weight-profile requirement. The original controls cover verified identity-domain direct lookup and bad signed endpoints, complete signed/highbit domains, duplicate edges and loops, an isolate, reversed stored edge orientation, wrong hops/distances, a valid but nonminimum signed predecessor, mixed nulls, omitted/fabricated reachability, cross-batch duplicate/unknown/missing rows, source/zero invariants, the empty expansion/cap, a legitimate Int64MAX predecessor with Int64MIN isolate, an unknown original endpoint, physical Float64 rejection, precise Int64/null conversion and repeated native diagnostics/owner identity.

`tiny-fixture.json` is a separately recorded 13-vertex/14-edge source-only fixture with depth 7, so terminal levels 8 crosses the K=8 boundary. Root can write its typed Parquet input and run it. This file is not an actual engine receipt. The original scale24 profile is explicitly V=16,777,216, E=268,435,456, source=13,507,776, undirected reference, K=8. It is the original generated graph and is distinct from the official Graphalytics graph500-24 dataset. Missing historical scratch files and changed historical source are not repaired or relabelled by this oracle.
