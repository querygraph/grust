# LPG: base traits and core APIs

Wave 1 of the Grust v2 plan agreed on
[querygraph/grust #36](https://github.com/querygraph/grust/pull/36). Sem asked
for "a graph of property groups. No execution; No connections to backends",
with base traits for vertex property groups, edge property groups,
directions, properties, logical data types and constraints, and core APIs:
resolving an unresolved pattern "to all the valid paths in the graph of
properties", helpers such as `find_path` and `is_feasible_from`, accessors,
and minimal serialization. "Overall should be small crate."

The proposal is the sketch crate [`../sketch/lpg`](../sketch/lpg/src/lib.rs)
(`grust-lpg`): about 1,000 lines of source (after formatting) and seven tests, one optional dependency
(`serde`), no Arrow, and no other Grust crate. Drafted by Claude for Alexy.
`schema.cypher` is postponed, as Sem decided on the PR.

## Summary

1. **Two traits describe a group, one describes the schema:**
   `VertexGroup`, `EdgeGroup` and `Lpg`. Any catalog can implement them;
   `Schema` is the in-memory implementation with a builder.
2. **The schema is a graph:** VPGs are its nodes and EPGs its edges, each EPG
   from one source VPG to one target VPG, directed or undirected.
3. **Pattern resolution is exact and cheap.** Feasibility is a backward pass
   over (pattern position, VPG) in time linear in the schema per hop.
   Enumeration is a forward walk that never reaches a dead end, capped by
   options, and it says when a cap was hit.
4. **Sem's example works:** `(a:Person)-[]-(b:Person){1,5}-[:KNOWS]-()` on an
   LDBC-shaped schema resolves to every valid path, among them Person
   `LIKES` Post `HAS_CREATOR` Person in the first segment.
5. **Group ids are 16 bits,** so at most 65,536 groups of each kind, matching
   the `(group, dense id)` convention.

## The types

| Sem's item            | Type                                                                                                          | Notes                                                                                                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Vertex property group | trait `VertexGroup`; `VertexGroupDef`                                                                         | id (`VpgId`, 16 bits), name, labels (a set: an LPG vertex may carry several), properties, key, constraints                                                                                         |
| Edge property group   | trait `EdgeGroup`; `EdgeGroupDef`                                                                             | id (`EpgId`), name, edge type, source and target VPG, direction, properties, the edge columns holding each endpoint's key, constraints                                                             |
| Directions            | `Direction::{Directed, Undirected}` on a group; `PatternDirection::{Outgoing, Incoming, Either}` in a pattern | An undirected group is stored once and traversable both ways                                                                                                                                       |
| Properties            | `Property { name, ty, nullable }`                                                                             | A key property must be non-nullable; the builder checks                                                                                                                                            |
| Data types (logical)  | `LogicalType`                                                                                                 | Boolean, Int32, Int64, Float32, Float64, Decimal, String, Binary, Date, Timestamp, Duration, List, Struct. Mapping to Arrow, SQL or Substrait is the lowering's job, not this crate's.             |
| Constraints           | `Constraint::{Unique, Cardinality, Total}`                                                                    | A group's key is unique implicitly. `Cardinality` bounds edges per vertex (one-to-one, many-to-one). `Total`: every source vertex has an edge. These are what a resolver and an optimizer can use. |

## The core APIs

| Sem's item                                                   | API                                                                                                     | Behaviour                                                                               |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Traversals: resolve an unresolved pattern to all valid paths | `Lpg::resolve(&Pattern, &ResolveOptions) -> Resolution`                                                 | Per pattern position, the feasible groups; the list of schema paths; a `truncated` flag |
| `is_feasible_from`                                           | `Lpg::is_feasible_from(VpgId, &Pattern)`, `Lpg::is_feasible(&Pattern)`                                  | The backward pass only; no enumeration                                                  |
| `find_path`                                                  | `Lpg::find_path(from, to, max_hops) -> Option<Vec<Hop>>`                                                | Shortest path in the schema graph, either direction, any edge type                      |
| Accessors (get)                                              | trait methods: `vertex`, `edge`, `vertex_by_name`, `property`, `vertices_matching(&LabelExpr)`          |                                                                                         |
| Accessors (set)                                              | `Schema::to_builder()`, then `set_property`, `constraint`, `vertex_group`, `edge_group`, then `build()` | The schema is immutable; changes go through a builder, which revalidates                |
| Serialization                                                | feature `serde`: every type derives `Serialize` and `Deserialize`                                       | JSON through `serde_json`; `schema.cypher` postponed                                    |

### What a pattern is here

`Pattern` is a chain `node, edge, node, ..., node`. A node step has a label
expression (`:A`, `:A&B`, `:A|B`, `:!A`, or any). An edge step has an edge
type expression, a direction, and a hop range (`{1}`, `{1,5}`, `{2,}`).

This is deliberately the minimum the schema needs. The unresolved logical
plan (wave 2, its own crate) carries variables, property predicates and path
modes. It lowers each path pattern to this form to ask the schema, and keeps
its own bookkeeping beside the answer. So the LPG crate never depends on the
plan crate.

### How resolution works

Two passes over the product of pattern positions and vertex groups:

1. **Backward, feasibility.** For the last node, the feasible groups are those
   whose labels match. For each edge step, going backwards, layer `B_k` is the
   groups that reach the next node's feasible set in exactly `k` admitted
   hops, and the node's feasible set is its matching groups that are in some
   `B_k` within the step's range. An unbounded range is iterated to a fixpoint,
   which comes within `|VPG|` more layers. Cost: hops times
   `(|VPG| + |EPG|)` per edge step.
2. **Forward, enumeration.** A depth-first walk from the feasible start groups
   that takes a hop only if the layers say the rest can still be completed.
   No walk ends in a dead end, so the cost is proportional to the output.
   `max_paths` and `unbounded_limit` cap it, and `truncated` reports a cap.

The feasible sets per position are exact when the enumeration completed. When
it was truncated, the node sets come from the backward pass, which is a
superset.

### Shown by the tests

`cargo test` in `../sketch`
([`lpg/tests/resolve.rs`](../sketch/lpg/tests/resolve.rs)), on an LDBC-shaped
schema of five vertex groups and ten edge groups:

| Test                           | Pattern                                     | Result                                                                                                                                           |
| ------------------------------ | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| anonymous edge between persons | `(:Person)-[]-(:Person)`                    | only `knows`; an undirected self-loop group counts as one hop, not two                                                                           |
| anonymous target               | `(:Person)-[:LIKES]->()`                    | the target resolves to `post` and `comment`                                                                                                      |
| Sem's example                  | `(:Person)-[]-(:Person){1,5}-[:KNOWS]-()`   | every path has 1 to 5 hops in the first segment; the last node can only be `person`; `likes_post` then `post_creator` is among the two-hop paths |
| infeasible                     | `(:Tag)-[]->()`                             | rejected by the backward pass alone                                                                                                              |
| label expressions, unbounded   | `(:Message&!Post)-[:REPLY_OF]->{1,}(:Post)` | starts only at `comment`; five paths with an enumeration cap of four extra hops                                                                  |
| `find_path`                    | forum to tag                                | `container_of`, `post_tag`; none within one hop                                                                                                  |
| validation, set                |                                             | an unknown or nullable key is refused; `set_property` adds a property                                                                            |

## Open questions for Sem

1. **Multi-label vertices.** A VPG has a label set, and a pattern's label
   expression is matched against it. Is one VPG per distinct label set the
   right model, or should a vertex be able to sit in several groups?
2. **An edge type spanning several group pairs.** `LIKES` from Person to Post
   and from Person to Comment is two EPGs with the same type here, so a
   pattern on `:LIKES` resolves to both. Agreed?
3. **Keys.** A VPG's key is any non-empty list of properties of any type. The
   dense id is not in the schema; it belongs to the backend. Agreed?
4. **How much of the pattern lives here.** Property predicates are absent
   from `Pattern` on purpose (they belong to the plan). Should label
   expressions stay here, as now, so that the schema can prune by label?

## Limits

- One example schema. No large or adversarial schema was timed; the cost
  claims come from the algorithm.
- Constraints are recorded but not yet used by resolution. A cardinality
  constraint could prune or annotate paths; that belongs with the resolver
  (wave 3).
- The traits return slices, which suits an in-memory catalog. A catalog that
  loads lazily would want iterators; easy to change while it is a sketch.
