# Host wind-down: what lives on grust and eigen, and what must move

Written 2026-09-23 06:45 UTC, while all four Linux hosts (`grust`, `eigen`,
`quegee`, `lakecat`) are unreachable: no ssh, no ICMP on their public addresses,
and all four left the tailnet within the same minute, ~05:20 UTC. The decision to
retire `grust` and `eigen` and move their work to `quegee` was taken independently
of that outage. This file records what was on each host, what exists nowhere else,
and what the migration costs, so nothing is lost when they are stopped.

## What each host was doing for this work

| host | role | class |
| --- | --- | --- |
| `quegee` | the only host publishable timings come from; benchmark campaigns | c5n, dedicated |
| `grust` | the Linux gate (`~/gates/gate.sh` → `scripts/ci-local.sh`) | t-class, burstable |
| `eigen` | second-opinion ratio runs and ablation attribution | t-class, burstable |
| `lakecat` | small clean-room checks | t-class, burstable |

## State on `grust` at the outage

- **One job was running:** the Linux gate for `ca77603` (`work/meter-block-charge`),
  PID 3750347, started 04:46Z with
  `nohup ~/gates/gate.sh ca77603444d4a2ee8dbccec84958f3f3b82598bf > ~/gates/meter-block-charge.log 2>&1 &`.
  It had passed every phase and was inside release package verification when the
  host went. **No `ci-local:` verdict line was read**, so that branch is not
  Linux-verified. The log is the only copy of that run.
- **Evidence that exists only there:** the gate logs. `~/gates/*.log` holds the
  verdict lines for `55a200f`, `f421282`, `ead3568`, `2985fac`, `48598b4` and the
  incomplete `ca77603`. Everything else (branches, commits) is on `origin`.
- **Disk:** 285 GB free after the clean-up of 2026-09-23 05:0xZ, which removed two
  stale gate caches and six abandoned worktree target directories and pruned dead
  worktree registrations. Remaining large items are `~/gates/target-48598b4…` and
  `~/gates/target-ca77603…`.

## State on `eigen` at the outage

- **No job running.** Three capped release builds, two fixture generations and two
  campaign scripts all completed; one driver started inside a blackout window was
  killed and verified gone.
- **Everything is under `/home/admin/pr-attrib/`**, about 750 MB plus two cargo
  target directories: staged sources for bench `31ea9f10` with Grust `2985fac` and
  `ead3568`, eight fixtures, eight logs, five scripts, six `cells-*.json` result
  files and `cells.csv`.
- **Evidence that exists only there:** the raw per-repeat samples
  (`cells-*.json`, `cells.csv`) and the run logs. Every number that feeds the
  attribution was transcribed to this Mac's scratchpad
  (`pagerank-attribution.md`), so no conclusion depends on the host, but the
  samples behind the medians do. The fixtures are exactly regenerable
  (`fixtures.py --seed 20260920`, and `degfix.py` for the degree sweep, both on
  the Mac).

## State on `quegee` at the outage

Campaign B8 (Grust `2985fac`) was mid-flight: image `simple-rust-algo-bench:b8-2985fac`
built and audited, all nine parity invocations clean with the f64 rows bit-identical
to v0.22.0, the two protocol timed runs clean, and the four large and xlarge runs
lost. Parity files, receipts, the image and the driver scripts (`b8-build.sh`,
`b8-postbuild.sh`, `b8-parity.sh`, `b8-timed.sh`, `b8-drive.sh`) are on its disk and
nowhere else; nothing of B8 is committed yet.

## What migrating to `quegee` costs

Two roles have to collapse onto one box, and they conflict:

1. **The gate is a load.** A full `ci-local.sh` compiles and tests the workspace for
   about 40 minutes at `-j4`. Running it on the timing host while a campaign is
   timing invalidates that campaign — `AGENTS.md` requires the host to be idle, and
   the harness discards a run whose watcher records a foreign process. So gates and
   campaigns must be strictly serialized by a lock both take, not merely by habit.
2. **The second opinion disappears.** `eigen` and `lakecat` were where a result
   could be checked in a different place, and where ablations ran at no cost to the
   campaign schedule. On one host that work has to wait for the timing host to be
   free, which makes attribution slower and gives up cross-host corroboration
   entirely. `AGENTS.md` already forbids publishing a burstable host's absolutes, so
   nothing published changes; what is lost is the ability to check a shape twice.

The honest way to write this down, if the migration stands, is a rule in
`AGENTS.md`: one host, one activity at a time, taken through a lock file that the
campaign driver and the gate script both respect; and a statement that
cross-host corroboration is no longer available, so a surprising result is
re-run in place rather than checked elsewhere.

## The decision, 2026-09-23 06:50 UTC: all four hosts down, work continues on the Mac

Every Linux host is being shut down, not only `grust` and `eigen`, and the work
continues on the Mac alone until another machine arrives. What that changes:

- **No Linux gate.** A commit can be gated on macOS only, which is a weaker claim:
  the Linux gate has caught what the Mac did not (a deadline test that passed on a
  laptop and failed on a loaded burstable host). Until a Linux gate exists again, a
  branch is "gated on macOS, Linux outstanding" and says so; nothing is merged to
  `main` on a Mac-only verdict without that sentence attached.
- **No publishable timings.** `AGENTS.md` publishes absolutes from a dedicated host
  only. On a laptop every number is shape: a ratio, interleaved, with its dispersion
  and the load on the machine stated. No campaign, no bundle, no site page, no post
  can be produced from Mac numbers, and none will be.
- **The benchmark loop pauses at measurement, not at work.** Kernel changes, their
  bit-identity proofs, their tests and their local shape can all continue; the cell
  that decides whether a change closed a gap cannot be run until a host exists.

**At risk if the instances are terminated rather than stopped** (small, and no
conclusion depends on it): `grust`'s `~/gates/*.log`, which hold the verdict lines
for every gate this work has passed, including the unfinished `ca77603` run; and
`eigen`'s `~/pr-attrib/cells*.json`, `cells.csv` and `logs/`, the raw per-repeat
samples behind the attribution's medians. Both are recoverable in substance — the
verdicts are quoted in this repository's history and in the session record, the
attribution's numbers are transcribed in full, and every fixture regenerates from
its seed — but the primary files exist only on those volumes. Stopping the
instances preserves them; terminating them does not.

When a host exists again, the order is: read `~/gates/meter-block-charge.log` for a
`ci-local:` line naming `ca77603`, copy `~/gates/*.log` and `~/pr-attrib/` off, then
restart the campaign on the timing host from `~/src/b8-timed.sh`.
