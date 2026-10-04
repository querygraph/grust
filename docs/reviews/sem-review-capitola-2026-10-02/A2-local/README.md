# Stage A repeated on Capitola: Pecan against graphframes-rs on one laptop

Measured on 2026-10-02 on Capitola (Apple M1 Max, 10 cores, macOS, native
arm64 builds). It repeats the gate's A2 contrast with the same inputs and
the same boundary, and adds a step-level profile of Pecan's WCC.

## Why

The gate's A2 report gives Pecan's rounds one by one. On cit-Patents the
randomized WCC takes 16 rounds, and round 1 alone is 23 s of a 48 s call.
graphframes-rs runs the same plan shape per round: a union, a grouped
minimum, two joins and a distinct. So the question was whether Sail is that
much slower on the same plan, or whether something on the gate is.

## Setup

| | Pecan | graphframes-rs |
|---|---|---|
| Source | `querygraph/sail` `0d1ef2ca3` | `ba2fdd8` |
| Build | `cargo build --release --locked -p sail-cli` (full LTO) | `cargo build --release` |
| Execution | Sail local mode, parallelism 10, 30 GiB greedy pool | one process, `--num-workers 10 --max-memory 30G` |
| WCC | `method="randomized"`, seed 42, canonical labels, snapshot and repartition on (A2's settings) | `wcc --seed 42` |
| PageRank | `method="pregel_delta"`, tolerance 0.01, 10 steps, normalized | `page-rank --tol 0.01 --max-iter 10` |
| Input | LDBC `cit-Patents-{v,e}.parquet`, read in place | the same files |

The timer runs from just before the engine process is started to its exit.
For Pecan that includes server start, session, the algorithm, the Parquet
export and shutdown. Two ABBA blocks, four samples per engine. Every pair is
checked: WCC labels equal on all 3,774,768 vertices; PageRank within 1e-12
on every vertex.

## Result: launch to exit

| Contrast | Pecan, median | graphframes-rs, median | Pecan over graphframes-rs | Oracle |
|---|---|---|---|---|
| Randomized WCC | 5.00 s | 3.66 s | **1.37** | 3,627 components, 0 label mismatches |
| PageRank, 10 delta steps | 5.12 s | 4.00 s | **1.28** | largest difference 2.2e-19 absolute, 3.6e-15 relative |

Raw records: [`a2-launch-to-exit.json`](a2-launch-to-exit.json). The first
graphframes-rs sample of the run was 4.68 s (cold); the others were 3.59 to
3.72 s.

## Result: graph500-24, launch to exit

The LDBC `graph500-24` files: 8,870,942 vertices, 260,379,520 edges. One
ABBA block, two samples per engine, the same settings and oracle.

| Contrast | Pecan | graphframes-rs | Pecan over graphframes-rs | Oracle |
|---|---|---|---|---|
| Randomized WCC | 31.0, 29.8 s | 26.8, 28.6 s | **1.10** | 2,901 components, 0 label mismatches on 8,870,942 vertices |
| PageRank, 10 delta steps | 23.9, 25.0 s | 19.5, 21.5 s | **1.20** | largest difference 2.0e-18 absolute, 1.4e-14 relative |

Pecan's WCC took 19 rounds. The largest resident set of any engine process
in the run was 13.3 GB. Sem's published time for this WCC on a c5d.4xlarge
is 33.3 s. Raw records:
[`a2-launch-to-exit-graph500-24.json`](a2-launch-to-exit-graph500-24.json).

Banda on the same machine and files is in [`../F1/README.md`](../F1/README.md):
about 140 s for its first WCC call, 1.1 s for the second.

## Result: three contrasts, both input policies

graphframes-rs reads its inputs where they are. Pecan by default first
copies them into the run (the snapshot); `snapshot_inputs=False` (B7) reads
them in place. Both policies were measured, each in its own paired run, at
`querygraph/sail` `d0e4e422a`, which also stops BFS writing the edge table a
second time. BFS is Pecan's frontier method against his `shortest-path` from
one landmark (vertex 5795784 on cit-Patents, 798169 on graph500-24), checked
hop by hop on every vertex. Median seconds, launch to exit.

| Graph | Contrast | graphframes-rs | Pecan, snapshot | Ratio | graphframes-rs | Pecan, in place | Ratio | Samples |
|---|---|---|---|---|---|---|---|---|
| cit-Patents | WCC | 3.66 | 5.00 | 1.37 | 3.45 | 4.05 | **1.17** | 4, 4 |
| cit-Patents | PageRank | 4.00 | 5.12 | 1.28 | 2.78 | 3.17 | **1.14** | 4, 4 |
| cit-Patents | BFS | 1.85 | 1.98 | 1.07 | 1.86 | 1.21 | **0.65** | 4, 4 |
| graph500-24 | WCC | 27.70 | 30.40 | 1.10 | 25.51 | 20.29 | **0.80** | 2, 2 |
| graph500-24 | PageRank | 20.48 | 24.49 | 1.20 | 18.05 | 17.06 | **0.95** | 2, 2 |
| graph500-24 | BFS | 9.70 | 14.15 | 1.46 | 9.78 | 8.53 | **0.87** | 2, 2 |

- With the inputs read in place, as his binary reads them, Pecan is between
  0.65 and 1.17 times graphframes-rs on this machine. At graph500-24 it is
  at or ahead of it on all three.
- The snapshot is the largest single cost Pecan adds: 10 s of a 30 s WCC at
  graph500-24. It is more than the 4 s the copy takes to write. The copy is
  written round-robin into 10 files, and the rounds that read it are slower
  than rounds over the original file.
- Before `d0e4e422a` the graph500-24 BFS took 19.7 s with the snapshot (ratio
  1.96): it wrote the 260M edges twice before the first round.
- The medians of the same engine differ between runs by up to 30% (PageRank
  on cit-Patents: 4.00 and 2.78 s for graphframes-rs). Each ratio is taken
  inside one run. The laptop was in use.

Records: `a2-launch-to-exit*.json`; the names carry the input policy, the
graph and, for BFS, the commit.

## The same contrast on the two hosts

| | Gate (A2) | Capitola | Gate over Capitola |
|---|---|---|---|
| graphframes-rs WCC, launch to exit | 13.75 s | 3.66 s | 3.8 |
| Pecan WCC, launch to exit | 51.8 s | 5.00 s | 10.4 |
| Pecan over graphframes-rs | 3.77 | 1.37 | |
| Pecan round 1 | 23.2 s | 1.43 s | 16 |
| Pecan rounds 5 to 16, together | 3.2 s | 0.26 s (the writes) | 12 |

Moving from the laptop to the gate slows graphframes-rs by 3.8 and Pecan by
10.4. Both engines read and write the same volume on the gate, and both are
x86 Linux builds there. Something on the gate costs Sail about 2.8 times more
than it costs graphframes-rs. It is not yet known what.

## Result: where Pecan's time goes (release host, warm server)

Median of five runs of the public call. Raw output:
[`profile-variants.txt`](profile-variants.txt).

| Setting | Call | Round 1 | of which representatives | of which relabel | Rounds 5 to 16 | Back pass |
|---|---|---|---|---|---|---|
| Default (A2's settings) | 4.08 s | 1.43 | 0.61 | 0.82 | 0.26 | 0.48 |
| Sort-merge joins preferred | 4.17 s | 1.38 | 0.61 | 0.77 | 0.26 | 0.66 |
| No keyless repartition (B1) | 3.62 s | 1.22 | 0.53 | 0.70 | 0.27 | 0.41 |
| Inputs in place (B7) | 3.57 s | 1.31 | 0.53 | 0.77 | 0.26 | 0.47 |
| In place, no repartition, hashed labels | 3.18 s | 1.19 | 0.51 | 0.68 | 0.25 | 0.29 |
| Debug-profile host, default, one run | 37.96 s | 12.59 | 6.09 | 6.49 | 1.40 | 5.53 |

- The counts are free here: Sail answers a count over a written stage in
  under 10 ms.
- A tail round costs about 20 ms. Twelve of them are a quarter of a second.
- Sort-merge joins change nothing at this size.
- Skipping the snapshot and the repartition saves 11 to 13% each. With the
  hashed labels kept, the three together save 22%.
- The debug-profile host is 9 times slower, and its tail round costs 0.1 to
  0.2 s. The gate's tail rounds cost 0.2 to 0.4 s.

## What it says

- On this laptop Pecan is in graphframes-rs's class: 1.1 to 1.5 times launch
  to exit with its default input snapshot, 0.65 to 1.17 times with the inputs
  read in place, with a client-driven controller and the same number of
  writes per round.
- So the gate's 3.8 is not explained by the controller's actions per round.
  Most of it appears on the gate and not here.
- Stage B's knobs are worth about 10% each on this graph. None is a large
  lever.

## What is not known, and the check that decides it

Why Sail loses 2.8 times more than graphframes-rs on the gate. Three
candidates, in the order to check them:

1. **The gate's Sail binary.** `scripts/build.sh` builds the host with the
   dev profile. Against this suspect: every gate receipt names a binary
   called `…-release`, and one of them sits in cargo's `release/` directory.
   **Cleared**: Codex found the receipt, `cargo build --locked --release -p
   sail-cli`, optimization level 3 and LTO. The next two are what remain. A dev-profile host on Capitola gives a 12.6 s
   round 1 and 0.1 to 0.2 s tail rounds, which is the gate's shape. The
   check: the exact cargo command, the file size (a stripped LTO release is
   about 134 MB here; a dev build is 930 MB), and a rebuild with
   `cargo build --release --locked -p sail-cli` if in doubt.
2. **Sail on x86 Linux in that VM.** If the binary is a true release build,
   run [`profile_wcc.py`](profile_wcc.py) once in the A1 container. It
   splits each round into its two writes and its count, which says whether
   the time is in the engine, in the writes, or in the round trips.
3. **Partitions.** The gate ran 16 partitions on 16 vCPUs of a shared
   18-core host. A run at 8 would show whether oversubscription matters.

## Limits

- Two graphs. graph500-24 has one block, two samples per engine.
- A laptop with other applications running. The medians are indications.
- macOS and arm64, not the gate's Linux and x86. The comparison between
  hosts is of ratios, not of seconds.
- graphframes-rs here is `ba2fdd8`; the gate built `b4da56d`.

## Reproduce

```sh
# builds
cargo build --release --locked -p sail-cli        # in the Sail fork at 0d1ef2ca3
cargo build --release                             # in graphframes-rs at ba2fdd8
# launch to exit, both engines, oracle on every pair
python a2_local.py --out a2-launch-to-exit.json
# step-level profile against a running server (serve.sh <port>)
python profile_wcc.py --remote sc://127.0.0.1:50178 --vertices cit-Patents-v.parquet \
  --edges cit-Patents-e.parquet --src source --dst target --partitions 10
```

The scripts carry Capitola's paths at the top; change them for another host.
