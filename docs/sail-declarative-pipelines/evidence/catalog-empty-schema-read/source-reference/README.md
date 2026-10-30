# Empty stored catalog schema: named-read fallback

This packet audits pinned Spark 4.2.1 source and Sail `03e8783f2164b259f17ed0294af6189053240bf4`.
It runs no new Spark/Sail runtime, service, build or gate and changes no worktree.
All retained Sail source files are byte-identical in public candidate
`8ea2c075ed2cccb503c99ece60e18db32a32964c`, the binary used by the root controls.
Exact full source files, numbered excerpts, licenses and hashes are retained in
`source-audit.json` and `sources/`.

## Supported minimal boundary

Spark DataSourceStrategy.scala253–277, FindDataSourceTable.readDataSourceTable,
passes None for an empty stored catalog schema and Some(schema) otherwise.
Its explicit comment preserves runtime inference for older empty-schema catalog
entries. This supports the same fallback in Sail's ordinary named-table read,
without first introducing CREATE-time inference.

Sail query/read.rs207–247 constructs a schema from stored columns, validates
constraints against it and always wraps it in Some. Empty catalog columns should
instead request inference at that named-table SourceInfo boundary; nonempty
columns and existing options/constraints/partition handling remain intact.
Direct ReadDataSource at read.rs613–620 independently retains the caller's None
versus Some(empty) distinction and must not be changed. Spark DataSource.scala221–231
likewise preserves Some(empty) for an explicitly supplied read schema. ORC's
prepare_explicit_schema retains explicit empty output; generic listing formats
historically converted empty to inference, explaining the differing controls.

## Prior runtime evidence, not a new probe

Root's first exact E public attempt reported 295 passed and one failed, before
its upstream runner executed. The unchanged external ORC test expected nullable
INT id but received StructType([]). `catalog-control.json` is a byte-for-byte copy
of the retained same-binary six-case control: omitted and explicit schemas for
ORC, Parquet and JSON. Omitted ORC produced two empty rows; omitted Parquet/JSON
returned id rows while all three omitted-schema DESCRIBE results were empty.
Explicit id INT succeeded for all three. All input data files retained their hashes.
The script, first failure log/XML, build/server/gate receipts and terminal
observation are referenced by exact path/size/hash, without duplicating the large
public packet. The control's recorded binary hash binds these observations to E.
No failed result is replaced by a hypothetical passing outcome.

## Separate CREATE and metadata gap

Spark createDataSourceTables.scala65–124 first validates the relation, normally
infers and persists schema plus partition names, and explicitly falls back to an
empty stored schema when data/partition columns overlap. Named-read compatibility
therefore does not establish complete CREATE/DESCRIBE parity.

Sail CREATE currently carries omitted columns as an empty vector through the
plain catalog path. Its special creation metadata path handles lake sources;
plain file formats return unchanged options, and the memory provider stores the
empty vector. A later general CREATE inference unit must preserve IF NOT EXISTS
and existing-table error ordering, capture the correct read-case/session options,
retain partition discovery, and preserve logical field metadata. The current
CreateTableColumnOptions/TableColumnStatus carriers retain type/nullability,
comment/default/generation/identity fields but no arbitrary top-level Arrow field
metadata map; field() reconstructs only those supported metadata properties.
Merely copying inferred fields through those carriers would not establish semantic
TIME/interval metadata persistence. No carrier or CREATE redesign is selected here.

Required focused regressions are named omitted-schema inference, unchanged
nonempty catalog schemas, direct explicit-empty ORC behavior, unchanged source
files, and no read-triggered catalog mutation. Existing Parquet/JSON reads and
DESCRIBE controls remain useful. The original E assertion must pass unchanged
before public qualification advances. No writer, streaming or CDC work is included.
