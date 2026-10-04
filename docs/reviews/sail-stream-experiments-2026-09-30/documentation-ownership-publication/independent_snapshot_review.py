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

OUT = Path('/private/tmp/grust-sail-review-ownership-publication-v2')
DST = Path('/private/tmp/grust-sail-review-ownership-docs-v2')
SRC = Path('/Users/alexy/src/grust')
REL = Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE = '980da04151cd5860017a06580a658bdf7e133c40'
AUTH = '0f5b862c96f0fcab343c3c62ffae989138e9d475dfd972ea6dfba46bd0816e28'
ORIGIN = 'git@github.com:querygraph/grust.git'
MODIFIABLE = {str(REL/'RESULTS.md'), str(REL/'DOCUMENTATION-SNAPSHOT.json'), str(REL/'verify_documentation_snapshot.py'), 'codex-to-codex.md'}
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
    report = dict(started_utc=datetime.now(timezone.utc).isoformat(), outcome='INCONCLUSIVE',
        scope='Independent read-only frozen documentation source/evidence audit. No operational gate, '
              'snapshot mutation, commit, push, activation, runtime suite, benchmark or remote call.', errors=[])
    target = OUT/'independent-audit.json'
    check(not target.exists(), 'independent receipt already exists')
    try:
        pin = load(OUT/'frozen.json')
        prep = load(OUT/'preparation.json')
        auth = load(OUT/'authorization.json')
        check(pin['tree'] == '36ddfe339051d11afc86b9a144669f6f7bca3aae' and
              pin['manifest_sha256'] == 'c18d5aea38d3d81fff6b808e8e003f7157db53b2e977ea0f0b83657c71dcd347',
              'frozen candidate differs from reviewed tree')
        check(sha(OUT/'authorization.json') == AUTH, 'authorization hash changed')
        check(pin['base'] == auth['base'] == BASE, 'base differs')
        check(pin['authorization_sha256'] == prep['authorization_sha256'] == AUTH, 'authorization binding differs')
        check(sha(OUT/'preparation.json') == pin['preparation_sha256'], 'preparation changed')
        check(sha(OUT/'base-manifest.json') == pin['base_manifest_sha256'], 'base manifest changed')
        check(prep['selected_sources'] == auth['selected_sources'] and prep['authorization'] == auth,
              'selected inputs/prose differ from authorization')
        check(len(auth['selected_sources']) == 240, 'selected inventory changed')
        previous_auth = load(OUT/'predecessor/authorization.json')
        check(sha(OUT/'predecessor/authorization.json') == 'ada313425cfc3d618ed6615fff076f9751c8ed8a2b977fb268ab413aa5327782', 'previous authorization differs')
        check(len(previous_auth['selected_sources']) == 223 and all(auth['selected_sources'].get(n) == v for n,v in previous_auth['selected_sources'].items()), 'old selected bytes changed')
        old_candidate = Path('/private/tmp/grust-sail-review-ownership-docs')
        check(git(old_candidate,'rev-parse','HEAD') == BASE and git(old_candidate,'write-tree') == '08cfe9287b8412547324b50cb5fc9463d2ad2a21', 'old failed candidate moved')
        check(sha(old_candidate/REL/'DOCUMENTATION-SNAPSHOT.json') == '5ee69bac72d6dcfbe7f84029c736ef55ccfbff21f268fe005ba04605175dec1d', 'old failed manifest changed')
        tooling = load(OUT/'tooling-preparation-v3.json')
        for name,digest in tooling['predecessor_files_unchanged_and_copied'].items():
            check(sha(OUT/'predecessor'/name) == sha(Path(tooling['predecessor'])/name) == digest, 'old output changed: '+name)
        before = shared(prep)
        check(git(DST, 'rev-parse', 'HEAD') == BASE and git(DST, 'write-tree') == pin['tree'], 'candidate source changed')
        check(subprocess.run(['git', '-C', str(DST), 'symbolic-ref', '-q', 'HEAD'], capture_output=True).returncode == 1,
              'candidate is attached')
        check(not git(DST, 'diff', '--name-only') and not git(DST, 'ls-files', '--others', '--exclude-standard'),
              'candidate has unstaged/untracked files')
        selected = auth['selected_sources']
        for name, expected in selected.items():
            check(info(safe_path(SRC, name)) == info(safe_path(DST, name)) == expected, 'selected source differs: '+name)
        for required in auth['required_json']:
            data = load(DST/required['path'])
            for path, expected in required['equals'].items():
                actual = data
                for key in path.split('.'):
                    actual = actual[key]
                check(actual == expected, 'closure assertion differs: '+required['path']+' '+path)
        helpers = {}
        for name, expected in pin['helper_hashes'].items():
            check(sha(OUT/name) == expected, 'operational helper changed: '+name)
            helpers[name] = expected
        status = [line.split('\t') for line in git(DST, 'diff', '--cached', '--name-status', BASE).splitlines()]
        check(all(len(row) == 2 and row[0] in ('A', 'M') for row in status), 'unexpected status/rename/delete')
        changed = {row[1] for row in status}
        modified = {name for kind, name in status if kind == 'M'}
        added = {name for kind, name in status if kind == 'A'}
        check(changed == set(pin['changed_paths']) and modified <= MODIFIABLE, 'changed path scope differs')
        check(set(pin['source_allowlist']) == set(selected) | {'codex-to-codex.md', str(REL/'DOCUMENTATION-SNAPSHOT.json')},
              'allowlist differs')
        check(changed <= set(pin['source_allowlist']), 'unexpected changed file')
        forbidden = ('/logging03/', '/logging03-monitor/', '/logging03-observations/', '/followup02/', '/host-pair-16k/')
        check(not any(any(part in name for part in forbidden) for name in added), 'active evidence admitted')
        check(not any('__pycache__' in Path(name).parts or Path(name).suffix in
                      ('.pyc', '.parquet', '.i64le', '.bin', '.so', '.dylib', '.whl') for name in added),
              'private data/cache admitted')
        coord_base = raw_git(DST, 'show', BASE+':codex-to-codex.md')
        coord = (DST/'codex-to-codex.md').read_bytes()
        check(coord.startswith(coord_base), 'candidate rewrote historical coordination')
        appendix = coord[len(coord_base):]
        check(dict(bytes=len(appendix), sha256=sha_bytes(appendix)) == prep['coordination_appendix'], 'appendix differs')
        check(appendix.decode().count('\n## ') == 1 and auth['coordination_body'].encode() in appendix,
              'unexpected coordination prose')
        check(not re.search(rb'^(<<<<<<<|=======|>>>>>>>)( |$)', coord, re.M), 'coordination conflict marker')
        manifest_path = DST/REL/'DOCUMENTATION-SNAPSHOT.json'
        check(sha(manifest_path) == pin['manifest_sha256'], 'manifest differs')
        manifest = load(manifest_path)
        old = json.loads(raw_git(DST, 'show', BASE+':'+str(REL/'DOCUMENTATION-SNAPSHOT.json')))
        check(old == load(OUT/'base-manifest.json'), 'base manifest is not exact base')
        files = {row['path']: row for row in manifest['files']}
        prior = {row['path']: row for row in old['files']}
        check(len(files) == len(manifest['files']) and set(prior) <= set(files), 'manifest loss/duplicates')
        prior_changed = {name for name in prior if files[name] != prior[name]}
        check(prior_changed <= MODIFIABLE and set(files)-set(prior) == added, 'prior evidence/new inventory differs')
        for name, row in prior.items():
            if name not in MODIFIABLE:
                check(sha(DST/name) == row['sha256'], 'prior immutable evidence changed: '+name)
        check(manifest['pending_excluded_subtrees'] == auth['excluded_scopes'] and
              manifest['current_snapshot_cutoff'] == auth['cutoff'], 'cutoff/exclusions differ')
        check(manifest['generated_fixture_exclusions'] == old['generated_fixture_exclusions'],
              'historical fixture exclusions changed')
        # Separate implementation from the production parser: this audit recognizes
        # exactly the reviewed mapping and derives its base from independently hashed proof.
        archived = str(REL/'documentation-validation-publication/preparation-attempt01/RESULTS.md')
        original = str(REL/'RESULTS.md')
        historical_name = str(REL/'documentation-validation-publication/preparation-attempt01/DOCUMENTATION-SNAPSHOT.json')
        expected_context = {archived: dict(original_path=original, source_manifest=historical_name)}
        check(manifest.get('archived_markdown_link_contexts') == auth['archived_markdown_link_contexts'] == expected_context, 'archive mapping differs')
        for name in (archived, original, historical_name):
            check(name in files and safe_path(DST,name).is_file(), 'unknown/unsafe archive context path')
        archive_bytes = safe_path(DST,archived).read_bytes()
        historical_bytes = safe_path(DST,historical_name).read_bytes()
        check(sha_bytes(historical_bytes) == files[historical_name]['sha256'] == 'ed836fc097c91323003015c1584bc34699c45e1ba76f62dd9810daef46f38232', 'historical source manifest differs')
        historical_rows = json.loads(historical_bytes)['files']
        historical_names = [r['path'] for r in historical_rows]
        check(len(historical_names) == len(set(historical_names)), 'duplicate historical rows')
        historical_row = next(r for r in historical_rows if r['path'] == original)
        check(sha_bytes(archive_bytes) == files[archived]['sha256'] == historical_row['sha256'] == '7cf7f2e3fb677f3e547db4214de2dd9d48c2db8f4a5463a3234bc002444e7d9a', 'historical original proof differs')
        check(len(archive_bytes) == files[archived]['bytes'] == historical_row['bytes'] == 33684, 'historical byte count differs')
        archived_links = 0
        hits = {}
        counters = dict(files=0, bytes=0, json_files=0, jsonl_rows=0, markdown_links=0, scan_units=0, archive_members=0)

        def scan(name, data):
            counters['scan_units'] += 1
            matches = {label: len(re.findall(pattern, data)) for label, pattern in PATTERNS.items()
                       if re.search(pattern, data)}
            if matches:
                hits[name] = matches
            if name.endswith('.jsonl'):
                for line in data.splitlines():
                    if line.strip():
                        json.loads(line)
                        counters['jsonl_rows'] += 1

        for name, row in files.items():
            path = safe_path(DST, name)
            observed = info(path)
            check(observed['sha256'] == row['sha256'] and observed['bytes'] == row['bytes'], 'manifest bytes differ: '+name)
            data = path.read_bytes()
            counters['files'] += 1
            counters['bytes'] += len(data)
            scan(name, data)
            if path.suffix == '.json':
                json.loads(data)
                counters['json_files'] += 1
            if path.suffix == '.md' and name != 'codex-to-codex.md':
                for link in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', data.decode()):
                    if link.startswith(('https:', 'http:', 'mailto:', '#')):
                        continue
                    link = unquote(link.strip('<>').split('#', 1)[0])
                    if link:
                        check(not Path(link).is_absolute() and '\\' not in link, 'nonportable link: '+name+' '+link)
                        link_base = (DST/original).parent if name == archived else path.parent
                        resolved_target = Path(os.path.normpath(link_base/link))
                        check(resolved_target.is_relative_to(DST), 'link escapes repository: '+name+' '+link)
                        check(safe_path(DST,str(resolved_target.relative_to(DST))).exists(), 'missing link: '+name+' '+link)
                        if name == archived:
                            archived_links += 1
                        counters['markdown_links'] += 1
            if path.name.endswith(('.tar', '.tar.gz', '.tgz')):
                with tarfile.open(fileobj=io.BytesIO(data), mode='r:*') as archive:
                    for member in archive.getmembers():
                        if member.isfile():
                            scan(name+'::'+member.name, archive.extractfile(member).read())
                            counters['archive_members'] += 1
            elif path.name.endswith(('.zip', '.whl')):
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for member in archive.namelist():
                        if not member.endswith('/'):
                            scan(name+'::'+member, archive.read(member))
                            counters['archive_members'] += 1
        check(archived_links == 68, 'all archived links must be checked')
        report['archive_context'] = dict(mapping=expected_context, source_manifest_sha256=sha_bytes(historical_bytes), historical_row=historical_row, relative_links_checked=archived_links, implementation='Independent audit logic; production parser not imported')
        report['privacy'] = dict(counters=counters, matched_files=len(hits), matches_file_and_count_only=hits,
                                scope='Heuristic credential-pattern scan; archives read in memory, never extracted. Not exhaustive secret detection.')
        check(not hits, 'credential-like matches require private review')
        # All selected subtrees are closed, complete copies; no selective success-only inventory.
        allowed_dirs = {'argentea-rank-wcc-input-lifetime', 'argentea-cursor-lease-control',
                        'physical-output-execution-preparation', 'documentation-validation-publication', 'documentation-archive-context'}
        allowed_files = {'RESULTS.md','verify_documentation_snapshot.py','argentea-rank-wcc-input-lifetime-delivery.json',
                         'documentation-validation-activation.json'}
        for name in selected:
            local = Path(name).relative_to(REL)
            check(local.parts[0] in allowed_dirs or str(local) in allowed_files, 'unapproved selected scope')
        for directory in allowed_dirs:
            actual = {str(p.relative_to(SRC)) for p in (SRC/REL/directory).rglob('*')
                      if p.is_file() and '__pycache__' not in p.parts}
            check(actual == {name for name in selected if name.startswith(str(REL/directory)+'/')},
                  'incomplete closed subtree: '+directory)
        check((DST/REL/'RESULTS.md').read_bytes().startswith(raw_git(DST,'show',BASE+':'+str(REL/'RESULTS.md'))),
              'existing RESULTS prose changed')
        check('is prepared for use after the compact replay closes' in (DST/REL/'RESULTS.md').read_text(),
              'prospective replay wording missing')
        component = DST/REL/'argentea-rank-wcc-input-lifetime'
        final = load(component/'final-receipt.json')
        component_manifest = load(component/'files-manifest.json')
        check(final['commit'] == '33adfce1d2ab77c3e108aa542f7eda80dd5f5cf9' and
              final['tree'] == '3f4399056199b49708340abf0b4d1205fca860dd' and
              final['outcome'] == 'EXACT_COMPONENT_GATE_PASS', 'expanded closure differs')
        check(sha(component/'final-receipt.json') == 'eff934be8adb0d9aa867596148b9fd9586fed96f1ba55ab74b2be35c9fa95380', 'final component bytes differ')
        check(sha(component/'files-manifest.json') == '07f783f99210e1611b692d101e9fa1ee7aff79da576a4e49c54dbaa30ccc9ea1', 'component manifest differs')
        check(len(component_manifest['files']) == 135, 'component member count')
        actual_component = {str(p.relative_to(component)) for p in component.rglob('*') if p.is_file()}
        check(actual_component == {r['path'] for r in component_manifest['files']}|{'files-manifest.json'}, 'component inventory differs')
        for row in component_manifest['files']:
            observed = info(component/row['path'])
            check(observed['sha256'] == row['sha256'] and observed['bytes'] == row['bytes'], 'component member changed')
        check(final['exact_gate'] == 'extended-exact-gate/receipt.json', 'intermediate scope used as final')
        check(sha(component/final['exact_gate']) == final['exact_gate_receipt_sha256'], 'expanded exact hash')
        exact = load(component/final['exact_gate'])
        check(exact['outcome'] == 'PASS' and exact['exact'] is True and exact['head'] == final['commit'] and exact['tree'] == final['tree'], 'expanded exact verdict')
        check(sha(component/'independent-exact-review.json') == 'db243b7e11163ea79694e5e5e3fd8cdf273ea4b2893243e04f07cb06d6fd9321', 'component audit differs')
        check(sha(component/'independent-readme-rebind.json') == 'b57943229b7b120a1917322678c514d4a0a9cc3862b30c469a7fb92dab77cabd', 'README clarification rebind differs')
        check(sha(component/'README.md') == final['readme_sha256'], 'final README changed')
        delivery = load(DST/REL/'argentea-rank-wcc-input-lifetime-delivery.json')
        check(delivery['outcome'] == 'PUSHED_AND_REMOTELY_VERIFIED' and delivery['commit'] == final['commit'] and
              delivery['tree'] == final['tree'] and delivery['exact_gate_sha256'] == final['exact_gate_receipt_sha256'] and
              delivery['final_receipt_sha256'] == sha(component/'final-receipt.json') and
              delivery['manifest_sha256'] == sha(component/'files-manifest.json'), 'outer delivery binding')
        check(set(delivery['remote_after'].values()) == {final['commit']} and len(delivery['remote_after']) == 2, 'two delivered refs')
        for name in ['baseline-receipt.json','baseline02-receipt.json','partition-lease-baseline-receipt.json',
                     'core-preliminary-failure.json','baseline-native-control02/receipt.json',
                     'candidate-native-control01/receipt.json','baseline-native-extended01/receipt.json',
                     'candidate-native-extended01/receipt.json','candidate-gate/receipt.json','exact-gate/receipt.json']:
            check((component/name).is_file(), 'failed/intermediate attempt absent: '+name)
        check(sha(DST/REL/'argentea-cursor-lease-control/final-receipt.json') == final['cursor_evidence_sha256'], 'cursor binding')
        executor = DST/REL/'physical-output-execution-preparation'
        check(sha(executor/'preparation-v2.json') == '729faa260a5f38eabfab906cd13d62c3970c5640e6d34c9e102cbde640bb10ed' and
              sha(executor/'independent-review-v2.json') == 'b60e953b2063b52b9574897bbd2690b7153e77feb7a8ee544935f12037734365', 'executor v2 reviewed bytes')
        check(load(executor/'preparation-v2.json')['result_parquet_read'] is False, 'physical output claim expanded')
        check(load(executor/'review-reproductions-v2.json')['outcome'] == 'BOTH_ATTEMPT01_GAPS_REPRODUCED', 'executor failures absent')
        after = shared(prep)
        for name, expected in selected.items():
            check(info(safe_path(SRC, name)) == info(safe_path(DST, name)) == expected, 'source moved during audit: '+name)
        check(git(DST, 'rev-parse', 'HEAD') == BASE and git(DST, 'write-tree') == pin['tree'] and
              sha(manifest_path) == pin['manifest_sha256'], 'candidate moved during audit')
        for name, expected in helpers.items():
            check(sha(OUT/name) == expected, 'helper moved during audit: '+name)
        claims_path = OUT/'predecessor/claims-spot-review.json'
        claims = load(claims_path)
        check(sha(claims_path) == '6a99250cde01242e130cf43f6949b34a5ebd91411e736643c4ecff9c957161aa' and
              claims['frozen_index_tree'] == '08cfe9287b8412547324b50cb5fc9463d2ad2a21' and
              claims['manifest_sha256'] == '5ee69bac72d6dcfbe7f84029c736ef55ccfbff21f268fe005ba04605175dec1d' and
              claims['outcome'].startswith('PASS'), 'previous claims spot review differs')
        archive_review_path = OUT/'independent-archive-context-review.json'
        archive_review = load(archive_review_path)
        check(sha(archive_review_path) == '25956bc352b4bfb5bcd855fa82fb0db2639c5870df32a0cf8666de0852b219ff', 'archive review bytes differ')
        check(archive_review['outcome'] == 'PASS_INDEPENDENT_ARCHIVE_CONTEXT_SOURCE_TOOLING_REVIEW' and
              archive_review['frozen_index_tree'] == pin['tree'] and archive_review['manifest_sha256'] == pin['manifest_sha256'] and
              archive_review['authorization_sha256'] == AUTH, 'archive source/tooling review not exact')
        for name,digest in archive_review['tooling_helpers'].items():
            check(sha(OUT/name) == digest, 'independently reviewed tooling changed: '+name)
        check(sha(OUT/'tooling-preparation-v3.json') == archive_review['tooling_preparation_sha256'], 'tooling preparation differs')
        check(sha(DST/REL/'verify_documentation_snapshot.py') == 'd27e1c2703f60167eb758529d3df4ad00b5df15eb2a03ee2d4b2e6fa6f754808', 'reviewed verifier differs')
        check(sha(DST/REL/'documentation-archive-context/receipt.json') == '39f321db8e096fa40a8a2aad7f5717590dfab945533abf7019988b043cc02adf', 'archive controls differ')
        report.update(outcome='PASS_INDEPENDENT_PUBLICATION_AUDIT', repository='querygraph/grust',
            base_commit=BASE, frozen_index_tree=pin['tree'], manifest_sha256=pin['manifest_sha256'],
            authorization_sha256=AUTH, selected_source_files_verified=len(selected),
            selected_source_bytes=sum(x['bytes'] for x in selected.values()),
            inherited_manifest_files=len(prior), total_manifest_files=len(files),
            changed_paths=len(changed), new_paths=len(added), modified_prior_paths=sorted(modified),
            changed_prior_manifest_entries=sorted(prior_changed), operational_helper_hashes=helpers,
            supplementary_claims_review_sha256=sha(claims_path),
            retained_auditor_failure_sha256=sha(OUT/'independent-auditor-attempt01-failure.json'),
            retained_auditor_source_sha256=sha(OUT/'independent_snapshot_review-attempt01.py'),
            unchanged_prior_selected_sources=223, archive_source_tooling_review_sha256=sha(archive_review_path),
            preserved_previous_failed_audit_sha256=sha(OUT/'predecessor/independent-audit-failure-20261001T010351687857Z.json'),
            shared_before=before, shared_after=after,
            prose_and_neutrality_review=[
                '72 allocator cells describe local owner0 requested allocation/admission, not aggregate worker/cluster or RSS/timing.',
                'Borrowed/split candidate API comparisons and actual unchanged-production adapter baselines remain distinct.',
                'Lease-release baseline and cursor actual-allocation evidence are scoped; no permanent leak or historical stream-cause attribution.',
                'Intermediate a41/129+54 gates remain historical; final33adfce exact136+55/49 ordinary+loaded gate is explicit.',
                'Component pre-push cutoff is preserved, with separate post-push delivery verified on two named fork refs.',
                'Executor v2 is prepared for future closed replay use only; both original failed controls remain included.',
                'Active03, future pairs, actual physical scans and subsequent SSSP feasibility are excluded; no outcome/performance promotion.',
                'Historical Markdown remains byte-identical;68 archived links are checked from proven original context, all ordinary links remain checked.',
                'Engineering properties and all outcomes are retained without favorable-system framing.'],
            limitations=['Documentation source/evidence review only; operational candidate/exact gates and remote CAS remain required.',
                        'No runtime suites, benchmark, physical campaign output recomputation, Linux/worker/Flight or timing qualification.',
                        'I authored the cursor experiment and component audit, and reviewed the executor; this inclusion audit is not an independent repetition of those experiments.',
                        'Heuristic privacy scan is not exhaustive; intentional local paths and command/environment provenance remain.'])
    except Exception as error:
        report['outcome'] = 'FAIL_INDEPENDENT_PUBLICATION_AUDIT'
        report['errors'].append(type(error).__name__+': '+str(error))
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    report['auditor_sha256'] = sha(Path(__file__))
    target = target if report['outcome'].startswith('PASS_') else OUT/('independent-audit-failure-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    with target.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(outcome=report['outcome'], path=str(target), sha256=sha(target), errors=report['errors'])))
    return 0 if report['outcome'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
