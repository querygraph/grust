# Run a local pipeline that can resume after a process crash

The local pipeline command reads a Delta table, applies a SQL projection or filter,
and appends the result to a new Delta target. It saves the input position with each
published output, so restarting the same run can finish uncertain work without adding
its rows twice. This guide applies to local implementation `bddb4670`; the
[human review summary](HUMAN-REVIEW.md) records its qualification and remaining scope.

The current path uses one continuously executing reader on one machine. It supports
local files and process crashes while the operating system and filesystem survive.
Distributed recovery, keyed change capture, stateful queries and the wider declarative
pipeline API require further integration. The [implementation contract](APPEND-RECOVERY.md)
explains the engineering choices and failure model.

## Declare the computation

From that implementation checkout, build the CLI with its default features and run:

```sh
cargo build --locked -p sail-cli
./target/debug/sail pipeline run --config pipeline.json
```

A declaration can look like this:

```json
{
  "version": 1,
  "pipeline_id": "orders-copy",
  "run_id": "initial-load",
  "source": {
    "path": "/data/orders",
    "start": {"kind": "snapshot"}
  },
  "target": "/data/orders-copy",
  "query": "SELECT * FROM input",
  "mode": "bounded"
}
```

The source must already be a Delta table. The target must be new and separate from
the source. The query reads the declared source as `input`. It can project columns
and filter rows using supported deterministic expressions. Current-time expressions,
stateful operators and additional inputs are refused. The default start is the current
snapshot. `{"kind": "latest"}` starts after the current end; `{"kind": "version", "version": 7}`
starts with that log version. The first declaration fixes this choice for the target.
Later source commits must be append-only. Data-changing removals and incompatible schema or protocol changes stop
the run instead of being interpreted as new rows.

Configuration is strict JSON. Unknown keys, duplicate keys, wrong types and conflicting
paths are errors. YAML and optional Dhall authoring remain planned frontends to the same
typed model; they are not accepted by this command yet.

## Distinguish a retry from a new request

`pipeline_id` names the fixed computation. `run_id` names the requested execution.
In bounded mode, the first execution saves the source's current end. Repeating the
same identifier resumes that saved range or returns its completed result, even if more
source data has arrived. After completion, choose a new identifier to capture and read
a later end. Reusing an older identifier never starts fresh work.

Set `mode` to `continuous` to keep reading later source commits in the same process.
Restart that process with the same declaration and identifier. It resumes from its
last published input position and finishes any prepared output first. Interrupting a
process does not declare its buffered output complete.

Keep the same executable for restart. The initial implementation conservatively binds
the saved definition to the runtime build, source, query and output schema. A changed
computation or executable is refused for that target. Migration between runtime builds
and computation generations is not implemented.

## Keep the required input and recovery files

The initial snapshot reader requires contiguous JSON transaction history. Once an input
segment has been saved, its file list and interpretation come from the saved manifest.
Restart still requires current table identity to be discoverable and all referenced
source data files to remain available. Source files must use canonical table-relative
paths; arbitrary external data files are not supported.

The target records ownership, prepared writes and completion in its Delta transaction
log. Its required writer feature makes ordinary Sail mutation commands refuse the table.
The dedicated pipeline writer checks ownership again when publishing. A replaced process
cannot regain ownership by retrying an append. Ordinary Sail Delta reads use their usual
interface.

There is no automatic recovery-file cleanup. Preserve the target's log, prepared output
and saved input manifests. Missing source files, or missing or changed saved output and
input metadata, stop recovery. Source data files are not rehashed on every read. The
contract assumes immutable committed source files and a stable filesystem namespace; it does not protect against arbitrary raw filesystem modification.

## Set operational limits

The optional `limits` object controls memory accounting, bytes per checkpoint, retained
recovery files, batch size, files per write, checkpoint interval and source polling.
These settings may change on restart without changing the computation. Raising a budget
can therefore recover from an explicit resource-limit failure.

| Setting | Default | Meaning |
| --- | --- | --- |
| `memory_bytes` | 268435456 | Execution memory accounting |
| `checkpoint_bytes` | 67108864 | Encoded output bytes per checkpoint |
| `retained_bytes` | 536870912 | Recovery directory, including published output |
| `batch_size` | 8192 | Maximum input rows per batch |
| `max_files_per_write` | 128 | Output chunks before requesting a checkpoint |
| `checkpoint_interval_ms` | 1000 | Periodic checkpoint interval |
| `poll_interval_ms` | 100 | Idle source polling interval |

For example, `"limits": {"retained_bytes": 2147483648}` raises the retained-file budget
to 2 GiB. It does not add automatic cleanup.

Memory accounting uses Sail's execution pool; it is not an operating-system RSS limit.
The retained-file budget counts preparation, saved input metadata and published output
under the recovery directory. Separate limits bound temporary spill and log history.
A hard disk quota across overlapping processes requires a filesystem quota. Exhaustion
stops the attempt without treating unwritten rows as complete.
