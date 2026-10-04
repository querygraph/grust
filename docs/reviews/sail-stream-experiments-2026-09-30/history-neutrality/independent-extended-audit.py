#!/usr/bin/env python3
"""Read-only exact-object audit of the 20-commit private neutrality candidate.

Writes only the explicitly requested audit receipt; never changes Git objects,
indexes, working files or refs. Run while the coordinator holds refs stable.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

PRIVATE = Path('/private/tmp/grust-review-neutral-history.git')
SHARED = Path('/Users/alexy/src/grust')
SOURCE = '5c1f7db290e3e1520015412474e8248b69df8d30'
CANDIDATE = '34a535c3f0c845c03533f1ae53ac14e8b2bb3972'
BASE = '2c3876ba3bdbff46db7c5b51a88edf738982deb3'
REF = 'refs/heads/work/neutral-review-extended'
CAPACITY = 'docs/reviews/gn-capacity-2026-09-29.md'
SEM = 'docs/SEM-REVIEW-2.md'
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
READ_COMMANDS = {'rev-parse', 'rev-list', 'cat-file', 'ls-tree', 'show-ref', 'symbolic-ref'}
NEUTRAL = (
    b'A distributed placement experiment should hold the workload, protocol and\n'
    b'resource envelope fixed and measure time and memory as resources are added.\n'
    b"The S1/S3 projection work applies to Argentea's adjacency build as much as\n"
    b"to Banda's."
)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def git(repo, *args):
    assert args[0] in READ_COMMANDS, 'read-only Git command allowlist'
    prefix = ['git', '--git-dir', str(repo)] if repo == PRIVATE else ['git', '-C', str(repo)]
    return subprocess.check_output(prefix + list(args), env=ENV)


def raw_commit(oid):
    headers, message = git(PRIVATE, 'cat-file', 'commit', oid).split(b'\n\n', 1)
    return headers.split(b'\n'), message


def tree(oid):
    rows = {}
    for entry in git(PRIVATE, 'ls-tree', '-rz', '--full-tree', oid).split(b'\0'):
        if entry:
            meta, name = entry.split(b'\t', 1)
            rows[name.decode()] = meta
    return rows


def blob(oid, name):
    return git(PRIVATE, 'cat-file', 'blob', oid + ':' + name)


def guards():
    return {
        'shared_head': git(SHARED, 'rev-parse', 'HEAD').decode().strip(),
        'shared_branch': git(SHARED, 'symbolic-ref', 'HEAD').decode().strip(),
        'candidate_ref': git(PRIVATE, 'rev-parse', REF).decode().strip(),
        'shared_refs_sha256': sha(git(SHARED, 'show-ref')),
        'private_refs_sha256': sha(git(PRIVATE, 'show-ref')),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'preserve earlier audit receipts'
    r = json.loads(args.receipt.read_bytes())
    prior_path = args.receipt.with_name('prepared-receipt.json')
    prior_bytes = prior_path.read_bytes()
    prior = json.loads(prior_bytes)
    prior_audit_path = args.receipt.with_name('independent-final-receipt.json')
    prior_audit = json.loads(prior_audit_path.read_bytes())
    assert r['old_head'] == SOURCE and r['new_head'] == CANDIDATE
    assert r['base_unchanged'] == BASE and r['candidate_ref'] == REF
    assert r['private_repository'] == str(PRIVATE)
    assert r['prior_prepared_receipt_sha256'] == sha(prior_bytes)
    assert prior_audit['mechanical_verdict'] == 'PASS'
    assert prior_audit['prepared_receipt_sha256'] == sha(prior_bytes)
    before_guards = guards()
    assert before_guards['shared_head'] == SOURCE
    assert before_guards['shared_branch'] == 'refs/heads/work/proposal-v5'
    assert before_guards['candidate_ref'] == CANDIDATE
    rows = r['commits']
    assert len(rows) == 20 and len(prior['commits']) == 16
    assert rows[:16] == prior['commits'], 'first sixteen mappings/receipts changed'
    assert [(x['old'], x['new']) for x in rows[:16]] == [
        (x['old'], x['new']) for x in prior_audit['checks']]
    for name, tip in [('old', SOURCE), ('new', CANDIDATE)]:
        observed = git(PRIVATE, 'rev-list', '--reverse', BASE + '..' + tip).decode().splitlines()
        assert observed == [x[name] for x in rows], 'range/topology mismatch'
    checks = []
    for index, record in enumerate(rows):
        old, new = record['old'], record['new']
        oh, om = raw_commit(old)
        nh, nm = raw_commit(new)
        kept = lambda lines: [line for line in lines if not line.startswith((b'tree ', b'parent '))]
        assert om == nm, ('raw message changed', old)
        assert kept(oh) == kept(nh), ('raw identity/date/extra headers changed', old)
        parents = lambda lines: [line[7:].decode() for line in lines if line.startswith(b'parent ')]
        assert parents(oh) == [BASE if index == 0 else rows[index - 1]['old']]
        assert parents(nh) == [BASE if index == 0 else rows[index - 1]['new']]
        assert parents(nh) == [record['new_parent']]
        ot, nt = tree(old), tree(new)
        assert ot.keys() == nt.keys(), ('tree path inventory differs', old)
        changed = sorted(name for name in ot if ot[name] != nt[name])
        allowed = sorted([CAPACITY, SEM] if index == 15 else [CAPACITY])
        assert changed == allowed, ('unexpected full-tree delta', old, changed)
        assert changed == sorted(x['path'] for x in record['changes'])
        files = []
        for name in changed:
            assert ot[name].split()[:2] == nt[name].split()[:2], 'mode/type changed'
            old_bytes, new_bytes = blob(old, name), blob(new, name)
            claimed = next(x for x in record['changes'] if x['path'] == name)
            assert sha(old_bytes) == claimed['before_sha256']
            assert sha(new_bytes) == claimed['after_sha256']
            if name == CAPACITY:
                # Identify the single historical paragraph fragment without
                # copying its prohibited strategy text into this audit file.
                marker = b'That is\n'
                assert old_bytes.count(marker) == 1
                start = old_bytes.index(marker)
                end = old_bytes.index(b"Banda's.", start) + len(b"Banda's.")
                assert old_bytes[:start] + NEUTRAL + old_bytes[end:] == new_bytes
                tables = lambda value: [line for line in value.splitlines() if line.startswith(b'|')]
                assert tables(old_bytes) == tables(new_bytes), 'capacity evidence table changed'
            else:
                assert index == 15
                assert sha(old_bytes) == '21e063be105306000b0ca65a62865bfe9d16fbb1861e2718efaeb7d9150e192d'
                assert sha(new_bytes) == '1b79efc36f6f6fb42140e4f08640b563ea21157fbba267d6420811a0a147750a'
                segment = lambda data, a, b: data.split(a, 1)[1].split(b, 1)[0]
                for a, b in [
                    (b'Translated from his messages of 2026-09-30:\n', b'His results ('),
                    (b'His results (', b'## 3. Where the time goes'),
                ]:
                    assert segment(old_bytes, a, b) == segment(new_bytes, a, b)
            files.append({'path': name, 'before_sha256': sha(old_bytes), 'after_sha256': sha(new_bytes)})
        sem_hash = None
        if index >= 16:
            assert ot[SEM] == nt[SEM], 'newer SEM tree blob/mode changed'
            original_sem, candidate_sem = blob(old, SEM), blob(new, SEM)
            assert original_sem == candidate_sem, 'newer SEM bytes changed'
            sem_hash = sha(original_sem)
        checks.append({
            'old': old, 'new': new, 'full_tree_entries': len(ot),
            'raw_message_sha256': sha(om),
            'identity_timestamp_extra_headers_sha256': sha(b'\n'.join(kept(oh))),
            'changed_paths': changed, 'file_hashes': files,
            'newer_sem_byte_identity_sha256': sem_hash,
        })
    after_guards = guards()
    assert after_guards == before_guards, 'source/candidate/shared refs moved during audit'
    result = {
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'auditor': 'review_pecan', 'verdict': 'PASS', 'candidate': CANDIDATE,
        'original': SOURCE, 'base': BASE, 'commits_audited': len(checks),
        'all_raw_identities_dates_messages_preserved': True,
        'linear_parent_topology_preserved': True,
        'all_twenty_full_trees_compared': True,
        'first_sixteen_mapping_records_unchanged': True,
        'new_four_capacity_fragment_only': True,
        'new_four_sem_versions_byte_identical': True,
        'capacity_tables_and_other_tree_entries_preserved': True,
        'refs_and_shared_head_unchanged': after_guards,
        'prepared_receipt_sha256': sha(args.receipt.read_bytes()),
        'prior_independent_audit_sha256': sha(prior_audit_path.read_bytes()),
        'script_sha256': sha(Path(__file__).read_bytes()), 'checks': checks,
        'scope': 'Read-only Git audit; only this executable audit and its receipt are new artifacts. No activation, fetch, reset, index/object/ref update or push. Not a runtime/benchmark verdict or a broad historical content audit.',
    }
    with args.output.open('x') as output:
        output.write(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'verdict': 'PASS', 'candidate': CANDIDATE, 'commits': len(checks),
                      'receipt': str(args.output), 'receipt_sha256': sha(args.output.read_bytes())}, indent=2))


if __name__ == '__main__':
    main()
