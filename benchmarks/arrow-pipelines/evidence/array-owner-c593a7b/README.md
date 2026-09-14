# Shared array owner consumer qualification

Source `c593a7b` passed 162 tests, 0 failed, 0 ignored across Arrow,
DataFusion, algorithms and algorithm-procedures; all-target Clippy passed.
Native Capitola, four nice Cargo jobs, locked all-feature commands.
The original `2494fb4` Arrow55 compilation failure is retained, corrected by
using common borrowed ArrayData accessors. This predates the additional C Data
array-export regression and full workspace qualification. No performance or
automatic-routing claim is made.
