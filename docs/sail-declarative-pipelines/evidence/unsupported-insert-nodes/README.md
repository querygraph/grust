# Ordinary INSERT nodes in pipeline definitions

The three-file increment rejects ordinary INSERT plans before pipeline query lowering, using Spark's UnresolvedWith, InsertIntoStatement, OverwriteByExpression and InsertIntoDir names. CREATE FLOW child operations retain their separate policy. Ordinary SQL lowering is unchanged. Shared parser validation still wins for invalid INTO IF NOT EXISTS.

Qualification:401 native+syntax/fmt/strictClippy, fresh300+67, seven exact-field public cases on each engine and an unchanged-test producer control. No golden or inventory changes. The full16-vector replay advances from12 to14matches; REPLACE BY NAME/USING remain unsupported grammar, and the existing recovery-hint/empty-statement/lexical/query-context gaps remain open. This does not qualify complete SDP conformance or CDC effects. Fable owns CDC independently.
