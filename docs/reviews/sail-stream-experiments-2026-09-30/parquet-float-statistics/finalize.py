from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = Path('/private/tmp/sail-parquet-float-statistics')
GATE = Path('/private/tmp/sail-parquet-float-statistics-gate')
BASE = '200d1cf8eb1db5e9057e09e071ebd57391f4b376'
TREE = '7063e31260100901bd43d8820c4e1e733aa99605'

def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root).decode().strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

head = git(ROOT, 'rev-parse', 'HEAD')
assert git(ROOT, 'rev-parse', 'HEAD^') == BASE
assert git(ROOT, 'rev-parse', 'HEAD^{tree}') == TREE
assert git(GATE, 'rev-parse', 'HEAD') == head
assert not git(ROOT, 'status', '--porcelain') and not git(GATE, 'status', '--porcelain')
exact = json.loads((OUT/'exact-gate/receipt.json').read_text())
candidate = json.loads((OUT/'candidate-gate02/receipt.json').read_text())
baseline = json.loads((OUT/'baseline02/baseline-receipt.json').read_text())
audit = json.loads((OUT/'independent-source-audit-v2.json').read_text())
assert exact['outcome'] == candidate['outcome'] == 'PASS'
assert exact['before'] == exact['after'] and exact['before']['head'] == head
assert baseline['outcome'] == 'EXPECTED_REGRESSION_FAILURE'
assert audit['frozen_index_tree'] == TREE
assert '77 passed; 0 failed' in (OUT/'exact-gate/tests.log').read_text()
record = dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='PASS_EXACT_COMMIT',repository='querygraph/sail',branch='work/parquet-float-statistics',commit=head,parent=BASE,tree=TREE,delivery='NOT_PUSHED',
    verdict=f'PARQUET_FLOAT_STATISTICS_GATE PASS {head} exact commit',
    scope='Local Rust data-source library; no Spark Connect/server/worker, Linux, production performance or full Parquet correctness qualification.',
    tests=dict(full_library_passed=77,new_tests=5,real_sail_metadata_and_scan_cases=29,scalar_float_types=['Float16','Float32','Float64'],dictionary_value_types=['Float32','Float64'],dictionary_key='Int32',unsupported='Dictionary(Int32, Float16) reader rejects before Sail scan; writer and metadata helper support do not imply readback support',baseline='Unchanged production parent plus identical final readback test module: 2 expected failures NaN became 0.5; 2 controls pass. Loops stop on first failing case (scalar Float16 and dictionary Float32); baseline does not independently enumerate all types.'),
    semantics='Clear floating and dictionary-floating min/max only before listing statistics caching/aggregation. Preserve row/byte/null counts, footer-supplied NDV, integer and other nonfloating metadata; all-null inference remains possible.',
    tradeoff='Floating file-level metadata MIN/MAX, constant-column substitution and range/equivalence simplifications lose bounds, including finite-only files. No timing or optimization cost measured.',
    exclusions=['Raw footer row-group/page pruning', 'Footer-derived ordering', 'Nested leaf statistics', 'Other reader paths', 'Cache entries injected outside this normalized path; no retroactive cache migration'],
    failures_retained=['initial-tests.log: fixture imports/Constraints API compile failure','initial-tests02.log: unsupported Dictionary(Float16) assumption','candidate-gate/clippy.log: denied unwrap calls in tests, replaced by Result propagation without weakening assertions','baseline.log and baseline02/baseline.log: intentional regression failures'],
    target_seed='APFS copy of idle /private/tmp/sail-compact-struct-min-target (exact56194 gate); private candidate target, then private baseline copy after exploratory candidate stopped. See preflight and baseline receipt.',
    receipts={name:sha(OUT/name) for name in ['candidate.patch','baseline02/baseline-receipt.json','candidate-gate02/receipt.json','precommit-guard.json','exact-gate/receipt.json','independent-source-audit-v2.json']},
    compiler=subprocess.check_output(['rustc','--version'],text=True).strip(),cargo=subprocess.check_output(['cargo','--version'],text=True).strip())
(OUT/'final-receipt.json').write_text(json.dumps(record,indent=2)+'\n')
readme=f'''# Parquet floating file-statistics mitigation

Sail fork branch `work/parquet-float-statistics`, commit `{head}`, parent `{BASE}`. Local exact detached gate passed; this receipt cutoff is **not pushed**.

The unchanged parent source reads a NaN as `0.5` from real Parquet bytes with equal finite footer bounds. An independent Parquet decoder in the same test first verifies that the stored values include NaN. The [matched baseline](baseline02/baseline.log) retains two expected regression failures and two passing controls. The scalar loop fails first at Float16 and the dictionary loop at Float32; it does not enumerate later baseline cases after the assertion fails.

The patch clears floating min/max at Sail's Parquet `infer_file_meta` boundary, before file-statistics caching and aggregation. It covers Float16/32/64 and dictionary value types. Counts, null counts, byte sizes, explicit footer NDV and nonfloating bounds remain intact. DataFusion's footer extraction reads NDV independently; the test pins preservation rather than claiming the footer always contains it. See [source inspection](source-inspection.json) and [final independent source review](independent-source-audit-v2.json).

[Candidate gate](candidate-gate02/receipt.json) and [exact-commit gate](exact-gate/receipt.json): package formatting, strict all-target Clippy, and **77 library tests**. Five new tests include 29 actual metadata-plus-scan readbacks: scalar Float16/32/64 and Dictionary(Int32, Float32/64), mixed NaN/constant finite values, reversed order, all NaNs, signed zero, finite constants, nulls and integers. Float16 dictionary readback is explicitly unsupported by pinned Parquet 59.3; the original failed assumption and a control pinning the reader error are retained. These are local library tests, not a rebuilt Spark server/worker or Linux qualification.

Floating file-level metadata MIN/MAX, constant substitution and range/equivalence simplification lose optimization opportunities, including finite-only files. Count/all-null and integer metadata remain usable. No runtime cost is measured. Raw footer row-group/page pruning, ordering, nested leaf statistics and other readers remain outside this fix. Cache entries injected outside the normalized path are not retroactively sanitized; normal Sail misses and later hits originate from normalized metadata.

Failures remain in [first compile](initial-tests.log), [unsupported dictionary assumption](initial-tests02.log), [first strict lint gate](candidate-gate/clippy.log), and both [initial](baseline.log) and [final matched](baseline02/baseline.log) baseline reproductions. The lint fix uses Result propagation; it does not suppress lints or weaken assertions. The macOS linker reports an existing oversized unwind-section warning during tests; no test fails on it. Targets were private APFS copies of an idle seed, with incremental compilation disabled and disk preflight retained. No registry edits or remote operations occurred.

Reproduction: [baseline runner](run_baseline02.py), [detached gate driver](run_gate.py), [precommit source/receipt guard](verify_candidate.py), and [final receipt](final-receipt.json). The conditional commit command is retained in [commit chain](conditional-commit-command.txt). Plans and evidence are in Grust only.
'''
(OUT/'README.md').write_text(readme)
files={str(p.relative_to(OUT)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'artifact-manifest.json'}
(OUT/'artifact-manifest.json').write_text(json.dumps(dict(recorded_utc=datetime.now(timezone.utc).isoformat(),commit=head,files=files),indent=2)+'\n')
print(record['verdict'])
print('artifact files',len(files))
