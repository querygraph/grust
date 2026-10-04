# Committed native C4 Rust gate

Source preparation only. Root has committed the identical eight Rust source files at detached HEAD `ef5fc415ab4b182fb3df4e238cf634cc9fc94cd9`, tree `268779f765b88813ec737beb1b30442eb30a5e72`, repository `workspaces/sem-completion-20261003/c4-allocation-source01`, prefix `probe/`. This owner gates that exact committed source.

## Candidate admission

`config-template.json` pins the actual passed allocation run02 owner, actual waited-owner receipt, final optimized binary, immutable configuration and frozen owner02 helper source. Runtime admission rechecks these pins, every prior command/log/group closure, and the six full 14-line allocator outputs with their final semantic markers and counters. Exact binary/argument bindings and all six locked Rust command arguments are required. The imported owner02/ownership helpers must match their original frozen paths and identities.

The prior controls are reused only because committed source bytes and rebuilt optimized binary must remain identical to that closed candidate. The committed gate runs no allocator binary or graph query. Candidate gate provenance remains separately named; its earlier uncommitted source bytes are not relabeled as a commit verdict.

## Root launch

Root prepares the fresh physical result directory selected by the final configuration. The template selects `C4-allocation-run03-committed`, allowing the original owner02 typed Plan namespace rules to remain intact. It reuses the closed candidate's private target and Cargo cache. Run the new waited supervisor with isolated imports:

```python
boot = 'import runpy,sys;sys.path[:0]=sys.argv[1:4];sys.argv=sys.argv[4:];runpy.run_path(sys.argv[0],run_name="__main__")'
argv = [PYTHON, '-I', '-B', '-c', boot,
        NEW_HELPERS, OWNER02_HELPERS, C2_OBSERVER_BUILD01_HELPERS,
        NEW_HELPERS + '/wait_committed.py', '--config', FINAL_CONFIG]
```

Root detaches this short-lived launch through its normal `Popen`/owned launcher. It must retain its actual outer wait and group absence. A detached PID alone cannot qualify.

The supervisor writes `wait.json`; the owner writes `owner-receipt.json`. The reused step helper also maintains a legacy `receipt.json` command journal during execution, copied to `command-journal.json` at closure. That journal's generic `running` outcome is not a positive allocator verdict; the new `owner-receipt.json` carries the specific final committed-gate verdict.

## Gates and boundaries

The owner sets soft `RLIMIT_NOFILE=8192` while preserving the observed hard ceiling, refusing a ceiling below8192. It records before/after limits. It acquires only the original two graph `gate.lock` and `serial-queue.lock` paths, with exact PID/token/config release checks. Root schedules it only after other heavy jobs and their locks close.

All six required commands run natively with the unchanged frozen owner02 environment/profile, offline locked dependencies, four build jobs and the same private target/cache: Rust version, Cargo version, format, Clippy, tests, and release build. Soft FD policy and fresh temporary directory are explicit. Release remains opt3/fatLTO/codegen1/debug0/striptrue. Git metadata inspections are separately owned and waited before/after; both must observe the exact detached commit/tree, clean status and complete eight-file set. Git environment overrides are refused.

The final source/config/helpers/tools/prior controls and compiled binary are rechecked after these gates. Every command group must be absent with actual completed waits and no forced cleanup. Failure retains locks and metadata, with no positive qualification even if cleanup subsequently waits zero. Root independently closes failures before releasing their own locks.

This gate qualifies the exact committed standalone Rust source. Its six prior allocator controls are exact-byte evidence reused from the earlier closed candidate. Requested System bytes, reported accumulator sizes, output sizes and lifetime RSS remain distinct; exploratory raw clocks include size sampling. No whole-graph speed, Sail physical pool, OS memory ceiling or historical stream diagnosis is qualified here.
