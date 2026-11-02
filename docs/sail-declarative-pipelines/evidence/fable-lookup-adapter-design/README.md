# C4: bounded Spark 4.2.1 column-lookup adapter review

Status: design scope supported by pinned Spark source, exact Scala bytecode, and
the previously retained direct-helper oracle. This is **not a parity verdict**,
an implementation, or proof of public CDC reachability. No repository files were
edited and no JVM/Sail build or new Spark execution was performed for this review.

Recommendation: keep the reusable grust-columns resolver contract
`Fn(&str) -> Option<usize>`. Implement Spark's name-to-index policy in a private
Sail adapter. Rejecting distinct spellings that lowercase to the same name is
not the final parity policy. The pinned behavior appears reproducible without a
Scala dependency or a general persistent-map implementation.

## Provenance and inspected commands

- Spark Git object: `617618396087429b5627a86ce933bb0f5d6645cb` in
  `/Users/alexy/src/spark-sdp-4.2.1`.
- Exact inspected jar:
  `/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark/jars/scala-library-2.13.18.jar`.
- Jar SHA-256:
  `4e85d96ff7bc7dc627985523c3541b9917aaa08e956391380c42db21a2c4e5a0`.
- Bytecode tool:
  `/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/bin/javap`.
- Existing oracle used Oracle JDK `17.0.8+9-LTS-211`, PySpark `4.2.1`, and
  Spark jar build revision exactly equal to the Git object above. These are
  recorded in the existing oracle receipt; they are not new runtime observations.
- Existing packet:
  `/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/fable-column-oracles`.
  In particular, `jvm/receipt.json`, `jvm/classpath-jars.json`,
  `jvm/spark-build-properties.json`, `jvm/results.json`, and the `rust/` packet.
- The only local Scala source jar located was version **2.13.12**, at
  `/Users/alexy/Library/Caches/Coursier/v1/https/repo1.maven.org/maven2/org/scala-lang/scala-library/2.13.12/scala-library-2.13.12-sources.jar`.
  It was used for orientation only. Claims below about 2.13.18 use its actual
  class bytecode, not the older source jar.

Exact inspection command form (invoked through Python subprocess argument
arrays, once per class below; selected methods printed for review):

```sh
/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/bin/javap -c -p \
  -classpath /Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages/pyspark/jars/scala-library-2.13.18.jar \
  'scala.collection.immutable.MapBuilderImpl'
```

The last argument was replaced with each relevant class in this table. Dollar
signs must remain quoted when reproducing these commands in a shell.

| Exact class (under `scala.`) | Inspected mechanism |
| --- | --- |
| `collection.immutable.MapBuilderImpl` | `addOne(K,V)`, `result`: switch at fifth distinct exact key |
| `collection.immutable.Map$Map1` through `Map$Map4` | `updated`, `iterator`; Map4 `buildTo` |
| `collection.immutable.Map$Map2$Map2Iterator`, `Map$Map3$Map3Iterator`, `Map$Map4$Map4Iterator` | `next`: stored key1, key2, etc. |
| `collection.immutable.Map$Map2$$anon$1`, `Map$Map3$$anon$4`, `Map$Map4$$anon$7` | Iterator subclass identities |
| `collection.immutable.Map`, `collection.immutable.AbstractMap`, `collection.immutable.Map$` | `toMap`, `from`: existing small maps and HashMap retained |
| `collection.MapOps`, `collection.StrictOptimizedMapOps`, `collection.StrictOptimizedIterableOps` | Map/view or builder traversal paths |
| `collection.immutable.HashMap` | `map` bridge, `iterator` |
| `collection.immutable.ChampBaseIterator` | `hasNext`, `searchNextValueNode`, `pushNode`: payload then child traversal |
| `collection.immutable.BitmapIndexedMapNode` | `getPayload`, `getNode`, bitmap indices, `mergeTwoKeyValPairs` |
| `collection.immutable.HashMapBuilder` | `addOne`, bitmap/collision-node update paths |
| `runtime.Statics` | `anyHash`: String uses `hashCode()` |
| `collection.Hashing$` | `improve(int)` |

Source was inspected with `git show` against the fixed object, for example:

```sh
git -C /Users/alexy/src/spark-sdp-4.2.1 show \
  617618396087429b5627a86ce933bb0f5d6645cb:sql/api/src/main/scala/org/apache/spark/sql/types/StructType.scala
```

The jar digest was computed with Python `hashlib.sha256(Path(jar).read_bytes())`.
Bytecode was inspected in memory; no disassembly archive or compiled artifact is
being offered as new runtime evidence.

## Source and bytecode facts

1. `sql/api/src/main/scala/org/apache/spark/sql/types/StructType.scala:122–124`
   builds `nameToIndex` with `SparkCollectionUtils.toMapWithIndex(fieldNames)`,
   then passes `nameToIndex.toMap` to `CaseInsensitiveMap`. Lookup methods at
   lines 315–320 use those maps.
2. `common/utils/src/main/scala/org/apache/spark/util/SparkCollectionUtils.scala:28–36`
   feeds `(name, index)` pairs to an immutable Map builder in schema order.
   Exact duplicates overwrite the value. They retain the original key position
   in a small map and a hash-collision leaf; they do not add another distinct key.
3. `sql/api/src/main/scala/org/apache/spark/sql/catalyst/util/CaseInsensitiveMap.scala:33–35`
   maps the original map's entries to `name.toLowerCase(Locale.ROOT)` and applies
   the same transformation to the lookup request. When transformed names collide,
   the last entry visited by this map operation supplies the value.
4. `MapBuilderImpl` retains small Map1–Map4 representations through four
   **distinct exact spellings**, regardless of raw schema length. The fifth new
   spelling creates a HashMapBuilder, inserts Map4's existing four pairs in their
   stored order, then inserts the new pair. `immutable.Map.toMap`/`Map$.from`
   retain these existing representations rather than rebuilding in a new order.
5. Small-map iteration follows first distinct insertion order. HashMap iteration
   visits all direct payloads of a CHAMP node in ascending bitmap bucket order,
   then visits child nodes in ascending bucket order, depth-first. A child emits
   its own direct payloads before its descendants. This is not a simple global
   numerical sort of hashes.
6. String hashes are Java String hashes (UTF-16 units, wrapping 32-bit arithmetic),
   followed by Scala's `Hashing.improve`. They are not MurmurHash3 string hashes.
   The exact bytecode implements:

   ```text
   h = hashCode + ~(hashCode << 9)
   h = h XOR (h >>> 14)
   h = h + (h << 4)
   h = h XOR (h >>> 10)
   ```

   Every arithmetic operation wraps at 32 bits; `>>>` is unsigned shift.
7. `BitmapIndexedMapNode.mergeTwoKeyValPairs` creates a collision node after
   exhausting the 32 hash bits, initially with existing pair then new pair.
   HashMapBuilder collision-node updates append a new exact name to its Vector;
   an existing exact name updates its original Vector position. Full-hash
   collision ordering is therefore first distinct insertion order in this
   insertion-only construction. This is bytecode evidence, not a fresh runtime
   collision probe.
8. HashMap's map operation consumes its iterator into a fresh map builder in
   that order. The second map's eventual iteration order does not affect a
   subsequent `get`; only the last assignment to each lowercased key matters.

## Minimal adapter outline (design inference)

Enumerate fields once. Keep one record per exact spelling, in first insertion
order, updating its stored index whenever the spelling repeats. Exact lookup
returns that last schema index.

For insensitive lookup, reconstruct the original map's traversal. Up to four
distinct spellings, use the retained insertion order. Above four, compute each
record's improved Java hash and use a bounded recursive partition:

```text
visit(records, shift):
    if shift >= 32:
        emit records in retained first insertion order
        return
    stable-group records by ((improved_hash >>> shift) & 31)
    emit singleton groups in ascending bucket order
    visit each nonsingleton group in ascending bucket order, shift + 5
```

The hash is 32 bits, so recursion is bounded. The last partition reads bits
30–31; the `shift >= 32` check must occur before shifting. A Rust implementation
must not accidentally adopt Java's masked shift count when reaching the leaf.

Use the **entire distinct-name set**, not only names in a lowercase collision
group: unrelated names can turn a direct payload into a subtree and change
iteration order. Retained insertion order is essential at true hash-collision
leaves. No deletions, merges, arbitrary key types, public Scala-map API, or
persistent structural sharing are required by this source construction.

Visit that order and assign `ROOT_lower(name) -> stored_last_index` to an ordinary
Rust lookup map. Transform the requested name with the same ROOT helper. The
ordinary map's own iteration order is immaterial. Keep Java/Scala policy in Sail;
grust-columns only needs to invoke the supplied resolver and preserve its
selection/missing-name bookkeeping.

The ROOT helper remains its own compatibility obligation. Rust `str::to_lowercase`
is not automatically equivalent to this pinned JDK; the existing Unicode oracle
packet records differences. Use UTF-16 units for hashing supplementary Unicode
characters. Null names and unpaired Java surrogates are outside the examined Rust
string domain and need an explicit input-domain assessment if exposed by a public
route.

## Evidence strength and bounded next work

An in-memory Python replay of this traversal hypothesis compared its results
against all **23 retained StructType lookup records** and found zero mismatches.
All 23 field-name sets are ASCII; Python lowercasing was used only for that ASCII
replay. This is a small refutation check against old evidence, not a new JVM oracle,
a Rust implementation test, or Unicode validation.

The replay is now retained as `/tmp/sail-sdp-scala-lookup-replay.py`, with its full
JSON result and receipt at `/tmp/sail-sdp-scala-lookup-replay.json`. The receipt
records the input and script SHA-256, interpreter version, command, all 23 case
results, and zero mismatches across 46 exact/insensitive index comparisons. It
asserts the ASCII-only boundary rather than silently applying Python Unicode
lowercasing to future non-ASCII fixtures.

The existing oracle already disproves generic first/last matching-schema policies:

| Fields | Insensitive lookup `a` |
| --- | --- |
| `[a, A, a]` | index 1, while exact `a` is index 2 |
| `[a, A, b, c]` | index 1 |
| `[a, A, b, c, d]` | index 0 |
| `[b, c, d, a, A]` | index 3 |

Before claiming the adapter faithful, retain a direct JVM oracle and compare Rust
results for the following focused cases:

- Four-to-five distinct-key transition; raw length above four with only four
  unique spellings; duplicate updates before and after the transition.
- Shared low-five-bit hash buckets, deeper shared prefixes, and unrelated names
  that alter direct-payload versus subtree placement.
- True full Java hash collisions (for example `Aa` and `BB`), case variants,
  permutations, repeated exact updates, and enough additional distinct names to
  force the HashMap representation. Existing 23 cases do not establish this path.
- Empty names, supplementary Unicode names, and the retained JDK ROOT mismatch
  examples. Test hashing and lowercasing separately so one does not mask the other.
- Deterministic generated schemas/permutations, plus include/exclude selection
  results using the same resolver. A kernel-only resolver test is not an adapter test.

The full-hash collision leaf policy is source-supported; its proposed compact
reconstruction still needs implementation review and oracle coverage. No estimate
of final code size or assertion of complete parity is warranted yet.

## CDC reachability is a separate open boundary

`sql/pipelines/src/main/scala/org/apache/spark/sql/pipelines/autocdc/ChangeArgs.scala:99–120`
calls these exact StructType helpers, with no local uniqueness precondition.
`graph/Flow.scala:250–301` constructs AutoCdcMergeFlow, applies ColumnSelection to
`df.schema` at lines 259–265, checks retained keys, then resolves sequencing at
273–274. Its constructor contains no explicit duplicate-name uniqueness check.
`graph/FlowAnalysis.scala:110–140` and `216–255` resolve/load inputs; no such check
was observed there. A bounded search of `sql/pipelines` for
`checkColumnNameDuplication`, `duplicateColumn`, and
`checkSchemaColumnNameDuplication` found no matching guard. This is not an
exhaustive proof about global analysis, providers, or table registration.

The direct StructType oracle proves helper behavior only. To establish a relevant
public CDC route, keep keys and sequence names unique and place collisions only
in payload columns, then observe whether flow analysis reaches selection or an
upstream provider/analyzer rejects the schema first. Probe a valid streaming or
derived-input route; storage schema restrictions alone do not prove all flow
results unique. A directly constructed AutoCdcMergeFlow fixture proves constructor
reachability, not necessarily public Connect-definition reachability.

A simpler policy may rely on uniqueness only after demonstrating the precondition
for every accepted relevant input route and preserving Spark's rejection phase and
error behavior. Until then, a Sail collision error is a deliberate divergence,
not a parity implementation. The scoped adapter investigation can proceed without
settling that broader reachability question first.
