# Prepared ORC public gate helpers

Prepared only. No helper has been executed; there is no CLI build, Sail server, pytest result, or upstream execution from this packet yet. Root owns candidate creation, detached gate checkout, live port/resource checks, execution, cleanup, and subsequent archive. The exact candidate file `/tmp/sail-sdp-orc-public-registration-candidate.json` was present at the recorded preparation snapshot; helpers require and validate it again at execution.

The four helpers target `/Users/alexy/src/sail-sdp-gate` and never fetch, reset, checkout, commit, or edit its sources. They require an exact clean detached candidate (including untracked-file checks) and compare all five E files against the frozen registration hashes. Candidate JSON uses the established `{base, commit, paths}` shape; if a `label` is present it must be `orc-public-registration`. Its parent must equal `base`, and `paths` must be exactly the five E paths. Any reviewed source change requires an explicitly updated qualification packet; hash checks must not be bypassed.

## Root execution sequence, after prerequisite gates

Use `/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python` for every helper. Do not use the system `python3`: its Python 3.15 XML extension failed to load during a read-only preparation inspection; the qualified venv parsed the XML normally. That initial inspection failure ran no test or helper and changed no source.

1. Prepare the root-owned candidate JSON and clean detached gate checkout. Independently confirm sufficient disk and absence of conflicting builds. Run `build.py`. It executes only `cargo +1.98.1 build -p sail-cli --locked`, with `CARGO_PROFILE_DEV_DEBUG=0`, `CARGO_PROFILE_DEV_INCREMENTAL=false`, `CARGO_INCREMENTAL=0`, the absolute qualified `PYO3_PYTHON`, and the gate's own target directory. It records exact source/tree/lock/candidate hashes, command, environment overrides, exit code, log hash, CLI path/hash/size, and before/after source state in `build.json`. The existing >2GiB build precondition is retained from the root library gate. Build failure records remain in place.
2. Independently live-check port **50088**. Run `server.py` in a separate owned foreground exec session. This optional supervisor rechecks no listener, verifies the immutable build receipt and CLI hash, and starts `target/debug/sail spark server --port 50088`. It applies the previously qualified server `PYTHONPATH=/Users/alexy/src/sail-pipelines-proposal/.venv/lib/python3.12/site-packages` and matching `VIRTUAL_ENV`, preserving the environment correction from the prior TIME gate. It records the supervisor and child PIDs, exact command, receipt/hash, readiness, and environment in `server.json`. It requires the listener to be exactly its child PID and refuses to replace any existing listener.
3. While the supervisor is running and reports `READY`, run `gate.py`. This requires the matching server receipt, PID/command/port ownership, exact source state, immutable CLI/build/helper hashes, and the frozen Spark reference packet. It runs Ruff check and format check on both changed Python files, then the public pytest selection, then the upstream Python runner. Every command has a complete log and retained exit code/hash. Source and binary checks occur before and after every command.
4. After the gate finishes, stop only this supervisor using its recorded PID (SIGINT or SIGTERM). Its signal handler stops only the owned child; it records exit code, escalation if required, process absence, remaining listener PIDs, and server-log hash. Independently confirm owned PIDs and listener absence. Do not advance or rebuild the gate checkout while the gate or server is still being qualified.

`build.py`, `gate.py`, and `server.py` refuse to overwrite previous receipts/logs. Archive a failed attempt before an intentional rerun; retain all initial errors and assertions. The build receipt fixes helper hashes, so modifying a helper after build invalidates that receipt and must be reviewed explicitly.

## Exact public selection

`inputs/baseline-pytest.xml` is copied byte-for-byte from `/tmp/sail-sdp-time-public/pytest.xml`, SHA256 `9ea4f2fbb93bd3121387e306ab49e7b8417e907b6ec778d97ab89a92d0d81b6f`. Its 285 successful, unique node IDs are preserved in XML order. `selected-nodes.json` appends only:

- `python/pysail/tests/spark/pipelines/test_file_sources.py::test_batch_pipeline_reads_file_source[orc]`
- `python/pysail/tests/spark/datasource/test_orc.py`

This is 287 selectors and **296 expected cases**: 285 baseline + one retained ORC pipeline branch + ten new reader cases. The result checker requires 296 unique actual nodes, every baseline and pipeline node, exactly ten additional nodes from the new file, and zero failures/errors/skips. No skip, normalization, or expected-value changes are introduced by these helpers.

The separate unchanged upstream runner is `scripts/spark-pipelines-tests/run.py --spark-source /Users/alexy/src/spark-sdp-4.2.1 --remote sc://localhost:50088 --report /tmp/sail-sdp-orc-public/upstream.json`. Its required outcome is 67 executions, zero failures/errors/skips, Spark version 4.2.1, and pinned source `617618396087429b5627a86ce933bb0f5d6645cb`.

The client environment follows the previous gate (`PYTHONPATH=python`, explicit `SPARK_REMOTE`) with the same venv and bytecode writing disabled. The server environment is deliberately the separately qualified site-packages environment, not the client's source import path.

## Evidence and boundaries

The frozen Spark Connect reference at `/tmp/sail-sdp-orc-public-reference` is checked by its exact manifest SHA256 `137d93140b122ce5d7784ee62c58ce8d7883ec9cdfacdfbcc56ead0385d62e22` and per-file hashes. The gate compares its unchanged public test source, TIME fixture, and fixture provenance with the candidate. That packet's ten passed cases were direct invocations of the original test functions/fixture through Spark Connect, not a pytest run. It establishes the retained expected results, not Sail execution.

The copied prior gate/build/library scripts and receipts under `inputs/` record where the environment, Cargo flags, node-selection method, and separate upstream runner came from. `PREPARATION.json` inventories inputs and helpers, plus static checks performed. These are prepared orchestration helpers, not a public-read capability claim or full SDP qualification. No distributed, streaming, CDC, or ORC writer qualification is implied.
