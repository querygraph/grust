"""Admit only six fully closed, source-pinned planned trials before any scan."""
import hashlib
import json
from pathlib import Path

PLAN_SHA = 'd51e9f4d5a1d16fb18c36e93fcb3d641c017610a7319ee56a203676800dbe1ab'
PAIR_SHA = '6a377820d65649a72ce4317da11e13245e404109deaa1eef573edff262816987'
CLOSED_SHA = 'c8d59db362136879bbd3a6efe8f527311849e3e0be18ddb64e6da996bdfcd318'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def closed_ok(closed):
    need(closed.get('integrity_status') == 'integrity_verified' and closed.get('errors') == []
         and closed.get('inconclusive_reasons') == [], 'closed integrity evidence incomplete')
    need(closed.get('helper_sha256') == CLOSED_SHA, 'closed helper differs')
    state = closed.get('recorded_outcomes', {}).get('docker_state', {})
    need(state.get('Running') is False and state.get('Status') == 'exited', 'producer not exited')


def all_six(evidence, plan):
    pair = evidence['pair_audit']
    need(pair.get('integrity_status') == 'integrity_verified' and pair.get('errors') == []
         and pair.get('inconclusive_reasons') == [], 'complete pair integrity required')
    need(pair.get('plan_sha256') == PLAN_SHA and pair.get('verifier_sha256') == PAIR_SHA
         and pair.get('helper_sha256') == CLOSED_SHA, 'pair audit source differs')
    rows = pair.get('cells'); exports = evidence.get('cells')
    need(isinstance(rows, list) and len(rows) == 6 and isinstance(exports, list) and len(exports) == 6, 'all six cells required')
    need(type(pair.get('ratio_eligible')) is bool, 'original ratio verdict missing')
    namespaces = set()
    for entry, row, exported in zip(plan['runs'], rows, exports):
        need(row['order'] == exported['order'] == entry['order'] and
             row['host'] == entry['host'] and row['phase'] == entry['phase'], 'six-cell order differs')
        need(row['integrity_status'] == 'integrity_verified' and row['errors'] == [] and row['inconclusive_reasons'] == [], 'cell integrity incomplete')
        need(exported['cell_output'] == entry['cell_output'] and exported['configuration_sha256'] == entry['configuration_sha256']
             and exported['binary_sha256'] == entry['binary_sha256'], 'planned cell binding differs')
        need(exported['expected_vertices'] == 16384 and exported['expected_source'] == 0, 'physical domain differs')
        need(exported['cell_output'] not in namespaces, 'repeated cell namespace'); namespaces.add(exported['cell_output'])
        closed = exported['closed_audit']; closed_ok(closed)
        need(closed['recorded_outcomes'] == row['recorded_outcomes'], 'full export differs from pair audit')
        need(any(name.endswith('/diagnostics/receipt.json') and pin.get('sha256') == exported['receipt_sha256']
                 for name, pin in closed.get('files', {}).items()), 'full closure does not pin producer receipt')
        need(any(pin.get('sha256') == entry['configuration_sha256'] for pin in closed['files'].values()), 'closure config differs')
        need(exported['boot_id'] == row['sequence_row']['boot_id'], 'observed boot differs')
    return exports


def validate_context(request, root):
    need(sha(root / 'pair-plan.json') == PLAN_SHA, 'plan differs')
    plan = json.loads((root / 'pair-plan.json').read_text())
    evidence = json.loads((root / 'all-six-closures.json').read_text())
    exports = all_six(evidence, plan)
    matches = [x for x in exports if x['cell_output'] == request['cell_output']]
    need(len(matches) == 1, 'cell not in complete planned sequence')
    item = matches[0]; entry = plan['runs'][item['order'] - 1]
    need(request['expected_vertices'] == 16384 and request['expected_source'] == 0, 'request domain differs')
    need(request['files']['configuration.json']['sha256'] == entry['configuration_sha256']
         and request['binary_sha256'] == entry['binary_sha256'], 'requested configuration/runtime differs')
    need(request['files']['producer-receipt.json']['sha256'] == item['receipt_sha256'], 'requested producer receipt differs')
    need(json.loads((root / 'closed-audit.json').read_text()) == item['closed_audit'], 'requested full closure differs')
    need(request['boot_id'] == exports[-1]['boot_id'], 'checker must use final observed VM boot')
    c = json.loads((root / 'configuration.json').read_text())
    r = json.loads((root / 'producer-receipt.json').read_text())
    need(c['container_sail_binary'] == plan['hosts'][entry['host']]['binary']
         and c['runtime_source_sha'] == plan['hosts'][entry['host']]['source'], 'host A/B runtime binding differs')
    for key in ('runtime_source_sha', 'native_source_sha', 'harness_source_sha'):
        need(r.get(key) == c[key], 'producer source differs: ' + key)
    args = r.get('arguments', {})
    need(args.get('output') == item['cell_output'] and args.get('source') == 0 and args.get('expected_vertices') == 16384
         and args.get('algorithm') == 'sssp' and args.get('engine') == 'pecan' and args.get('variant') == 'frontier', 'producer arguments differ')
