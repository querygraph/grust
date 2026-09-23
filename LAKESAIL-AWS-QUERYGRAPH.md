# Decommissioning the four AWS hosts: what was on them and where it went

On 2026-09-23 the four Linux hosts this work ran on — `quegee`, `grust`, `eigen`
and `lakecat`, all EC2 instances in one AWS account, reached by name over
Tailscale — were stopped for cost and then cleared for termination. This file is
the record of what was taken off them first, how each item was verified, and what
was deliberately left to die. It is written so that someone who never saw the
hosts can tell whether anything was lost.

Terminating an instance destroys its EBS volume. Everything below was therefore
copied or pushed *before* termination, not after, and every claim here was
checked by a command whose output is quoted or summarised.

## 1. The hosts and what each did

| host | class | role in this work |
| --- | --- | --- |
| `quegee` | c5n, dedicated | the only machine publishable timings came from; benchmark campaigns B3–B9 |
| `grust` | t-class, burstable | the Linux gate (`~/gates/gate.sh` → `scripts/ci-local.sh`) |
| `eigen` | t-class, burstable | second-opinion ratio runs and the PageRank ablation |
| `lakecat` | t-class, burstable | small clean-room checks |

They went unreachable together at 2026-09-23 ~05:20 UTC — no ssh, no ICMP, and
all four left the tailnet within the same minute — which cost campaign B8 its
large and xlarge runs and left a Linux gate without a verdict. They were restarted
later the same day with their disks intact, and the preservation below was done in
that window. Their public addresses changed across the restart; the Tailscale
names did not, which is why every command in this record uses `quegeetail`,
`grustail`, `eigentail` and `tailcat`.

## 2. How "what is only here" was established

Two sweeps, because the first was too narrow and missed real work.

**First sweep** walked `~/src/*/` on each host and reported, per repository, the
branches with commits not on `origin`, the stashes, and the modified tracked
files. It found the obvious things and gave a false sense of completeness.

**Second sweep** walked every git repository anywhere under `$HOME` (plus
`/data`, `/opt`, `/mnt`, `/srv`) to depth 4, excluding `target/`, `node_modules/`
and `.cargo/`, and counted commits not on **any** remote rather than not on
`origin`. That found three things the first missed:

- `~/src/nutmeg-0.23/sail` on `grust`, branch `pr-2522`, **nine commits**;
- `~/src/perfattr/grust-exp` on `quegee`, **seven branches**, whose `origin` was
  another directory on the same host — a remote that would die with it;
- `~/src/eigentimes` on `lakecat`, `main`, 153 commits with no remote configured.

A third sweep looked for untracked files and non-repository data, which is how the
7.3 GB `fit-hn4` tree and the strain-benchmark reports were found.

**The lesson worth keeping:** counting against `origin` hides a branch whose
`origin` is itself local, and a repository with no remote at all reports every
commit as unpushed, which looks alarming and may mean nothing. Both cases occurred
here, one in each direction.

## 3. Source code: pushed to real remotes

Every branch that existed only on a host is now a ref on a hosted repository.
Names are prefixed `rescue/` and record the host they came from, so nothing
collides with live work.

**`querygraph/grust`** (11 refs):

| ref | commits | from |
| --- | --- | --- |
| `rescue/quegee-pagerank-gap-experiments` | 12 | `quegee:~/src/grust` |
| `rescue/quegee-meter-balance-padding` | 1 | `quegee:~/src/grust-next` |
| `rescue/quegee-perfattr-exp-body-only` | 1 | `quegee:~/src/perfattr/grust-exp` |
| `rescue/quegee-perfattr-exp-charge-fix` | 1 | same |
| `rescue/quegee-perfattr-exp-fix-root-inline` | 3 | same |
| `rescue/quegee-perfattr-exp-inline-only` | 1 | same |
| `rescue/quegee-perfattr-exp-revert-counted` | 1 | same |
| `rescue/quegee-perfattr-exp-root-inline` | 2 | same |
| `rescue/quegee-perfattr-work-pagerank-path-experiments` | 5 | same |
| `rescue/lakecat-lancedb-anchored-reads` | 1 | `lakecat:~/src/grust-lance` |
| `rescue/lakecat-turso-mvcc-bulk-load` | 2 | `lakecat:~/src/grust-mvcc-load` |

**`querygraph/adversarial-graph`**: `rescue/lakecat-compact-reference`, 6 commits,
from `lakecat:~/src/adversarial-graph`.

**`querygraph/sail`** (the fork, not upstream): `pr-2522` at `f702d3a9` and
`session-factory-hook` at `8806310d`.

Verification: three of the `rescue/` refs were checked head-to-head against the
host (`b9781db`, `faff5cb`, `d347fc5` — identical on both sides), and both Sail
branches were verified by tree hash rather than by commit id, because they were
replayed rather than fetched (§4): `1f3578e7…` for `pr-2522` and `8f48a8df…` for
`session-factory-hook`, each matching the host's tip exactly.

**Why the Sail branches went to a fork and not upstream.** Their checkouts had
`https://github.com/lakehq/sail.git` as `origin`. Pushing there would have put our
branches on the upstream project's repository. That is a publication, not a
backup, and it is not ours to make; the automated attempt was refused and the
decision was taken to the operator, who chose the `querygraph/sail` fork.

## 4. The partial-clone obstacle, and how it was worked around

`grust:~/src/nutmeg-0.23/sail` and `quegee:~/src/sail` are **blobless partial
clones** (`origin` carries `[blob:none]`). Such a clone cannot serve its own
history: `git fetch` from it aborts with *"git upload-pack: aborting due to
possible repository corruption on the remote side"*, and a `git bundle` made with
`--not --remotes` is unusable elsewhere because it names prerequisite commits the
bundle does not contain.

The route that worked, and that anyone repeating this should use:

1. On the host, `git format-patch` the commits (this succeeds: the blobs the
   local commits introduced are present, and missing base blobs are fetched on
   demand from upstream).
2. On a machine with a full clone of the fork, fetch the **base** commit from
   upstream by sha (`60d6771a…` for `pr-2522`, `20f4de4f…` for the hook).
3. Branch at that base, `git am` the patches, compare `HEAD^{tree}` with the
   host's tip tree, then push.

The tree comparison is what makes this a preservation rather than a re-creation.

## 5. Working-tree state that was not commit-shaped

Stashes and modified tracked files across roughly 25 probe and release checkouts
were saved as patches — `<repo>--stash.patch` and `<repo>--modified.patch` — in
the rescue directory. They are not branches and were not pushed; they exist so
that a half-finished edit can be read later, not so that it can be replayed
blindly. Untracked files were excluded except where a stash carried them.

## 6. Data

**`s3://eigentimes-data` and `s3://eigentimes-site`** are in the same AWS account
as the instances and are unaffected by terminating EC2. The eigentimes repository
documents the first as canonical (`scripts/daily.sh` pulls from it). The bucket
held 26,555 objects, 42.3 GB, under `raw/`, `derived/` and `models/`.

**One tree was not in either bucket**: `grust:~/src/eigentimes/fit-hn4`, 7.3 GB in
49,407 files (`derived/comments/`, `derived/embeddings/model=bge-small…`,
`raw/articles/`), written between 1 and 13 September, with no `fit-hn4` prefix in
the bucket and no `derived/comments` there either. On the operator's instruction it
was synced up:

```
AWS_PROFILE=eigentimes aws s3 sync ~/src/eigentimes/fit-hn4/ s3://eigentimes-data/fit-hn4/
```

Completed 2026-09-23T18:56:34Z. Verified by count and size: **49,407 objects,
7,673,441,728 bytes** at the destination, against 49,407 files at the source.

**`alexy/eigentimes`** already contained every host's `main`: the heads on
`lakecat` (`8ba873b`), `grust` (`256b6fe`) and `eigen` (`1c548d9`) were each
checked with `git merge-base --is-ancestor` against the GitHub default branch and
are all present and merged. The "153 unpushed commits" reported on `lakecat` was an
artefact of that clone having no remote configured.

## 7. Benchmark and agent records

- **Campaign B9** (Grust `4a9e7f5`) was bundled into
  `adversarial-graph-algorithms` on `work/bench-b9` and pushed, with a
  regeneration gate proving every published table comes back from the evidence.
- **Campaign B8** was never bundled — the outage killed it mid-flight — so its
  clean parity files, two timed runs, receipts, plan, sources, `campaign.jsonl`
  and driver scripts were copied off (45 MB). Its image receipt had been
  overwritten by a B9 postbuild script with a hard-coded `b8-` prefix; a
  reconstructed receipt, marked as such, was written from the image still on the
  host.
- **Gate logs**: every `~/gates/*.log` from `grust`, holding the verdict lines for
  `55a200f`, `f421282`, `ead3568`, `2985fac`, `48598b4` and `4a9e7f5`. The
  `ca77603` log holds only its header: that gate died with the host, which is why
  the branch stack was re-gated at its head instead.
- **The ablation's raw samples** from `eigen`: `cells-*.json`, `cells.csv` and the
  run logs behind the PageRank attribution (288 KB).
- **Agent session records**: the complete `~/.claude/projects` tree from all four
  hosts — 145 MB, 34 memory files, 23 transcripts. These hold host-specific
  operating knowledge that exists nowhere else: build memory caps on `quegee`, the
  one-consolidated-watcher rule, burstable-steal warnings, the box setup script's
  location, the crawl fleet's shard layout.
- **Text artefacts** from the probe and report directories on all four hosts
  (5.4 MB, ~4,700 files): the 60 timestamped strain-benchmark run reports from
  15–16 September, each an `adversarial-graph/report/v1` document recording
  harness revision, Grust version and source rev and host CPU — provenance that
  was not in any repository — plus the `gap` profiling outputs and the probe logs
  and configurations. The databases and build trees underneath them were left.

Everything above is under one directory on the operator's Mac, 394 MB in 244
files: git bundles (15), patches, the Claude records, the B8 evidence, the gate
logs and the artefact tarballs.

## 8. What was deliberately left to die

Reproducible by construction, and large: benchmark fixtures (regenerate from their
seeds, and the manifests pin them by SHA-256), the Docker images `b5-`…`b9-`
(rebuild from the recorded commits), cargo target directories, the LanceDB and
PostgreSQL probe databases (19 GB and 8.4 GB), the Turso MVCC data, the strain
load corpora, and the demo trees. Roughly 900 GB in total across the four hosts.

## 9. Checks run immediately before clearing termination

- No process above 5% CPU on any host, none of ours running anywhere.
- The branch sweep re-run: every remaining "unpushed" line traced to a ref that
  now exists on a hosted remote under its `rescue/` name, spot-checked by sha.
- `fit-hn4` object count and byte total matched at source and destination.
- The eigentimes heads confirmed merged on GitHub.

With those four checks passing, the hosts held nothing unique.
