# ORC semantic schema merging: reuse audit

Source inspection only; no runtime/probe verdict or new code.

Existing Sail pipelines/schema_merge.rs already implements Spark-style field
order, left metadata, nullability, decimal same-scale widening, interval qualifier
union and semantic TIME precision via spec::DataType. It is private to Connect,
returns SparkError and assumes case-sensitive field names. Data-source code must
not import Connect; an extraction would need a small lower-level error contract
and suitable Arrow/spec conversion, preserving existing pipeline behavior.
Arrow Schema::try_merge is not sufficient: equal TIME storage can have differing
precision, interval qualifier metadata needs union, and metadata/null promotion
policies differ. Avoid treating every Arrow metadata difference as incompatibility.

Spark 4.2.1 SchemaMergeUtils passes caseSensitiveAnalysis into StructType.merge
for file schema merging. A subtle source fact at StructType.scala619–620:
matched field types call merge(leftType,rightType) WITHOUT passing caseSensitive,
so nested field merging resets to its true default after the outer STRUCT level.
This must not be conflated with requested ORC reader nested-name matching, which
uses the Java ORC default-locale map. The outer schema map uses Locale.ROOT.
A future mergeSchema unit should retain separate top/nested case reference cases
before implementing a recursively insensitive merge. Existing 11-file reference
already qualifies TIME precision conflicts and interval-family/qualifier outcomes.

Next: choose the smallest shared semantic merge/type-boundary module using actual
callers; preserve pipeline tests and keep name-normalization policy explicit.
No extraction or universal Unicode decision is adopted by this source audit.
