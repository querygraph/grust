# Report metadata plan generator

Source preparation only. No actual plan, Git mutation or documentation gate ran during authoring. Root supplies the admitted detached commit, baseline and tree after staging the final docs.

## Root configuration

Pass `--config ABSOLUTE_JSON` with these fields:

```json
{
  "mode": "candidate or committed",
  "commit": "actual detached HEAD, 40 lowercase hex",
  "base_commit": "root-selected pre-report baseline, 40 lowercase hex",
  "tree": "actual admitted staged or committed tree, 40 lowercase hex",
  "root": "/Volumes/Apo/graph-tests/results/sem-completion-20261003/report-plan-FRESH-ID",
  "output": "/Volumes/Apo/graph-tests/results/sem-completion-20261003/REPORT-GATE-FRESH-ID",
  "primary_markdown": []
}
```

`configuration-schema.json` is the strict typed contract. Both result directories must be fresh, disjoint direct children of the completion root. The exact fixed report checkout is `/Volumes/Apo/graph-tests/workspaces/sem-completion-20261003/grust-report`. An empty primary list selects the primary report README and each immediate child README; root may explicitly supply another safe repository-relative list.

## Invocation

Use the source-gated metadata Python and include the exact frozen gate directory in the isolated bootstrap:

```text
/tmp/sem-output-oracle-venv/bin/python -I -B -c 'import runpy,sys;sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[2]);sys.argv=[sys.argv[2]+"/make_plan.py"]+sys.argv[3:];runpy.run_path(sys.argv[0],run_name="__main__")' /Volumes/Apo/graph-tests/results/sem-completion-20261003/report-metadata-gate01 /Volumes/Apo/graph-tests/results/sem-completion-20261003/report-metadata-plan01 --config ABSOLUTE_JSON
```

The generator writes fresh `root/plan.json` and `root/receipt.json`. Positive sealing is `sealed_documentation_metadata_plan` with a hash-bound plan. Root then runs the separate frozen `doc_gate.py --plan root/plan.json`. Sealing is not a gate pass. Candidate tree/worktree admission and the final clean committed SHA remain the actual documentation gate's responsibility. The conditional commit and final committed gate remain root-owned.

## Inventory and observed fields

The changed map comes from actual `git diff --name-only -z BASE TREE`, limited to docs and the coordination log; changed physical files are SHA-bound and deletions are explicit. Exactly six copied topic manifests are admitted: C2-D2-C4, C3, X2, E0, F2 and Vortex. Every copied `.tar.gz` is pinned within the report, at most64MiB. The strict gate will subsequently verify manifest members, JSON bounds and primary Markdown destinations.

Fourteen named JSON objects bind actual retained observations: C2/D2/C4 counts and false stronger qualifications, C3 ledger scope, X2 successful tiny controls and all12 unexplained historical causes, E0 retained gate/independent reviews, F2 eight-output qualification and archive identity, and all three Vortex success/not-admitted profiles including recorded unsupported writer attempts. Expected values are read from actual hash-bound JSON; no expected success or source-dependent observer revision is substituted. The plan seals exact fields, rather than inferring prose completeness. Source/model/freeze/config/changed files/manifests/archives/evidence and HEAD are checked again before saving.

No code, engine, memory, complete causal explanation or all-Sem verdict is produced. Original absolute clocks remain archival shared-host observations. Detailed observer source/build/collector work remains separately qualified.
