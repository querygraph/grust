# Grust

## Terminology

- LPG -- Labeled Property Graph
- VPG -- Vertex Property Group
- EPG -- Edges Property Group
- Backend -- Sail, Turso and friends

## What is it?

- an LPG mapping that keeps the graph' schema as the form of the graph of VPG with it's known schemas (types) connected by EPG (with known types as well); should be more than enought to lower any query to backend' SQL dialect
- collections of kernels that take CSR in as arrow, return arrow RecordBatch out with row ordered as input CSR indices --- this part should know literally nothing about how CSR was build. Easy for engine-agnostic microbenchmarks, easy to reuse
- an optional "io" module that implements `gar` and `icebug-disk` support via parsing metadata (YAMLs or schema.cypher) and feeding to the backend what it should know: adresses of parquet files to read;

## Why is it needed?

- unified ISO-GQL / Cypher queries interface: grust parse the query to AST, resolve against the knwon LPG, split the query to valid (along the known LPG graph) paths, mark common relations, optionaly re-order joins based on the known graph statistics (that backend can provide but can not); think about it as a "Calcite for ISO-GQL / Cypher over columnar data"
- collections of in-process kernels that backends can use

## What grust is not?

- grust is not a user-facing library: as end users never seen, for example, Apache Calcite, they should never see grust
- backends should implement the suport based on known optimizations and preferntials (or we can vibecode some)

# Sail

## Graphs on relations paths

This is what Spark GraphFrames do today and this is why people are still using it: when you do entity resolution over few billions of pairse where scoring function told "looks the same" there is almost no other tools except GraphFrames; when ppl prepare ML-features for feeding downstream models, there is no other tool (that does not require own infra like GraphScope) that can handle it.

**This path should always prefer scalability over wall-time on small graphs**

Existing Pecan is a perfect starting point for it; the rule is "nothing of the order of O(|V|) is collected to driver"

## Graphs as local projections

This is where we should rethink the grust-integration from scratch: if we keep in grust only kernels, it simplify things. Either local-projection keeps the mapping from original id to dense ids or Sail feeds them: needs to be measured at scale: the logic is sail cluster has much more compute than local node as well keeping the mapping on local node is an additional memory pressure (especially if the origin ids were strings): maybe we should consider dense-id and mapping as Sail tables (parquet? checkpointed tables?) instead and then separation of responsibilities is clear: Sail use grust as it is supposed to be used (feed CSR into it).

CSR can give a huge speedup but memory become a bottleneck very fast. If we can move mapping and sort away from local kernel for me it is better than have a speedup on small graphs. **This is a tradeoff**

The logic of unified memory is already there and can be reused. But better to write from scratch to keep a clear border between sail and grust (preferable is "grust knowns nothing about sail").

# What I want?

I want to do it in the right way. Code is cheap, LLM-generating is cheap. Design matters. Contracts matters. Boundaries matters. We need to learn from mistakes: one decision about grust layout leaded to a sequence of workarounds later, bad results, long investigation. So, design is first: who owns what, what is collected where, memory / perf complexity estimations everywhere. When we have a claer picture, generating/writing the code is machinery. So, let's try to rethink it.
