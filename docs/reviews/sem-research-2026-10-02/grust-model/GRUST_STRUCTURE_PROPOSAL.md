# Grust

## LPG abstraction

This should be a graph of property groups. No execution; No connections to backends; 

### What I would like to see first?

Proposal about based traits:

- Vertex Property Group
- Edges Property Group
- Directions
- Properties
- Data Types (logical)
- Constraints

Proposal about core APIs:

- traversals: given the unresolved pattern like "(a: name)-[]-(b: name){1-5}-[knows]-()" or similar should be resolved to all the valid paths in the graph of properties; something like BFS/DFS
- find_path, is_feasibkle_from, maybe some other helpers
- accessors (get/set)
- maybe ser-de? something minimal, JSON and maybe schema.cypher

Overall should be small crate;

## Unresolved Logical Plan (or just Query)

The core idea why shoult it be a separete crate is that we can reach the Unresolved (Parsed) Query from multiple points:

- Cypher
- ISO GQL
- programmatic Gremlin-like API `g.v()...`

This should know nothing about backends. No resolution here excpet the resolution against the logical LPG structure.

Parsing must be outside of this crate!!!

### What I would like to see first?

Base traits, overall flow.

## GQL / Cypher

Two separate. The current cypher is regex based and conatains a lot of code. I would prefer parser-combinators and something like `nom`. But actually it does not matter a lot. Important is to parse the query and return the Unresolved Logical Plan from here.

### What I would like to see first?

Report about "how to parse" (parser-combinators vs antl4 vs regex vs whatever)

## Programmatic API

Extension over LPG that allows to write Gremlin-like and build the Unresolved Logical Plan progammatically. This is for library developers who want to void generating cypher/gql and want to build the query explicitly.

### What I would like to see first?

Base traits, overall flow, API proposal.

## Resolution

When we have unresolved query we need to transform it to the "analyzed":

- transform any anonymous edges / nodes to all the feasible paths inside the LPG
- lower filters to join conditions where possible
- resolve schemas (what we need to carry along the join, what should we add later)
- ...

This need to be concrete analyzed set of valid paths inside the LPG;

### What I would like to see first?

Base traits, overall flow.

## Explain

Explain, vizualize (as graph of paths in LPG)

### What I would like to see first?

API draft

## Optimization

I want to introduce the graph-statistics trait: cardinality of properties, amount of rows, min-max statistics, etc. This all should be optional! As well optimizer itself. The main ultimate goal is join reordering.

Some backend can provide statistics, some cannot.

### What I would like to see first?

Base traits, overall flow.

## Substrait

This is an open question. It would be nice to be able to generate not only SQL but substrait. Need to be researched.

### What I would like to see first?

This is an open question, so I need a reasearch.

## SQL generations and optimization rules per backend

This already exists in the grust, it just should land on the proposal.


## Kernels

This are pure CSR in, arrow out.

What I want here: **Memory Discipline Proposal**

- who allocate input buffers? who own them? lifetime?
- who allocate output buffer? who own them? lifetime?

We are crossing FFI here, so Rust is not safe anymore after this point and we must have clear discipline contract there! Follow Arrow C-Interface philosophy (there were rules about this exact case).

### What I would like to see first?

Base traits, overall flow, **memory discipline contract**
