# Commit identities after message amendment

On 2026-11-06 the local Sail commits from upstream `b52144955` to the Delta append
pipeline were recreated so that every commit has a full message body. Trees, authors
and dates are unchanged; only messages and therefore commit hashes changed. Evidence
written before this date cites the original hashes. The originals remain reachable
under `refs/backup/pre-message-amend/` in the Sail repository.

| Original | Amended | Subject |
| --- | --- | --- |
| `60b98ba03` | `ce87175c2` | fix: preserve Arrow data fidelity in streaming events |
| `e432a464f` | `c442efdb7` | fix: exclude streaming control markers from filter evaluation |
| `d57946ee2` | `2e606f7ce` | fix: propagate terminal streaming failures to query clients |
| `2c9fa8499` | `049017850` | perf: preserve reporting costs when propagating streaming failures |
| `06dd7e237` | `bfdecbcf9` | feat: support pinned Comet scalar kernels with field and code ownership |
| `327572240` | `62e180afe` | fix: isolate streaming projections from control records |
| `6e4da8d33` | `cb2d58ab0` | fix: preserve streaming sources before logical pruning |
| `b6d73d6a6` | `c40e30efc` | fix: preserve projection computations and declared schemas |
| `bd1847d8e` | `ad94e3901` | feat: control live streaming sources through execution owners |
| `3f741daad` | `e77ff4cd4` | feat: capture immutable Delta replay descriptors |
| `d72803efd` | `46ef4d6eb` | fix: release sorted Delta replay payloads per input batch |
| `07cb40965` | `600fa36a7` | feat: decode complete Delta Add payloads without scan defaults |
| `bddb46709` | `37837d20a` | feat: add local recoverable Delta append pipelines |

Branches now point at the amended commits: `work/streamsource-foundation-20261105`,
`work/streamsource-comet-scalar-20261105`, `work/streamsource-projection-20261105`,
`work/streamsource-participation-20261105`, `work/projection-composition-20261106`,
and the new `work/delta-append-recovery-20261106` for the append pipeline tip.
Detached worktrees under `sail/tmp` still hold the original commits.
