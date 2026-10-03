# Four-phase WCC oracle preparation

The independent F2a physical WCC checker is copied byte-exact, SHA256
`6514d12838a558336bfbeee0340682f500938e750ccf39698fdf8fb621b2bbc3`.
Its old source gates and controls remain the authority; no engine code is imported.

Tiny config `oracle-tiny-int64-c3-plan03.json` binds the actual closed smoke03
worker and waited producer receipts plus all three complete output file hashes.
Its reference is the old independently specified four-vertex expected partition
(including isolate0), not a GF production result. The main four templates retain
separately qualified GF WCC reference inventories from A5 and exact originals.
Their output inventories are explicitly null; these are not runnable Configs.

Root invokes the copied helper as `python -I -B f2a_oracle.py --config ABSOLUTE_JSON`
after producer groups close. Full original-domain, signed Int64 schema, non-null,
uniqueness, label domain and canonical partition comparison cover every row of
every output. This checks partition equivalence, not identical raw component
labels. All original/reference/output hashes are rechecked by the actual oracle
outside every engine timer. Root separately owns current process closure,
original topology/reference provenance and complete output retention.

Author only read small metadata/source and hashed three tiny raw output files
without decoding Parquet. No input/fullgraph/reference payload was read, no
engine/oracle/build/process action launched. No positive oracle verdict is
claimed here. The initial pure-model namespace error is retained separately.
