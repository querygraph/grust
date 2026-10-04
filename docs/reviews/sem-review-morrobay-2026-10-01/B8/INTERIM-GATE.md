# B8 interim publication gate preparation

This is a source and historical metadata gate. No detached publication candidate or committed report has been gated yet. No engines, Docker, native build, input payload, raw result or reference array is executed or reread by this helper.

## Exact handoff

Copy these prepared files into `docs/reviews/sem-review-morrobay-2026-10-01/B8/` in querygraph/grust:

- `INTERIM-FINDINGS.md`
- `interim-findings.json`
- `interim-evidence-pins.json`
- `sem_b8_interim_gate.py`
- `test_sem_b8_interim_gate.py`
- `interim-source-controls.json`
- `INTERIM-GATE.md`

The external `sem-b8-interim-v2-source-manifest.json` pins those exact repository-relative names, byte lengths and SHA256 values. It is a gate input, separate from the tracked files, so it has no hash cycle. The separate codex entry file is also pinned by the gate receipt. Root owns the actual append, candidate creation, commit and push. Any source correction requires a new manifest and fresh candidate/receipt; retain each failed attempt.

## What the gate proves

`sem_b8_interim_gate.py` requires the actual clean checkout to be detached at the supplied full commit, tree and single parent. The tree delta must contain exactly the external manifest's files plus `codex-to-codex.md`. Every file must match its exact source blob/hash and regular `100644` mode. The codex file must equal its parent's complete bytes followed by the exact pinned owned entry. It checks its own module origin.

It then checks all 273 historical metadata/source pins before and after derivation: both original queues, generated-queues02 plan and configuration provenance, all 30 Cit-Patents host/producer/engine/container/bootstrap/collection/removal/plan records, reference/admission receipts, frozen helpers, natural-OOM audit and the preserved lock owners. JSON byte identities and original top-level key order are frozen. There are no `.parquet`, `.i64`, native binary or raw archive reads; total metadata/source bytes are 18,458,269.

The derivation requires all 30 qualified Cit-Patents cells and their unchanged embedded original receipts, full-oracle pass metadata, closed archive/container evidence and actual envelope. It recomputes both ratio families and block formulas from raw records. Graph500's original 30-record queue must retain its first failed/unqualified warmup and 29 completely untouched pending entries. The prior full OOM payload/archive audit is cited by its exact hash; this gate does not replace or rerun it. Preserved original owner PIDs and byte hashes must match the original failure/preservation proofs.

The report must equal the recomputation and remain `b8_interim_incomplete`, `incomplete=true`, `all60_done=false`. The gate cannot qualify an engine, a new payload scan, a continuation/tail mapping or an all 60 complete publication.

## Root-owned candidate and committed gates

Create one detached worktree for the exact staged candidate and another for the exact committed report, each naming its actual tree and parent. Gate outputs and tool caches stay outside those worktrees. Use the supplied source manifest and pinned codex entry unchanged. The helper writes a fresh atomic/fsynced external receipt and retains an error verdict/traceback on an admitted failure. It runs read-only Git commands only.

For each exact worktree, root supplies the task-specific variables below from the actual candidate or committed object and invokes:

```sh
/tmp/sem-output-oracle-venv/bin/python -B \
  "$b8_report_worktree/docs/reviews/sem-review-morrobay-2026-10-01/B8/sem_b8_interim_gate.py" \
  --repo "$b8_report_worktree" \
  --commit "$b8_report_commit" --tree "$b8_report_tree" --parent "$b8_report_parent" \
  --manifest /tmp/sem-b8-interim-v2-source-manifest.json \
  --manifest-sha256 "$b8_report_manifest_sha256" \
  --codex-entry /tmp/sem-b8-interim-v2-codex-entry.md \
  --codex-entry-sha256 "$b8_report_codex_entry_sha256" \
  --output "$b8_report_fresh_gate_receipt"
```

Repository Ruff, strict mypy and the ten bounded controls must gate the same source files. Keep the commit conditional on all candidate gates, then independently gate the exact committed object before push. Do not use the frozen complete B8 publication helper for this interim package: it does not understand future tail skips/mappings. Do not label the task all 60 DONE.

## Numerical formulas and limits

The main ratio is `median(A)/median(U)` over four measured cells per form, with six total warmups excluded. Engine-child monotonic Popen→completed-wait duration and queue host-driver wall-clock Popen→completed-wait duration are separate fields and summaries. Block ratios of geometric means are `gmean(A_block)/gmean(U_block)`; block median ratios and the geometric mean of those two ratios are separately named in JSON.

Raw seconds/bytes are retained diagnostics for reconstruction. Shared-host prose reports dimensionless ratios. Enabled explain and preparation are inside the engine boundary; full oracle/archive work is outside that boundary but inside host-driver wall time. No kernel-only, absolute performance, native fit, generic 32 GiB, Graph500 qualified ratio or OOM allocation-attribution claim follows.

## v2 configured-quota correction

Frozen preparation01 remains unchanged. v2 replaces the factual native-prepayment claim in prose, machine execution scope and gate Literal/derivation with configured quota wording. Required machine fields retain configured_native_quota_bytes=268435456, native_reservation_observed=false and actual_native_prepaid_bytes=null. Actual reservation/prepayment and allocated bytes remain unobserved/pending. The exact config/source/envelope/full-oracle/closure/timing predicates and all 273 historical metadata pins are unchanged; no numeric result or raw receipt was rewritten. The tenth bounded control refuses inferred observed prepayment. Source preparation controls do not replace root-owned detached candidate/committed gates.
