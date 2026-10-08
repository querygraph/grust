# Exact-source Cypher semantics and SNB evidence

Source: `6638d9b4b4094f28593439e26f94a75e70264c79`.

- [Source gate](source-gate.json) and [full gate log](native-gate.log).
- [Relational results](relational/receipt.json) and [programs](relational/queries.json).
- [Iterative results](iterative/receipt.json) and [programs](iterative/queries.json).
- [Earlier Cypher frontend results](cypher/receipt.json) and [programs](cypher/queries.json).
- [New semantics results](semantics/receipt.json) and [programs](semantics/queries.json).
- [Managed memory control](memory/receipt.json).
- [SNB results, including every warmup/measured cell](snb/receipt.json), [ratios/ranges](snb/ratios.json), [programs/parameters/types/estimates](snb/queries.json), and [schema/table request](snb-request.json).
- [Eighteen refusals](refusals.json).
- [Preserved development failures](development-failures/index.json).
- [Observed GitHub states](github-states.json).

Absolute execution and compilation times are omitted from public JSON artifacts
because the host is shared. Each SNB cell retains elapsed time as a ratio to
that binding's measured resolved median, including warmups. Original raw
artifacts and their hashes are identified in the source receipt. Verbose
explain strings are replaced by hashes; generated SQL, ordered execution
steps, output types, cost estimates and rewrite traces remain reviewable.

Expected arithmetic errors, refusals and historical failures have separate
outcomes. A gate verdict covers its exact source commit only.
