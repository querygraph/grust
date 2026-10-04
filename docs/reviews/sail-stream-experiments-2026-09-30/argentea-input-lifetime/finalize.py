"""Bind unchanged baseline counters, exact-source tests, and final artifact receipt."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
out=Path(__file__).parent;repo=Path('/private/tmp/sail-argentea-owned-input');gate=Path('/private/tmp/sail-argentea-owned-input-gate')
def git(root,*a):return subprocess.check_output(['git','-C',str(root),*a],text=True).strip()
def save(path,data):
 with path.open('x') as f:json.dump(data,f,indent=2);f.write('\n')
head=git(repo,'rev-parse','HEAD');tree=git(repo,'rev-parse','HEAD^{tree}');base='200d1cf8eb1db5e9057e09e071ebd57391f4b376'
assert head=='7f5b80d0fe35cf8520f80078ee0dbd50b1a5833d' and git(repo,'rev-parse','HEAD^')==base
assert git(gate,'rev-parse','HEAD')==head and git(gate,'write-tree')==tree
assert not git(repo,'status','--porcelain') and not git(gate,'status','--porcelain')
r=json.loads((out/'exact-gate/receipt.json').read_text());assert r['verdict']=='PASS' and r['head']==head and r['source_scope']=='exact commit' and r['all_load_reaped']
initial=json.loads((out/'matched-initial-counters.json').read_text())
def rows(p):
 # Rust test-status prefixes can share a line with println output. Match the
 # complete fixed record, then demand all 24 unique keys; do not drop cells.
 pattern=r'INPUT_LIFETIME_COUNTER (n=\d+ degree=\d+ weighted=(?:true|false) release=(?:true|false) allocation_calls=\d+ allocated_bytes=\d+ peak_requested_bytes=\d+ retained_admitted_bytes=\d+ peak_admitted_bytes=\d+ work=\d+)'
 result=[{k:(v=='true' if v in ['true','false'] else int(v)) for k,v in re.findall(r'(\w+)=([^ ]+)',m)} for m in re.findall(pattern,p.read_text())]
 assert len(result)==24 and len({(x['n'],x['degree'],x['weighted'],x['release']) for x in result})==24
 return result
ordinary=rows(out/'exact-gate/core-release.stdout');loaded=rows(out/'exact-gate/core-loaded.stdout');key=lambda x:(x['n'],x['degree'],x['weighted'],x['release'])
assert sorted(ordinary,key=key)==sorted(loaded,key=key)
for c in initial['cells']:assert c['original_200d1cf8'] in ordinary and c['candidate_released_input'] in ordinary
finalc={'recorded_utc':datetime.now(timezone.utc).isoformat(),'baseline_head':base,'candidate_commit':head,'candidate_tree':tree,'ordinary_and_saturated_counters_identical':True,'unchanged_baseline_matches_candidate_retained_input_control':True,'cells':initial['cells'],'limits':initial['limits'],'parser_scope':'24 complete unique records per exact log, allowing a preceding Rust test-status prefix; raw logs unchanged.'}
save(out/'matched-final-counters.json',finalc)
paths=git(repo,'diff',base,'--name-only').splitlines();assert all(p.startswith('examples/extensions/argentea/') or p.startswith('examples/extensions/nutmeg/src/argentea/') for p in paths)
assert not any('adjacency.rs' in p or '/protocol.rs' in p for p in paths)
rec={'recorded_utc':datetime.now(timezone.utc).isoformat(),'repository':'querygraph/sail','branch':'work/argentea-owned-input','commit':head,'base_commit':base,'tree':tree,'outcome':'EXACT_COMMIT_GATE_PASS_NOT_PUSHED','verdict':'ARGENTEA_INPUT_LIFETIME_GATE PASS '+head+' exact commit','gate_worktree':str(gate),'implementation_worktree':str(repo),'clean_branch_and_gate':True,'changed_paths':paths,'host_rust_and_protocol_and_adjacency_sources_unchanged':True,'core_test_count':120,'native_test_count':51,'native_argentea_test_count':45,'ordinary_and_saturated':True,'all_load_processes_reaped':True,'local_only':True,'upstream_or_fork_push':False,'gate_receipt_sha256':hashlib.sha256((out/'exact-gate/receipt.json').read_bytes()).hexdigest(),'independent_review_sha256':hashlib.sha256((out/'independent-source-audit.json').read_bytes()).hexdigest(),'counters_sha256':hashlib.sha256((out/'matched-final-counters.json').read_bytes()).hexdigest(),'scope':'Prepared-adjacency boundary for BFS and SSSP; raw vectors and their admission released before initial labels/frontier. Source, oracle, protocol, allocation/work, resource lifetime and local native adapter controls. No Linux rebuild, worker/Flight trial, wall-time, RSS, stream-cause or cluster-scaling result.'}
save(out/'final-receipt.json',rec)
print(json.dumps({'commit':head,'verdict':rec['verdict'],'counter_cells':len(initial['cells']),'final_receipt_sha256':hashlib.sha256((out/'final-receipt.json').read_bytes()).hexdigest()}))
