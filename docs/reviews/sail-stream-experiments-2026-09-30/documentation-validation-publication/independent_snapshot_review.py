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

OUT = Path('/private/tmp/grust-sail-review-validation-publication')
DST = Path('/private/tmp/grust-sail-review-validation-docs')
SRC = Path('/Users/alexy/src/grust')
REL = Path('docs/reviews/sail-stream-experiments-2026-09-30')
BASE = 'd9df4b0e89b1e4a1838b1b536d05f47ba4f12808'
AUTH = 'c82c2dca3c1f2395e0058c6767de06c600526ea1335b9a984d153612c87ec5a3'
ORIGIN = 'git@github.com:querygraph/grust.git'
MODIFIABLE = {str(REL/'RESULTS.md'), str(REL/'DOCUMENTATION-SNAPSHOT.json'), 'codex-to-codex.md'}
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
        auth = load(OUT/'authorized-inputs.json')
        check(pin['tree'] == '7f751ac8075c2a378d229fa632f765ff89698d4f' and
              pin['manifest_sha256'] == 'e469536eac6b651d2b337acec468759df5ca3fcaeef3927005abe3d658e4ba03',
              'frozen candidate differs from reviewed tree')
        check(sha(OUT/'authorized-inputs.json') == AUTH, 'authorization hash changed')
        check(pin['base'] == auth['base'] == BASE, 'base differs')
        check(pin['authorization_sha256'] == prep['authorization_sha256'] == AUTH, 'authorization binding differs')
        check(sha(OUT/'preparation.json') == pin['preparation_sha256'], 'preparation changed')
        check(sha(OUT/'base-manifest.json') == pin['base_manifest_sha256'], 'base manifest changed')
        check(prep['selected_sources'] == auth['selected_sources'] and prep['authorization'] == auth,
              'selected inputs/prose differ from authorization')
        check(len(auth['selected_sources']) == 434, 'selected inventory changed')
        refresh = load(OUT/'preparation-refresh.json')
        failure = load(OUT/'preparation-attempt01-failure.json')
        check(sha(OUT/'preparation-refresh.json') == pin['precision_refresh_sha256'] and
              sha(OUT/'preparation-attempt01-failure.json') == pin['retained_preparation_failure_sha256'],
              'preparation failure/refresh binding differs')
        old_auth = load(OUT/'preparation-attempt01/authorized-inputs.json')
        check(sha(OUT/'preparation-attempt01/authorized-inputs.json') == refresh['retained_authorization_sha256'],
              'original authorization changed')
        expected_auth = json.loads(json.dumps(old_auth))
        expected_auth['selected_sources'][str(REL/'RESULTS.md')] = auth['selected_sources'][str(REL/'RESULTS.md')]
        expected_auth['precision_refresh_utc'] = refresh['recorded_utc']
        check(expected_auth == auth, 'authorization refresh exceeds RESULTS fingerprint and recorded refresh time')
        changed_refresh = git(DST, 'diff', '--name-only', refresh['previous_failed_tree'], pin['tree']).splitlines()
        check(set(changed_refresh) == {str(REL/'RESULTS.md'), str(REL/'DOCUMENTATION-SNAPSHOT.json')},
              'refresh changed raw evidence')
        old_results = (OUT/'preparation-attempt01/RESULTS.md').read_text()
        replacement = refresh['exact_replacement']
        check(old_results.count(replacement['before']) == 1 and
              old_results.replace(replacement['before'], replacement['after']) == (DST/REL/'RESULTS.md').read_text(),
              'prose precision correction differs')
        check(failure['outcome'] == 'PREPARATION_FAILED_BEFORE_GATE_OR_COMMIT' and
              load(OUT/'preparation-resume.json')['outcome'] == 'PREPARATION_RESUMED_WITHOUT_SOURCE_CHANGE',
              'preparation outcomes differ')
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
        forbidden = ('/logging03/', '/logging03-monitor/', '/followup02/', '/argentea-rank-wcc-input-lifetime/')
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
                        check(not Path(link).is_absolute() and (path.parent/link).exists(), 'nonportable/missing link: '+name+' '+link)
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
        report['privacy'] = dict(counters=counters, matched_files=len(hits), matches_file_and_count_only=hits,
                                scope='Heuristic credential-pattern scan; archives read in memory, never extracted. Not exhaustive secret detection.')
        check(not hits, 'credential-like matches require private review')
        union = DST/REL/'resource-validation-union'
        final = load(union/'final-receipt.json')
        check(final['commit'] == 'a3462345a6764096024c055dc4d105a3c634e5a4' and
              final['outcome'] == 'EXACT_GATED_PUSHED_AND_INDEPENDENTLY_REVIEWED', 'union closure differs')
        for name, expected in final['files'].items():
            actual = info(union/name)
            check(all(actual[k] == value for k, value in expected.items()), 'union member differs: '+name)
        check(sha(union/'independent-exact-review.json') == 'efe879c64bb019c8a7ae541cb493237629b54b2b5df63aaca0f97aabaef50a03',
              'reviewed exact union receipt changed')
        for attempt, expected in [('candidate-gate', 'FAIL'), ('candidate-gate02', 'FAIL'), ('candidate-gate03', 'PASS'), ('exact-gate', 'PASS')]:
            check(load(union/attempt/'receipt.json')['outcome'] == expected, 'union attempt outcome changed')
        delivery = load(DST/REL/'resource-validation-union-delivery.json')
        check(delivery['commit'] == final['commit'] and delivery['outcome'] == 'PUSHED_AND_REMOTELY_VERIFIED' and
              delivery['exact_gate_sha256'] == sha(union/'exact-gate/receipt.json') and
              delivery['independent_audit_sha256'] == sha(union/'independent-exact-review.json'), 'delivery binding differs')
        check(sha(DST/REL/'resource-validation-union-delivery.json') == final['delivery']['sha256'], 'outer delivery bytes differ')
        after = shared(prep)
        for name, expected in selected.items():
            check(info(safe_path(SRC, name)) == info(safe_path(DST, name)) == expected, 'source moved during audit: '+name)
        check(git(DST, 'rev-parse', 'HEAD') == BASE and git(DST, 'write-tree') == pin['tree'] and
              sha(manifest_path) == pin['manifest_sha256'], 'candidate moved during audit')
        for name, expected in helpers.items():
            check(sha(OUT/name) == expected, 'helper moved during audit: '+name)
        claims_path = OUT/'claims-spot-review.json'
        check(sha(claims_path) == 'ab80c2b2c8a9583201ea738754ec542521db4146bf7880160a152943ea59087b',
              'supplementary claims review changed')
        report.update(outcome='PASS_INDEPENDENT_PUBLICATION_AUDIT', repository='querygraph/grust',
            base_commit=BASE, frozen_index_tree=pin['tree'], manifest_sha256=pin['manifest_sha256'],
            authorization_sha256=AUTH, selected_source_files_verified=len(selected),
            selected_source_bytes=sum(x['bytes'] for x in selected.values()),
            inherited_manifest_files=len(prior), total_manifest_files=len(files),
            changed_paths=len(changed), new_paths=len(added), modified_prior_paths=sorted(modified),
            changed_prior_manifest_entries=sorted(prior_changed), operational_helper_hashes=helpers,
            retained_preparation_failure_sha256=pin['retained_preparation_failure_sha256'],
            precision_refresh_sha256=pin['precision_refresh_sha256'],
            supplementary_claims_review_sha256=sha(claims_path),
            retained_auditor_attempt=dict(path='independent-audit-failure-20261001T002601061821Z.json',
                sha256=sha(OUT/'independent-audit-failure-20261001T002601061821Z.json'),
                reason='First audit expected only a RESULTS source-pin refresh; explicit generated precision_refresh_utc was also added. Final audit binds that timestamp exactly to the retained refresh receipt.'),
            shared_before=before, shared_after=after,
            prose_and_neutrality_review=[
                'Allocation claims remain per-partition requested-heap controls with three configured partitions; no RSS or timing promotion.',
                'Component pre-push README cutoffs remain intact and outer delivery receipts update publication state.',
                'PageRank component tests use the separately pinned installed runtime; combined union tests explicitly require the newly built CLI.',
                'Parquet floating-bound optimization loss and untested paths are explicit; no historical corruption or stream-cause attribution.',
                'Both union gate failures and narrow harness fixes remain visible; active logging03 and future paired results remain excluded.',
                'Supplemental physical-output and pair auditors are preparation only; no physical campaign scan or qualified ratio is claimed.',
                'New reviewed prose frames measurements as engineering evidence and retains unfavorable outcomes and scope limits.'],
            limitations=['Documentation source/evidence review only; operational candidate/exact gates and remote CAS remain required.',
                        'No Linux/worker/Flight, combined native extension load, performance, large-output recomputation or new PR/WCC verdict.',
                        'I authored supplemental auditors and the earlier exact union audit; this review checks their frozen inclusion and scope, not an independent repeat of runtime tests.',
                        'Public privacy scan is heuristic; local paths, command lines and environment provenance remain intentional evidence.'])
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
