# Post-sequence physical checks for the six-cell host pair

Recorded UTC: 2026-09-30T23:47:34.823593+00:00

This is a prepared handoff recipe, not execution authorization. Complete and
collect **all six trials first**. Do not read/hash their output payloads between
trials: that would change the cache/workload boundary. No actual pair collection
or campaign output was read while preparing this recipe.

The existing collection verifier's `ratio_eligible` means the pinned recorded
reference/parent checks and collection/metric requirements passed. It does not
include an independent read of physical output values. Preserve that verdict and
all raw times. The additional qualification requires all six physical checks,
including both warmups, on their exact producer-hashed outputs.

## Pinned code and plan

| File | SHA-256 |
|---|---|
| `host-pair-collection-audit/audit_pair.py` | `6a377820d65649a72ce4317da11e13245e404109deaa1eef573edff262816987` |
| `closed-cell-audit/audit_cell.py` | `c8d59db362136879bbd3a6efe8f527311849e3e0be18ddb64e6da996bdfcd318` |
| `physical-output-audit/audit_output.py` | `4c5fe87d0eb0b3f4aec3e70841bc7db968017f952dda6978840d101d2f2f7872` |
| `host-pair-16k/run_host_pair.py` | `8220b9951c51420bd34ca5e32ba20c2304a1b863aa5f2fa1fa9467e74d60a7f1` |
| `host-pair-16k/pair16k-20260930201356-plan.json` | `d51e9f4d5a1d16fb18c36e93fcb3d641c017610a7319ee56a203676800dbe1ab` |

The plan binds six distinct configuration hashes, the original controller
`3a9028057c6c6c5034492845926fc4bc18f9626f`, native source `ffcfbd569`, weighted16k
input and both host binaries. Order is warmup A/B, then measured A/B/B/A. The
`prepared()` function verifies all six configuration hashes and their parity;
do not replace these with the earlier smoke configuration.

## Export full closed-cell audit objects

`audit_pair.py:183` calls `h.audit(cell, profile, EXP)`, but its returned cell
summary at lines 195–200 keeps only part of that object. Its top-level
`evidence_files` merges every cell's files. Therefore `pair_report['cells'][i]`
is **not** a complete closure input for the physical helper.

Re-run the unchanged closed-cell helper locally with the exact profile
construction from `audit_pair.py:180–182`. This produces a new audit of already
collected metadata/archive bytes; it does not recover a previously serialized
object or read result Parquet. The helper's original return at
`audit_cell.py:285` includes `files`, `helper_sha256`, `recorded_outcomes`, closure
and integrity status. Serialize that return directly, with a unique output
name outside the collected evidence, then pin its SHA-256.

The following shows the exact extraction. Substitute already reviewed local
paths and use the pinned Python 3.12 environment. A failed assertion is a stop;
retain the outer command/error and any reports already written. Do not change
the frozen verifier/helper/configuration files.

```python
import hashlib
import importlib.util
import json
from pathlib import Path

EXP = Path("/Users/alexy/src/grust/docs/reviews/sail-stream-experiments-2026-09-30")
COLLECTION = Path("<closed local pair16k-20260930201356 mirror>").resolve()
OUT = Path("<new post-sequence audit directory>").resolve()
assert not OUT.is_relative_to(COLLECTION)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return sha(path)

path = EXP / "host-pair-collection-audit/audit_pair.py"
assert sha(path) == "6a377820d65649a72ce4317da11e13245e404109deaa1eef573edff262816987"
spec = importlib.util.spec_from_file_location("frozen_pair", path)
pair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pair)
h = pair.support()
plan, configs = pair.prepared(h)
OUT.mkdir(exist_ok=False)
pair_report = pair.audit_collection(COLLECTION)
pair_sha = save(OUT / "pair-collected-evidence.json", pair_report)
assert pair_report["integrity_status"] == "integrity_verified"
assert len(pair_report["cells"]) == 6

exports = []
for entry, config in zip(plan["runs"], configs):
    cell = COLLECTION / "cells" / config["run_id"]
    profile = dict(
        config_path="host-pair-16k/" + entry["configuration"],
        evidence_pins=[], binary_sha256=entry["binary_sha256"],
        native_identity_canonical_sha256=h.canonical(plan["expected_native_package_identity"]),
        dataset_canonical_sha256=h.canonical(plan["expected_dataset"]),
        resolved_dataset_path=plan["expected_arguments"]["dataset"],
    )
    closed = h.audit(cell, profile, pair.EXP)
    closed_path = OUT / f"{entry['order']:02d}-closed-cell.json"
    closed_sha = save(closed_path, closed)
    assert closed["integrity_status"] == "integrity_verified"
    assert not closed["errors"] and not closed["inconclusive_reasons"]
    receipt_path = cell / "diagnostics/receipt.json"
    receipt_pin = closed["files"][str(receipt_path)]
    exports.append(dict(
        order=entry["order"], run_id=config["run_id"],
        closure_audit=str(closed_path), closure_sha256=closed_sha,
        receipt=str(receipt_path), receipt_sha256=receipt_pin["sha256"],
        expected_cell_output=entry["cell_output"],
        original_result_path=entry["cell_output"] + "/result",
        expected_vertices=16384, expected_source=0,
    ))

# Retain the complete pair audit's stable-input condition through extraction.
for name, pin in pair_report["evidence_files"].items():
    assert not Path(name).is_symlink() and h.file_info(Path(name)) == pin
pair.prepared(h)
assert sha(path) == pair_report["verifier_sha256"]
assert sha(EXP / "closed-cell-audit/audit_cell.py") == pair.HELPER_SHA
save(OUT / "physical-check-inputs.json", dict(
    pair_audit_sha256=pair_sha, plan_sha256=pair.PLAN_SHA, cells=exports,
    scope="Prepared exact physical-check bindings; no payload scan performed by extraction",
))
```

`pair_report['ratio_eligible']` may be false for a legitimately closed failed
trial. Do not assert that it is true merely to export the receipts. Closure and
integrity are distinct from the benchmark outcome.

## Read the six physical outputs and retain both verdict layers

After resource admission, call the frozen physical helper once per export using
its exact receipt/closure hashes, namespace, N=16,384 and source=0. Use the
retained result path through a read-only mount, or a separately verified copy;
only `--result-dir` may change for a copy. The producer's original namespace and
file hashes must remain the same. Verify the physical helper hash above before
each call and keep its output outside retained inputs. Keep separate output
receipts and outer exit/failure records for every cell, including failures.

The inventory and resource/mount restrictions in
[the physical helper README](physical-output-audit/README.md) apply. Result
Parquet is absent from the diagnostic archives; receipt hashes alone cannot
substitute for those payloads. None of the six physical checks adds a graph edge
or Dijkstra computation, and none may be moved into the timed sequence.

Preserve the collection verifier's original ratio fields. Separately record:

```text
supplemental_physical_qualification =
    original_pair_ratio_eligible
    AND six distinct planned namespaces are bound to their recorded payloads
    AND every physical check has status physical_values_pass
    AND all consumed report/helper/input hashes remain unchanged
```

A physical failure blocks that supplemental qualification. Missing payload,
missing closure, wrong schema/hash, an interrupted check or partial collection
does not count as a pass. Never replace the original benchmark outcome or erase
raw times/ratios to express this qualification.

Even after all six pass, these remain descriptive ratios on the shared host:
two measured samples per runtime, sampled execute PSS, whole-VM/whole-trial steal,
and no per-cell macOS closure pressure deltas. Physical checks add no dedicated
host, quiet-host, runtime-only causality, peak-memory or full independent graph
correctness claim.
