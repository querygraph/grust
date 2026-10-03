# Documentation metadata gate

Source only. Ruff, formatting and strict mypy passed in
`source-gates02/receipt.json`; the initial import-order failure is preserved.
No actual report gate, Git mutation, Rust gate, engine or process probe was run.

The exact `Plan` schema is `plan-schema.json`. The repository is fixed at
`/Volumes/Apo/graph-tests/workspaces/sem-completion-20261003/grust-report`;
portable manifests and archives must be under its
`docs/reviews/sem-completion-2026-10-03` report tree. Root supplies actual pins.

- `mode`: `candidate` or `committed`.
- `commit`: actual detached HEAD SHA; `base_commit`: the unchanged source
  baseline before the documentation changes; `tree`: the exact admitted tree.
- `changed_files`: every path in base-to-tree diff, mapped to `{bytes,sha256}`
  or null for an actual deletion. Only `docs/` and `codex-to-codex.md` are admitted.
- `helpers`: exact `doc_models.py` and `doc_gate.py` identities.
- `manifests`: full FilePins of unpacked portable package manifests. The
  `packaged_closed_metadata_only` schema contains `observed_utc`, `topic`,
  `members` with relative `path`, `original`, `bytes`, `sha256`, declared
  `excluded_payload_pins`, and `scope`. Excluded pins are declarations, never
  opened or rehashed by this gate.
- `archives`: actual archive FilePins, named `*.tar.gz`. Each is hashed without
  extraction, with a64MiB admission bound. Raw archive catalogs can be ordinary
  manifest members; archived JSON/log content is not reparsed by this gate.
- `primary_markdown`: explicit repository-relative main Markdown files whose
  local links are required. Archived historical handoffs/sketches are not used
  as primary Markdown. HTTP links and fragment-only links are outside the local
  file check; local links must resolve within the portable checkout.
- `observed_claims`: `{name,evidence,expected_fields,scope}`. Evidence is a
  portable JSON FilePin; expected fields use dotted **object** keys and exact
  JSON values/types. Include each reported pass/failure/unavailable or unresolved
  status as appropriate. This checks the explicitly bound observed fields; it
  does not infer completion from a report title or reinterpret historical raw
  clocks. The root owns factual/editorial review and must keep unresolved X1/X2
  historical causes explicit.
- `output`: a fresh verdict directory directly under the completion evidence
  root. The helper refuses an existing directory and preserves every failed run.

Run from a root-owned short-lived command; these metadata checks need no Rust
crate gates or engine reruns:

```sh
/tmp/sem-output-oracle-venv/bin/python -I -B -c \
  'import runpy,sys;r=sys.argv[1];sys.path.insert(0,r);sys.argv=[r+"/doc_gate.py"]+sys.argv[2:];runpy.run_path(sys.argv[0],run_name="__main__")' \
  /Volumes/Apo/graph-tests/results/sem-completion-20261003/report-metadata-gate01 \
  --plan /ABSOLUTE/FRESH/PLAN.json
```

Actual Git HEAD, detached status, cached/working diff against the admitted tree,
untracked-source absence, exact changed-file set, source diff checks, coordination
conflict markers, changed/copied JSON parsing, member bytes/SHA, archive identities,
main Markdown links, explicit observed fields and final file/tree closure are
required. File hashing is limited to64MiB metadata/archive files; JSON parsing is
limited to16MiB unpacked JSON, so large original action JSON belongs in archives.

Positive candidate outcome: `passed_candidate_documentation_metadata`, naming
the actual **base commit plus staged tree**. Root must make commit conditional on
this gate in one `&&` chain, then prepare a fresh final plan/verdict for the clean
exact committed revision. Final outcome: `passed_committed_documentation_metadata`.
The receipt records observed UTC, mode, actual commit/tree, detached source before
and after, repository, helper/configuration pins, individual checks, files, errors
and explicit metadata-only scope. Exit0 requires that positive exact verdict.
Nothing in this helper commits or publishes.
