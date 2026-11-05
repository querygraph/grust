# Decision notes: native extensions over Arrow-only C boundaries

Each note is one post for the maintainers' discussion thread. The proposal
they belong to is EXTENSIONS-ON-ARROW-C-ABI.md; the plan is REDESIGN-PLAN.md.

Terms used throughout: a **native extension** is a separately compiled
library installed as a Python package that adds functions or relations to
Sail. The **Arrow C Data Interface** is Arrow's stable C definition of
schemas, arrays and streams. A **C boundary** here is a struct of function
pointers with a private data pointer and a release function, so that neither
side owns the other's memory. **Comet** is Apache DataFusion Comet, a Spark
accelerator; **Sedona** is Apache SedonaDB, a spatial engine; both publish
such boundaries.

---

## E1. The scalar function boundary

**Context.** Our contract crosses scalar functions through `datafusion-ffi`,
which binds a library to one DataFusion major version. Sedona defined a
scalar kernel over the Arrow C Data Interface only; Comet adopted the same
structs, added a discovery symbol (`comet_c_udf_list_v1`) and a version probe
(`comet_udf_abi_version`), and reports that all of Sedona's functions import
through it with no change.

**Options.**
1. Implement Comet's boundary unchanged, including its symbol names, so a
   library built with Comet's SDK or Sedona's loads into Sail as is.
2. The same structs under Sail-named symbols, which forces every library to
   export a second pair of symbols.
3. Keep `datafusion-ffi` only.

**Recommendation.** Option 1. If the header moves to DataFusion or Arrow,
Sail follows it there; until then Comet's copy, with its probe, is the shared
one. The `datafusion-ffi` flavor stays accepted as a fallback and is dropped
when no shipped extension needs it.

**What settles it.** Your preference; P5 loads Comet's test library and
Sedona's functions through it.

---

## E2. The relation boundary

**Context.** Relations (table providers and execution plans) also cross
through `datafusion-ffi` today. Sedona's header defines table providers,
execution plans with named properties, and execution into an Arrow array
stream, with no DataFusion type; its Rust crate holds the import and export
adapters.

**Options.**
1. Adopt Sedona's structs for relations; depend on Sedona's crate for the
   adapters.
2. Adopt the structs; carry the two adapters in Sail, with attribution.
3. Keep `datafusion-ffi` for relations.

**Recommendation.** Option 1 if the dependency is acceptable to you, else
option 2; the adapters are small. Our bounded-relation dispatch keeps its
shape: children exported as C execution plans, the extension's plan imported
back.

**What settles it.** Your preference on the dependency; P6 scans a Sedona C
table provider through the dispatch.

---

## E3. What a package declares

**Context.** Today a package declares the Sail extension API version and the
DataFusion and Arrow versions it was built against, and the host refuses a
mismatch before binding.

**Options.**
1. Declare the header version of each C surface used, the Arrow C Data
   Interface version, and the Sail extension API version; drop the DataFusion
   version, since no DataFusion type crosses.
2. Keep declaring the DataFusion version as well.

**Recommendation.** Option 1. A declaration that nothing checks is a false
promise.

**What settles it.** Your preference.

---

## E4. The memory lease

**Context.** Host-funded memory crosses as a small C record (version, size,
byte quota, owner, retain and release callbacks) of Sail's own definition. It
has no Arrow or DataFusion type in it.

**Options.**
1. Keep it as is.
2. Offer it to the same shared home as the scalar header, so extension
   authors have one place to look.

**Recommendation.** Keep it now; offer it once the scalar header's home is
settled.

**What settles it.** Your preference.

---

## E5. What stays outside the contract

**Context.** The maintainers' earlier inventory lists optimizer rules,
physical planner extensions and command plugins as further extension points;
Sedona's header also defines catalog providers.

**Options.**
1. Leave all four out and say so; the contract covers functions, relations
   and memory.
2. Include catalog providers now.

**Recommendation.** Option 1. Optimizer and planner extensions need
DataFusion types by nature and deserve their own discussion; catalog providers
would have to match Sail's catalog contract, which is its own design.

**What settles it.** Your preference.
