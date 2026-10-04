#!/usr/bin/env python3
"""Read retained Morrobay receipts; do not launch or mutate remote work."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


BENCHMARK = Path('/Users/alexy/src/sail-large-graphs/examples/extensions/benchmarks')
sys.path.insert(0, str(BENCHMARK))
from run_matrix import classify, plan_cells
from summarize import integrity_errors, tables


remote = r'''
import json
from pathlib import Path
base=Path.home()/'src/sail-extensions-gates'
locations = {
 'uncertified_push_pull': ('graph-nuts-b87fb27ac/capacity-hub', 'capacity-bfs-r1-scale25-pecan-bfs-push_pull'),
 'uncertified_grenada_push_pull': ('graph-nuts-b87fb27ac/capacity-hub', 'capacity-bfs-r1-scale25-nutmeg-datafusion-bfs-push_pull'),
 'uncertified_grenada_frontier': ('graph-nuts-b87fb27ac/capacity-hub', 'capacity-bfs-r1-scale25-nutmeg-datafusion-bfs-frontier'),
 'certified_frontier': ('graph-nuts-b87fb27ac/capacity-hub', 'capacity-bfs-r1-scale25-pecan-bfs-frontier'),
 'certified_banda_gate3': ('graph-nuts-gate-next/decide-gate3', 'decide-banda-s24-sssp-r1-scale24-nutmeg-native-sssp-delta_star'),
 'argentea_cap': ('graph-nuts-gate-next/decide-gate3', 'decide-argentea-s24-sssp-r1-scale24-argentea-sssp-delta_star'),
 'near_limit_without_event': ('graph-nuts-b87fb27ac/capacity-hub', 'capacity-bfs-r1-scale24-nutmeg-datafusion-bfs-frontier'),
}
result={}
for label,(matrix,cell) in locations.items():
 root=base/matrix
 directory=root/'cells'/cell
 path=directory/'artifacts/receipt.json'
 receipt=json.loads(path.read_text())
 summary=json.loads((directory/'summary.json').read_text())
 record=dict(receipt_path=str(path), summary_path=str(directory/'summary.json'),
             receipt=receipt, summary=summary)
 if label.startswith('certified'): record['configuration']=json.loads((root/'configuration.json').read_text())
 if label=='argentea_cap':
  record['native_cap_records']=[]
  for line in (directory/'artifacts/server.log').open():
   if 'ARGENTEA_RECEIPT ' in line and 'sssp_round_cap' in line:
    record['native_cap_records'].append(json.loads(line.split('ARGENTEA_RECEIPT ',1)[1]))
 result[label]=record
print(json.dumps(result))
'''
completed = subprocess.run(['ssh', 'morrobay', 'python3', '-'], input=remote, text=True,
                           capture_output=True, check=True, timeout=60)
records = json.loads(completed.stdout)
compact = {}
for label, record in records.items():
    receipt = record['receipt']
    compact[label] = {
        'receipt_path': record['receipt_path'],
        'summary_path': record['summary_path'],
        'harness_source_sha': receipt.get('harness_source_sha'),
        'receipt_outcome': receipt.get('outcome'),
        'summary_outcome': record['summary'].get('outcome'),
        'end_to_end_seconds': receipt.get('end_to_end_seconds'),
        'elapsed_until_error_seconds': receipt.get('elapsed_until_error_seconds'),
        'correctness': receipt.get('correctness'),
        'execute_peaks': receipt.get('memory', {}).get('phase_peaks', {}).get('execute'),
        'cgroup_memory_events': receipt.get('cgroup_after', {}).get('memory.events'),
        'error_last_line': receipt.get('error', '').splitlines()[-2:],
    }
    if label.startswith('uncertified'):
        compact[label]['decode_error_lines'] = [line for line in receipt.get('error','').splitlines()
                                               if 'decoded message' in line]
    if label == 'argentea_cap':
        compact[label]['native_cap_records'] = record['native_cap_records']
        compact[label]['classify_result'] = classify(
            {'transport_errors': []}, receipt, receipt['harness_source_sha'])
    if label.startswith('certified'):
        config = record['configuration']
        cell = next(cell for cell in plan_cells(config)
                    if cell['cell_id'] == record['summary']['cell_id'])
        compact[label]['actual_summarizer_integrity_errors'] = integrity_errors(
            cell, record['summary'], receipt, config)
        compact[label]['manifest_file_count'] = len(receipt['dataset']['files'])
        compact[label]['manifest_file_examples'] = list(receipt['dataset']['files'])[:3]
try:
    tables([{'suite':'proof','dataset':'fixture','mode':'process-cluster',
             'algorithm':'bfs','engine':'argentea','variant':'reference',
             'metrics': {}, 'outcomes': {'error': 1}}])
except KeyError as error:
    argentea_tables_error = repr(error)
else:
    raise AssertionError('Argentea table rendering unexpectedly succeeded')
target = Path(__file__).with_suffix('.json')
evidence = {'generated_utc': datetime.now(timezone.utc).isoformat(), 'host':'morrobay',
            'certification_scope': 'The three uncertified records are baseline b87fb27ac cells only. '
                'grust/docs/reviews/gn-capacity-2026-09-29.md:247-254 separately records a later '
                'gate2 Grenada scale25 push-pull certificate pass at 1593 seconds and a Pecan '
                'frontier pass at 2746 seconds. These baseline records do not refute those passes.',
            'summarizer_checkout_sha': subprocess.check_output(
                ['git','-C',str(BENCHMARK),'rev-parse','HEAD'], text=True).strip(),
            'records': compact, 'argentea_tables_error': argentea_tables_error}
target.write_text(json.dumps(evidence, indent=2) + '\n')
print(json.dumps({'artifact':str(target), 'records':len(compact),
                  'argentea_tables_error':argentea_tables_error,
                  'passed_cell_integrity_errors':compact['certified_banda_gate3']['actual_summarizer_integrity_errors']}))
