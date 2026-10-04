"""Close the reviewed exact component without editing prior evidence or delivery."""
from datetime import datetime,timezone
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parent
REPO=Path('/private/tmp/sail-certificate-parent-witness-gate')
COMMIT='cab6bacc0ad0d1fc8b3070e9e4267e99751909fe'
BASE='fc094a0c25a49edeac2f9f0195aa973421a21a43'
TREE='cd73d093230153857de196abc17ea8e98464149b'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,data):
    with p.open('x') as f:json.dump(data,f,indent=2);f.write('\n')
def counts(path):
    return {key:sum(int(s.attrib[key]) for s in ET.parse(path).getroot().findall('testsuite'))
            for key in ('tests','failures','errors','skipped')}

def main():
    assert not (ROOT/'final-receipt.json').exists() and not (ROOT/'files-manifest.json').exists()
    frozen=load(ROOT/'frozen.json')
    spec=importlib.util.spec_from_file_location('guarded_gate',ROOT/'run_sql_gate.py')
    gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
    source=gate.support.source_identity(REPO,COMMIT,TREE,'exact')
    assert source==load(ROOT/'exact-gate02/source-after.json')
    for name,digest in frozen['source_hashes'].items():assert sha(REPO/name)==digest
    assert subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD^'],text=True).strip()==BASE
    required=['frozen.json','candidate.patch','README.md','runtime-provenance.json',
        'candidate-gate/receipt.json','candidate-gate02/receipt.json','exact-gate02/receipt.json',
        'exact-gate/receipt.json','lifecycle-control01/receipt.json','gate-isolation-change.json',
        'run_sql_gate-before-isolation.py','run_sql_gate.py','gate-isolation.patch',
        'commit-and-gate.log','commit_and_gate.sh','run-isolated-gates.sh',
        'independent-source-review.json','independent-exact-review.json','work-comparison.json',
        'baseline04/receipt.json','baseline-preconditions01/receipt.json',
        'candidate-preconditions01/receipt.json','candidate-preconditions02/receipt.json']
    for name in ('candidate-gate02','exact-gate02'):
        r=load(ROOT/name/'receipt.json')
        assert r['outcome']=='PASS' and r['tree']==TREE
        assert r['source_runtime_unchanged'] is True and r['server_reaped'] is True
        assert r['head']==(BASE if name=='candidate-gate02' else COMMIT)
        assert r['unit_counts']==counts(ROOT/name/'unit.xml')==dict(tests=473,failures=0,errors=0,skipped=136)
        assert r['sql_counts']==counts(ROOT/name/'sql.xml')==dict(tests=71,failures=0,errors=0,skipped=0)
        assert r['sql_isolation']=='one fresh pytest subprocess per test module'
        assert [m['counts']['tests'] for m in r['sql_modules']]==[9,43,6,6,7]
        for m in r['sql_modules']:
            assert m['counts']==counts(ROOT/name/(m['label']+'.xml'))
            assert all(m['counts'][k]==0 for k in ('failures','errors','skipped'))
        assert len(r['commands'])==8 and all(c['returncode']==0 for c in r['commands'])
        for name2,digest in r['logs'].items():assert sha(ROOT/name/name2)==digest
    initial=load(ROOT/'candidate-gate/receipt.json')
    assert initial['outcome']=='PASS' and initial['tree']==TREE and initial['head']==BASE
    assert initial['sql_counts']==dict(tests=71,failures=0,errors=0,skipped=0)
    failure=load(ROOT/'exact-gate/receipt.json')
    assert failure['outcome']=='failed' and failure['source_runtime_unchanged'] and failure['server_reaped']
    assert counts(ROOT/'exact-gate/sql.xml')==dict(tests=71,failures=39,errors=0,skipped=0)
    assert sha(ROOT/'run_sql_gate-before-isolation.py')==frozen['helper_hashes']['run_sql_gate.py']
    assert load(ROOT/'lifecycle-control01/receipt.json')['outcome']=='PASS'
    audit=load(ROOT/'independent-exact-review.json')
    assert audit['outcome']=='PASS_INDEPENDENT_PARENT_WITNESS_EXACT_AUDIT'
    assert audit['commit']==COMMIT and audit['tree']==TREE and not audit['blockers']
    assert audit['source_hashes']==frozen['source_hashes'] and audit['readme_sha256']==sha(ROOT/'README.md')
    work=load(ROOT/'work-comparison.json')
    assert work['outcome']=='PASS_MATCHED_WORK_CONTROL' and len(work['raw_cells'])==14 and len(work['pairs'])==7
    pattern=re.compile(r'(?i)(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[A-Z0-9]{16})')
    scanned=dict(files=0,json=0,xml=0,python=0,matched_credential_files=0)
    for p in ROOT.rglob('*'):
        assert not p.is_symlink()
        if p.is_dir():assert p.name!='__pycache__';continue
        scanned['files']+=1
        raw=p.read_bytes();text=raw.decode('utf-8')
        assert '\0' not in text
        if p.suffix=='.json':json.loads(text);scanned['json']+=1
        if p.suffix=='.xml':ET.fromstring(text);scanned['xml']+=1
        if p.suffix=='.py':ast.parse(text);scanned['python']+=1
        assert not pattern.search(text),'credential-like content in '+p.name
    final=dict(recorded_utc=datetime.now(timezone.utc).isoformat(),outcome='EXACT_COMPONENT_GATE_PASS',
        commit=COMMIT,base=BASE,tree=TREE,branch='work/certificate-parent-witness',
        unit_passed=337,unit_skipped=136,server_configured_cases=71,actual_sql_cases=67,pure_argument_cases=4,
        candidate_gate='candidate-gate02/receipt.json',exact_gate='exact-gate02/receipt.json',
        conditional_commit_gate='candidate-gate/receipt.json',retained_exact_failure='exact-gate/receipt.json',
        delivery='NOT_PUSHED_AT_EVIDENCE_CUTOFF',source_hashes=frozen['source_hashes'],
        inputs={name:sha(ROOT/name) for name in required},content_scan=scanned,
        scope='Local Python certificate and builtin SQL on pinned existing union CLI, no Rust build, Linux/Flight/combined native extension, timing, RSS, replay or cluster verdict. 71 configured cases include four pure argument controls. All seven client-work pairs retained including over-cap +1 ExecutePlan iterator call. Module-isolated client fixture correction does not establish exact GC interleaving or older stream-loss cause.')
    save(ROOT/'final-receipt.json',final)
    members={str(p.relative_to(ROOT)):sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file()}
    save(ROOT/'files-manifest.json',dict(recorded_utc=datetime.now(timezone.utc).isoformat(),commit=COMMIT,
        file_count=len(members),files=members,scope='Every file except this manifest; private generated fixture directories are outside this folder.'))
    print('EXACT_COMPONENT_GATE_PASS',COMMIT,'manifest_members',len(members))


if __name__=='__main__':main()
