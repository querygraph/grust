Prepared public regression harness, defaulting to corrected Sail candidate
`ec8e74d57de51149a774cd4f9048d82039704d0c`.

Run from any directory, after the root agent chooses to begin the public gate:

```sh
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python /tmp/sail-sdp-local-runner-public-harness/run.py --commit ec8e74d57de51149a774cd4f9048d82039704d0c
```

The default result directory is `/tmp/sail-sdp-local-runner-public-ec8e74d57de5`.
`--commit` accepts another exact full hash; the default output path uses its
first 12 characters. `--output` may select another fresh directory. Existing result
directories are refused. The owned server uses port 50094 and is stopped in a
`finally` block, with escalation restricted to its own process. An existing port
listener causes refusal; it is never stopped.

The harness builds `sail-cli` from the clean, detached gate checkout, with
`PYO3_PYTHON`, `VIRTUAL_ENV`, `PYTHONPATH`, `CARGO_TARGET_DIR`, and nonincremental
debug settings explicit. It records the CLI hash and `--version`, checks the
client and remote Spark versions are 4.2.1, and checks the exact source commit
and source hashes before and after each command. It records commands, selected
environment overrides, timestamps, exit codes, output logs, raw JUnit/upstream
results, and artifact hashes. Reusing the detached gate's target directory does
not skip the build command.

Coverage is 300 frozen pytest case IDs: all 298 accepted CTAS-public cases
(including both zero-row and three-row CTAS result regressions), followed by the
two accepted nested-materialization cases from `sail-sdp-nested-public-02`.
The retained failed first nested attempt is not the selection source. The
separate upstream runner must execute the same 67 pinned Spark Python case IDs
as the prior accepted run. No withdrawn `test_flow_file_config` cases are
included. This is selected regression coverage, not the whole SDP inventory or
proof of distributed shutdown, Iggy, CDC, or public ORC writing.

`preparation.json` records the exact prior XML/report hashes, the selected case
counts by file, and source hashes frozen at selection-preparation commit
`e8c47f2d9ccd3383ce03fe0a4b33ba20707ff33b`. That commit is provenance, not an
equality requirement for later candidates; all frozen test/helper source hash
assertions still apply. Root reported the corrected candidate changes only the
runner test's collection-error assertion. Copies of the prior
results are included solely to freeze selection provenance. They are not
results for this candidate.

Preparation performed read-only source inspection and static Python parsing.
No build, test collection, server, or test execution was started.
