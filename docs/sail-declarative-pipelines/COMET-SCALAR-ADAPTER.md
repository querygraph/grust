# Qualify the standalone Comet scalar adapter

Native scalar functions should preserve Arrow fields and remain safe when results
outlive their query. Sail already has a standalone adapter for Comet-shaped kernels,
but it rebuilds argument fields from array types and retains library code only
through the function. This loses metadata and leaves result callbacks
without a proven code lifetime.

Keep the pinned Comet ABI v1 and require explicit admission of trusted pure immutable
producers. Reject other declared volatility before loading. The low-level API is
unsafe: numeric version checks cannot verify pointer validity, non-unwinding
callbacks, concurrency or truthful purity.

Retain library code for the process lifetime before foreign callbacks. Retain
neither session state nor kernel instances in that registry. The initial standalone
loader retains each admitted opening; package integration must bound admissions
and supply content identity. Unloading would require ownership following every
returned array and callback, a broader mechanism than this increment needs.

Admit zero or more arguments in planning; each kernel decides its actual arity.
Pass DataFusion’s actual argument fields during initialization at planning and
execution. Check argument types, counts and row lengths before execution. Compare
the execution return type and metadata with planning. DataFusion ignores the
top-level return-field name and permits safe nullability widening; preserve exact
nested fields and refuse incompatible output. The reserved constant-argument
pointer remains null as required by the pinned interface.

Qualify metadata-sensitive, sliced, empty and nested inputs, retained results,
named failures and declared-volatility refusals. Run failing controls against the
original adapter. An independently built pinned Comet SDK producer supplies a
separate interoperability check beyond the handwritten fixture.

These changes precede package registration and worker loading. Those remain
separate increments; streaming expressions still need marker isolation, and
durable pipelines still need replay identity, prepared output and fenced commits.
