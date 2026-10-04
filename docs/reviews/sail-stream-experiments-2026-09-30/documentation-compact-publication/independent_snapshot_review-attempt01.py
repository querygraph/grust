"""Read-only frozen publication audit, not the operational documentation gate."""
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
from urllib.parse import unquote
import zipfile

OUT = Path('/private/tmp/grust-sail-review-compact-publication-v2')
DST = Path('/private/tmp/grust-sail-review-compact-docs-v2')
SRC = Path('/Users/alexy/src/grust')
REL = Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE = '95ad9933053a3896db10ff6b1ec57a98b904fb50'
AUTH = '72af4994d08303461dd188d116b1a88d312a51e4922abf2eb33fad1bc931c7a3'
ORIGIN = 'git@github.com:querygraph/grust.git'
MODIFIABLE = {str(REL/'RESULTS.md'), str(REL/'DOCUMENTATION-SNAPSHOT.json'), str(REL/'COMPACT-REPLAY-AND-SSSP.md'), 'codex-to-codex.md'}
PATTERNS = {
    'aws_access_key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'github_token': rb'\b(?:gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b',
    'openai_style_token': rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}',
    'google_api_key': rb'\bAIza[0-9A-Za-z_-]{30,}',
    'slack_token': rb'\bxox[baprs]-[A-Za-z0-9-]{20,}',
    'private_key': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'basic_bearer_auth': rb'(?i)authorization\s*[:=]\s*["\x27]?(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{16,}',
    'credential_url': rb'(?i)https?://[^\s:@/]{1,100}:[^\s@/]{8,100}@',
}


def check(value, message):
    if not value:
        raise ValueError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return sha_bytes(path.read_bytes())


def info(path):
    check(path.is_file() and not path.is_symlink(), 'not regular: '+str(path))
    data = path.read_bytes()
    return dict(sha256=sha_bytes(data), bytes=len(data), mode=oct(path.stat().st_mode & 0o777))


def load(path):
    return json.loads(path.read_text())


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args],
        env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), timeout=60).decode().strip()


def raw_git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args],
        env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'), timeout=60)


def safe_path(root, name):
    p = Path(name)
    check(not p.is_absolute() and '..' not in p.parts and str(p) == name, 'noncanonical path')
    current = root
    for part in p.parts:
        current /= part
        check(not current.is_symlink(), 'symlink ancestor: '+name)
    return current


def shared(prep):
    before = prep['shared_before']
    for args in [('--all',), ('--push', '--all')]:
        check(git(SRC, 'remote', 'get-url', *args, 'origin') == ORIGIN, 'origin changed')
    check(git(SRC, 'rev-parse', 'HEAD') == before['head'] == BASE, 'shared HEAD moved')
    check(git(SRC, 'symbolic-ref', 'HEAD') == before['branch'] == 'refs/heads/work/proposal-v5',
          'shared branch changed')
    index = Path(git(SRC, 'rev-parse', '--path-format=absolute', '--git-path', 'index'))
    check(info(index) == before['index'], 'shared raw index changed')
    for category in ('prose', 'review_inputs'):
        for name, expected in before[category].items():
            check(info(safe_path(SRC, name)) == expected, 'shared review/prose changed: '+name)
    p = SRC/'codex-to-codex.md'
    data = p.read_bytes()
    prefix = before['coordination']
    check(len(data) >= prefix['bytes'] and sha_bytes(data[:prefix['bytes']]) == prefix['sha256'],
          'shared coordination prefix changed')
    check(info(p)['mode'] == prefix['mode'], 'shared coordination mode changed')
    return dict(head=before['head'], index=before['index'], prefix=prefix,
                observed_coordination_bytes=len(data), suffix_bytes=len(data)-prefix['bytes'])


def main():
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), outcome='INCONCLUSIVE', errors=[],
        scope='Read-only frozen documentation source/evidence audit; no operational gate, snapshot mutation, commit, push, activation, runtime or remote-host operation.')
    target = OUT/'independent-audit.json'
    check(not target.exists(), 'audit already exists')
    try:
        pin,prep,auth = [load(OUT/n) for n in ['frozen.json','preparation.json','authorization.json']]
        check(pin['tree']=='095013015c48ef99e83cb73af78717b340725e3a' and pin['manifest_sha256']=='7aea3ac402b3a189cccdf1da36a0fa520e9572ae645701e7d830d112e13fe9cd','wrong frozen identity')
        check(sha(OUT/'authorization.json')==AUTH==pin['authorization_sha256']==prep['authorization_sha256'],'authorization drift')
        check(pin['base']==auth['base']==BASE,'base drift')
        check(sha(OUT/'preparation.json')==pin['preparation_sha256'] and sha(OUT/'base-manifest.json')==pin['base_manifest_sha256'],'preparation drift')
        selected=auth['selected_sources']
        check(len(selected)==461 and prep['selected_sources']==selected and prep['authorization']==auth,'selection drift')
        previous=Path('/private/tmp/grust-sail-review-compact-publication')
        check(sha(previous/'authorization.json')==AUTH,'retry selection/prose differs')
        retry=load(OUT/'retry-preparation.json')
        check(sha(previous/'index-refresh-guard-failure.json')==retry['failure_sha256']=='7a43fda0057587cd23090035817cc7e4b37b3e67a0ad76cf09691b9cca110872','retained failed attempt differs')
        failure=load(previous/'index-refresh-guard-failure.json')
        check(failure['outcome']=='GUARD_REJECTED_SHARED_INDEX_REFRESH' and failure['index_tree']==failure['head_tree'] and failure['selected_sources_unchanged'] is True,'wrong prior failure')
        for name,digest in retry['helper_hashes'].items():
            check(sha(OUT/name)==digest,'retry helper drift')
            expected=(previous/name).read_text()
            if name in ('common.py','commit_and_gate.sh'):
                expected=expected.replace('/private/tmp/grust-sail-review-compact-docs','/private/tmp/grust-sail-review-compact-docs-v2').replace('/private/tmp/grust-sail-review-compact-publication','/private/tmp/grust-sail-review-compact-publication-v2')
            check((OUT/name).read_text()==expected,'non-path helper delta: '+name)
        check(sha(OUT/'path-only-delta.patch')==retry['delta_sha256'],'retry delta drift')
        controls=load(OUT/'offline-controls02/receipt.json')
        check(controls['count']==len(controls['controls'])==60 and all(x['outcome']=='PASS' for x in controls['controls']),'offline control receipt differs')
        before=shared(prep)
        check(git(DST,'rev-parse','HEAD')==BASE and git(DST,'write-tree')==pin['tree'],'candidate drift')
        check(subprocess.run(['git','-C',str(DST),'symbolic-ref','-q','HEAD'],capture_output=True,env=dict(os.environ,GIT_OPTIONAL_LOCKS='0')).returncode==1,'attached candidate')
        check(not git(DST,'diff','--name-only') and not git(DST,'ls-files','--others','--exclude-standard'),'unstaged/untracked candidate')
        for name,expected in selected.items():
            check(info(safe_path(SRC,name))==info(safe_path(DST,name))==expected,'source byte/mode drift: '+name)
        for item in auth['required_json']:
            data=load(DST/item['path'])
            for pointer,expected in item['equals'].items():
                value=data
                for key in pointer.split('.'):value=value[key]
                check(value==expected,'closed predicate drift: '+item['path']+' '+pointer)
        helpers=pin['helper_hashes']
        for name,digest in helpers.items():check(sha(OUT/name)==digest,'frozen operational helper drift')
        changes=[row.split('\t')for row in git(DST,'diff','--cached','--name-status',BASE).splitlines()]
        check(all(len(x)==2 and x[0]in('A','M')for x in changes),'rename/deletion')
        changed={n for _,n in changes};added={n for k,n in changes if k=='A'};modified={n for k,n in changes if k=='M'}
        check(changed==set(pin['changed_paths']) and modified<=MODIFIABLE,'changed scope drift')
        check(set(pin['source_allowlist'])==set(selected)|{'codex-to-codex.md',str(REL/'DOCUMENTATION-SNAPSHOT.json')} and changed<=set(pin['source_allowlist']),'allowlist drift')
        forbidden=('/logging03-compact/','/followup02/','/host-pair-16k/','/host-pair-execution/','/certificate-parent-witness/')
        check(not any(any(p in n for p in forbidden)for n in added),'excluded active/raw evidence admitted')
        binary=str(REL/'logging03-publication/diagnostics.tar.gz')
        for name in added:
            check('__pycache__' not in Path(name).parts and Path(name).suffix not in ('.pyc','.parquet','.i64le','.bin','.so','.dylib','.whl'),'cache/private binary admitted')
            if name!=binary:
                data=(DST/name).read_bytes();data.decode('utf-8');check(b'\0'not in data,'new unapproved binary')
        check(info(DST/binary)==dict(bytes=13848616,sha256='2643372903532e7c1ff7b3f206aa7e5b176fef2a2b547ddc6947c1052d4fa83b',mode='0o644'),'gzip exception differs')
        coord_base=raw_git(DST,'show',BASE+':codex-to-codex.md');coord=(DST/'codex-to-codex.md').read_bytes()
        check(coord.startswith(coord_base),'historical coordination rewritten')
        appendix=coord[len(coord_base):]
        check(dict(bytes=len(appendix),sha256=sha_bytes(appendix))==prep['coordination_appendix'] and auth['coordination_body'].encode()in appendix,'coord append drift')
        check(not re.search(rb'^(<<<<<<<|=======|>>>>>>>)( |$)',coord,re.M),'coordination conflict')
        manifest_path=DST/REL/'DOCUMENTATION-SNAPSHOT.json';check(sha(manifest_path)==pin['manifest_sha256'],'manifest drift')
        manifest=load(manifest_path);old=json.loads(raw_git(DST,'show',BASE+':'+str(REL/'DOCUMENTATION-SNAPSHOT.json')))
        check(old==load(OUT/'base-manifest.json'),'base manifest differs')
        files={r['path']:r for r in manifest['files']};prior={r['path']:r for r in old['files']}
        check(len(files)==len(manifest['files'])==3260 and set(prior)<=set(files),'manifest loss/duplicates')
        prior_changed={n for n in prior if prior[n]!=files[n]}
        check(prior_changed<=MODIFIABLE and set(files)-set(prior)==added,'prior/new inventory differs')
        for name,row in prior.items():
            if name not in MODIFIABLE:check(sha(DST/name)==row['sha256'],'immutable prior evidence differs: '+name)
        check(manifest['pending_excluded_subtrees']==auth['excluded_scopes'] and manifest['current_snapshot_cutoff']==auth['cutoff'],'cutoff/exclusions differ')
        check(manifest['generated_fixture_exclusions']==old['generated_fixture_exclusions'],'inherited exclusions changed')
        archived=str(REL/'documentation-validation-publication/preparation-attempt01/RESULTS.md');original=str(REL/'RESULTS.md');history=str(REL/'documentation-validation-publication/preparation-attempt01/DOCUMENTATION-SNAPSHOT.json')
        context={archived:dict(original_path=original,source_manifest=history)}
        check(manifest['archived_markdown_link_contexts']==auth['archived_markdown_link_contexts']==context,'archive context drift')
        historical=load(safe_path(DST,history));rows={r['path']:r for r in historical['files']}
        check(len(rows)==len(historical['files']),'duplicate historic row')
        check(sha(DST/history)=='ed836fc097c91323003015c1584bc34699c45e1ba76f62dd9810daef46f38232','historical manifest differs')
        check(sha(DST/archived)==rows[original]['sha256']==files[archived]['sha256']=='7cf7f2e3fb677f3e547db4214de2dd9d48c2db8f4a5463a3234bc002444e7d9a' and (DST/archived).stat().st_size==rows[original]['bytes']==33684,'archive proof differs')
        counters=dict(files=0,bytes=0,json_files=0,jsonl_rows=0,markdown_links=0,archive_members=0,scan_units=0);hits={};archived_links=0
        compiled={k:re.compile(v)for k,v in PATTERNS.items()}
        def scan(name,data,count_unit=True):
            if count_unit:counters['scan_units']+=1
            for k,p in compiled.items():
                count=len(p.findall(data))
                if count:hits.setdefault(name,{}).setdefault(k,0);hits[name][k]+=count
            if name.endswith('.jsonl'):
                for line in data.splitlines():
                    if line.strip():json.loads(line);counters['jsonl_rows']+=1
        package_members={}
        for name,row in files.items():
            path=safe_path(DST,name);observed=info(path)
            check(observed['sha256']==row['sha256'] and observed['bytes']==row['bytes'],'manifest bytes differ: '+name)
            counters['files']+=1;counters['bytes']+=observed['bytes']
            if path.name.endswith(('.tar','.tar.gz','.tgz')):
                with tarfile.open(path,'r:*')as archive:
                    for member in archive:
                        if not member.isfile():continue
                        counters['archive_members']+=1;counters['scan_units']+=1;digest=hashlib.sha256();length=0
                        with archive.extractfile(member)as stream:
                            for line in stream:
                                digest.update(line);length+=len(line);scan(name+'::'+member.name,line,False)
                        if name==binary:
                            check('/'not in member.name and member.name not in package_members,'unsafe package member')
                            package_members[member.name]=dict(bytes=length,sha256=digest.hexdigest())
            elif path.name.endswith(('.zip','.whl')):
                with zipfile.ZipFile(path)as archive:
                    for member in archive.namelist():
                        if not member.endswith('/'):scan(name+'::'+member,archive.read(member));counters['archive_members']+=1
            else:scan(name,path.read_bytes())
            if path.suffix=='.json':json.loads(path.read_bytes());counters['json_files']+=1
            if path.suffix=='.md' and name!='codex-to-codex.md':
                for link in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)',path.read_text()):
                    if link.startswith(('https:','http:','mailto:','#')):continue
                    link=unquote(link.strip('<>').split('#',1)[0])
                    if link:
                        check(not Path(link).is_absolute() and '\\'not in link,'nonportable link: '+name+' '+link)
                        resolved=Path(os.path.normpath(((DST/original).parent if name==archived else path.parent)/link))
                        check(resolved.is_relative_to(DST) and safe_path(DST,str(resolved.relative_to(DST))).exists(),'missing link: '+name+' '+link)
                        counters['markdown_links']+=1
                        if name==archived:archived_links+=1
        check(archived_links==68,'incomplete archived links')
        report['privacy']=dict(counters=counters,matched_files=len(hits),matches=hits,scope='Eight credential-pattern families over text and streamed archive contents; no raw matching values emitted; not exhaustive sensitive-data detection.')
        check(not hits,'credential-like matches require review')
        package=DST/REL/'logging03-publication';pm=load(package/'manifest.json')
        check(package_members==pm['archive_members'] and len(pm['raw_tree'])==14,'package member inventory differs')
        for name,p in pm['package_files'].items():
            observed=info(package/name);check(all(observed[k]==v for k,v in p.items()),'package payload changed')
        check(sha(package/'frozen.json')=='146f60d1f45bc1dbf407da7d343ef51a4789275dd7e8241a2bff16b173279e73','package freeze differs')
        check(load(package/'controls02-receipt.json')['returncode']==0 and load(package/'rehydration02-receipt.json')['outcome']=='EXACT_RAW_COLLECTION_RESTORED','package validation absent')
        check(load(package/'rehydration02-receipt.json')['files']==pm['raw_tree'],'restored inventory differs')
        component=DST/REL/'sssp-candidate-buffer-reuse';final=load(component/'final-receipt.json');cm=load(component/'files-manifest.json');exact=load(component/'exact-gate/receipt.json')
        check(final['commit']==exact['head']=='fc094a0c25a49edeac2f9f0195aa973421a21a43' and final['tree']==exact['tree']=='5abc3e30eadb878402b3a90bcbeb0a48ac8c4b25' and exact['outcome']=='PASS' and exact['exact'] is True,'exact component mismatch')
        check(final['core_tests']==141 and final['native_tests']==55 and final['native_argentea_tests']==49,'component test scope differs')
        for row in cm['files']:
            observed=info(component/row['path']);check(observed['bytes']==row['bytes'] and observed['sha256']==row['sha256'],'component manifest mismatch')
        delivery=load(DST/REL/'sssp-candidate-buffer-reuse-delivery.json');check(set(delivery['remote_after'].values())=={final['commit']} and len(delivery['remote_after'])==2,'delivery refs differ')
        physical=load(DST/REL/'logging03-physical-execution/independent-final-review.json')
        check(physical['outcome']=='PASS_INDEPENDENT_CLOSED_PHYSICAL_EXECUTION_AUDIT' and physical['blockers']==[],'physical audit absent')
        check(sha(DST/REL/'verify_documentation_snapshot.py')=='d27e1c2703f60167eb758529d3df4ad00b5df15eb2a03ee2d4b2e6fa6f754808','verifier mutated')
        check((DST/REL/'RESULTS.md').read_bytes().startswith(raw_git(DST,'show',BASE+':'+str(REL/'RESULTS.md'))),'historical RESULTS rewritten')
        package_audit=Path('/private/tmp/logging03-publication-independent-review.json')
        check(sha(package_audit)=='056e465b08bc0739f064ffbb1bb2165bef6ba784013d0f4aee2b2ae907b24bec','independent package/prose review differs')
        after=shared(prep)
        for name,expected in selected.items():check(info(safe_path(SRC,name))==info(safe_path(DST,name))==expected,'source moved during review')
        check(git(DST,'rev-parse','HEAD')==BASE and git(DST,'write-tree')==pin['tree'] and sha(manifest_path)==pin['manifest_sha256'],'candidate moved')
        for name,digest in helpers.items():check(sha(OUT/name)==digest,'helper moved')
        report.update(outcome='PASS_INDEPENDENT_PUBLICATION_AUDIT',repository='querygraph/grust',base_commit=BASE,frozen_index_tree=pin['tree'],manifest_sha256=pin['manifest_sha256'],authorization_sha256=AUTH,selected_source_files_verified=len(selected),selected_source_bytes=sum(v['bytes']for v in selected.values()),inherited_manifest_files=len(prior),total_manifest_files=len(files),new_paths=len(added),modified_prior_paths=sorted(modified),prior_changed_entries=sorted(prior_changed),operational_helper_hashes=helpers,shared_before=before,shared_after=after,archive_context=dict(mapping=context,relative_links_checked=archived_links,independent_logic=True),retained_index_refresh_rejection_sha256=retry['failure_sha256'],path_only_retry_delta_sha256=retry['delta_sha256'],supplementary_package_prose_review_sha256=sha(package_audit),
            prose_and_neutrality_review=['Producer pass60/22-round certificate remains distinct from supplemental physical value/domain checks and independent shortest-path proof.','Container35,481,849,856B33.05GiB peak is distinct from PSS/heap; OOM baseline has no completed timing or uncapped peak denominator.','Shared-host/VM steal/host swap limits, wrapper attribution ambiguity and historical stream cause remain explicit.','All package/archive bytes and failed auditor/executor/monitor attempts remain retained; no raw collection or actual pair result admitted.','SSSPfc exact141core/55native49Argentea ordinary+loaded scope remains local; all36allocationcells and18matched pairs retained, no Linux/worker/Flight/timing promotion.','Historical RESULTS and archived Markdown bytes remain unchanged; all inherited links checked with68proven original-context links.'],limitations=['Documentation audit only; root still must execute candidate/exact gates and guarded publication.','No engine/SQL/benchmark/physical-output recomputation; component and physical review rely on exact retained receipts.','I authored closed review/package; independent Pecan package/prose review056e is separately bound.','Privacy scan is heuristic, not exhaustive; explicit machine paths and provenance commands remain.'])
    except Exception as error:
        report['outcome']='FAIL_INDEPENDENT_PUBLICATION_AUDIT';report['errors'].append(type(error).__name__+': '+str(error))
    report['finished_utc']=datetime.now(timezone.utc).isoformat();report['auditor_sha256']=sha(Path(__file__))
    if not report['outcome'].startswith('PASS_'):target=OUT/('independent-audit-failure-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    with target.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(dict(outcome=report['outcome'],path=str(target),sha256=sha(target),errors=report['errors'])))
    if report['outcome'].startswith('PASS_'):
        with(OUT/'audit-pin.json').open('x')as f:json.dump(dict(recorded_utc=datetime.now(timezone.utc).isoformat(),sha256=sha(target)),f,indent=2);f.write('\n')
        return 0
    return 1


if __name__=='__main__':raise SystemExit(main())
