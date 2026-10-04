"""Private synthetic-fixture controls; never operate the real publication repos."""
import copy
import shutil
import tempfile
from pathlib import Path
import common as c

output = c.OUT/'offline-controls02'
output.mkdir(exist_ok=False)
real_src = c.SRC
results = []


def test(name, operation):
    operation()
    results.append(dict(name=name, outcome='PASS'))


def rejected(operation, expected):
    try:
        operation()
    except RuntimeError as error:
        c.check(expected in str(error), 'unexpected rejection: '+str(error))
    else:
        raise AssertionError('missing rejection: '+expected)


try:
    with tempfile.TemporaryDirectory(prefix='grust-docs-tooling-control-', dir='/private/tmp') as directory:
        root = Path(directory)
        c.SRC = root
        c.git(root, 'init', '-q', '-b', 'work/proposal-v5')
        c.git(root, 'remote', 'add', 'origin', c.ORIGIN)
        files = {c.COORD: b'base section\npreviously inserted historical entry\nlast base section\n',
                 c.REL/'RESULTS.md': b'reviewed results\n',
                 c.REL/'COMPACT-REPLAY-AND-SSSP.md': b'reviewed compact result\n',
                 Path('docs/SEM-REVIEW-2.md'): b'reviewed SEM input\n',
                 Path('docs/STREAM-LOSS-STATUS.md'): b'reviewed stream input\n',
                 c.REL/'sssp-candidate-buffer-reuse/exact-gate/receipt.json': b'{"verdict":"PASS"}\n',
                 c.REL/'sssp-candidate-buffer-reuse/final-receipt.json': b'{"outcome":"EXACT_COMPONENT_GATE_PASS"}\n',
                 c.REL/'sssp-candidate-buffer-reuse-delivery.json': b'{"outcome":"PUSHED_AND_REMOTELY_VERIFIED"}\n'}
        files.update({Path(name):b'{}\n' for name in c.REQUIRED_CLOSURES if Path(name) not in files})
        files.update({Path(name):b'synthetic gzip bytes\n' for name in c.BINARY_PINS})
        for relative, data in files.items():
            (root/relative).parent.mkdir(parents=True, exist_ok=True)
            (root/relative).write_bytes(data)
        c.git(root, 'add', '.')
        c.git(root, '-c', 'user.name=Offline Control', '-c', 'user.email=control@example.invalid',
              '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Synthetic fixture')
        selected = str(c.REL/'sssp-candidate-buffer-reuse/exact-gate/receipt.json')
        final = str(c.REL/'sssp-candidate-buffer-reuse/final-receipt.json')
        delivery = str(c.REL/'sssp-candidate-buffer-reuse-delivery.json')
        preparation = dict(shared_before=c.shared_state(), selected_sources={name:c.info(root/name) for name in c.REQUIRED_CLOSURES | set(c.BINARY_PINS)})
        test('unchanged_shared_state', lambda: c.check_shared(preparation))
        original = (root/c.COORD).read_bytes()
        def appended():
            (root/c.COORD).write_bytes(original+b'\nbenign appended coordination\n')
            result = c.check_shared(preparation)
            c.check(result['appended_coordination_bytes'] == len(b'\nbenign appended coordination\n'), 'append count')
            (root/c.COORD).write_bytes(original)
        test('append_only_coordination_accepted', appended)
        def coord_reject(data, expected):
            (root/c.COORD).write_bytes(data)
            rejected(lambda:c.check_shared(preparation), expected)
            (root/c.COORD).write_bytes(original)
        test('historical_coordination_edit_rejected', lambda:coord_reject(original.replace(b'historical',b'CHANGEDold'), 'prefix edited'))
        test('coordination_truncation_rejected', lambda:coord_reject(original[:-1], 'truncated'))
        def file_change(relative, expected):
            path = root/relative
            old = path.read_bytes()
            path.write_bytes(old+b'changed\n')
            rejected(lambda:c.check_shared(preparation), expected)
            path.write_bytes(old)
        for relative in sorted(c.REVIEW_INPUTS):
            test('review_input_change_rejected:'+str(relative), lambda relative=relative:file_change(relative, 'review_inputs changed'))
        test('results_change_rejected', lambda:file_change(c.REL/'RESULTS.md', 'prose changed'))
        test('selected_evidence_change_rejected', lambda:file_change(Path(selected), 'selected source changed'))
        def index_change():
            path = root/c.COORD
            path.write_bytes(original+b'new staged suffix\n')
            c.git(root, 'add', str(c.COORD))
            rejected(lambda:c.check_shared(preparation), 'index changed')
            c.git(root, 'reset', '-q', 'HEAD', '--', str(c.COORD))
            path.write_bytes(original)
        test('shared_index_change_rejected', index_change)
        def push_destination_change():
            c.git(root, 'remote', 'set-url', '--push', 'origin', 'git@example.invalid:wrong/repository.git')
            rejected(lambda:c.check_shared(preparation), 'origin destination changed')
            c.git(root, 'config', '--unset-all', 'remote.origin.pushurl')
        test('push_destination_change_rejected', push_destination_change)
        def ancestor_symlink():
            (root/'elsewhere').mkdir()
            (root/'linked').symlink_to(root/'elsewhere', target_is_directory=True)
            rejected(lambda:c.safe_path(root, 'linked/file.json'), 'symlink in selected path')
        test('selected_ancestor_symlink_rejected', ancestor_symlink)
        for name in ('logging03/cell.json', 'followup02/receipt.json', 'host-pair-16k/new-cell.json', 'host-pair-execution/new-cell.json', 'resource-validation-union/receipt.json'):
            test('active_scope_rejected:'+name, lambda name=name:rejected(lambda:c.selected_path(str(c.REL/name)), 'outside fixed preparation scope'))
        auth = dict(archived_markdown_link_contexts=copy.deepcopy(c.ARCHIVE_CONTEXTS), status='AUTHORIZED_FROZEN_INPUTS', base=c.BASE, scope='Offline synthetic test only',
                    coordination_title='ACK synthetic', coordination_body='Synthetic fixture',
                    commit_message='Synthetic fixture', activation_done_body='Synthetic {commit}',
                    cutoff='Synthetic closed boundary', excluded_scopes=['all active runs'],
                    selected_sources=preparation['selected_sources'],
                    required_json=[dict(path=path, equals=copy.deepcopy(predicates))
                                   for path, predicates in c.CLOSURE_PREDICATES.items()])
        auth['selected_sources'] = copy.deepcopy(auth['selected_sources'])
        for path, digest in c.CLOSED_PINS.items():
            auth['selected_sources'][path]['sha256'] = digest
        for path, expected in c.BINARY_PINS.items():
            auth['selected_sources'][path] = copy.deepcopy(expected)
        test('well_formed_authorization_accepted', lambda:c.validate_authorization(auth))
        test('verifier_edit_rejected', lambda:rejected(lambda:c.selected_path(str(c.REL/'verify_documentation_snapshot.py')), 'outside fixed preparation scope'))
        test('prior_archive_context_unchanged', lambda:c.check(len(c.ARCHIVE_CONTEXTS)==1 and 'documentation-validation-publication/preparation-attempt01/RESULTS.md' in next(iter(c.ARCHIVE_CONTEXTS)), 'archive context changed'))
        for context in ({}, None, {'unknown':{}}):
            changed=copy.deepcopy(auth);changed['archived_markdown_link_contexts']=context
            test('wrong_archive_context_rejected:'+str(context),lambda changed=changed:rejected(lambda:c.validate_authorization(changed),'reviewed archive link context differs'))
        test('prior_component_selection_rejected', lambda:rejected(lambda:c.selected_path(str(c.REL/'argentea-cursor-lease-control/final-receipt.json')), 'outside fixed preparation scope'))
        for path in c.REQUIRED_CLOSURES:
            changed=copy.deepcopy(auth)
            predicates=next(x for x in changed['required_json'] if x['path']==path)['equals']
            predicates[next(iter(predicates))]='wrong'
            test('wrong_expanded_identity_rejected:'+path, lambda changed=changed:rejected(lambda:c.validate_authorization(changed),'closed evidence predicates differ'))
        for path in c.CLOSED_PINS:
            changed=copy.deepcopy(auth); changed['selected_sources'][path]['sha256']='0'*64
            test('wrong_closed_receipt_hash_rejected:'+path, lambda changed=changed:rejected(lambda:c.validate_authorization(changed),'closed evidence receipt hash differs'))
        changed=copy.deepcopy(auth)
        old=str(c.REL/'sssp-candidate-buffer-reuse/candidate-gate/receipt.json')
        changed['selected_sources'][old]=changed['selected_sources'].pop(selected)
        next(x for x in changed['required_json'] if x['path']==selected)['path']=old
        test('intermediate_exact_gate_rejected', lambda:rejected(lambda:c.validate_authorization(changed),'component, physical check and package closure receipts required'))
        binary_path=next(iter(c.BINARY_PINS))
        test('sole_named_gzip_allowed', lambda:c.selected_path(binary_path))
        for name in ('logging03-publication/other.tar.gz', 'logging03-monitor/private.gz',
                     'logging03-publication/diagnostics.tar', 'logging03-publication/raw.parquet'):
            test('unapproved_binary_rejected:'+name, lambda name=name:rejected(
                lambda:c.selected_path(str(c.REL/name)), 'private/binary data selected'))
        for key,value in [('sha256','0'*64),('bytes',13848617),('mode','0o755')]:
            changed=copy.deepcopy(auth);changed['selected_sources'][binary_path][key]=value
            test('changed_gzip_pin_rejected:'+key, lambda changed=changed:rejected(
                lambda:c.validate_authorization(changed), 'binary exception pin differs'))
        changed=copy.deepcopy(auth);del changed['selected_sources'][binary_path]
        test('missing_gzip_rejected', lambda:rejected(lambda:c.validate_authorization(changed),
             'closed diagnostics package missing'))
        def unexpected_binary_content():
            path=root/'unexpected.data';path.write_bytes(b'\xff\x80')
            rejected(lambda:c.check_selected_content(path,'unexpected.data'),'unapproved non-text')
            path.write_bytes(b'abc\0def')
            rejected(lambda:c.check_selected_content(path,'unexpected.data'),'unapproved NUL-bearing')
            path.write_text('valid ordinary text\n')
            c.check_selected_content(path,'ordinary.log')
        test('unfamiliar_binary_extension_rejected',unexpected_binary_content)
        test('same_gzip_path_wrong_actual_bytes_rejected',lambda:rejected(
            lambda:c.check_selected_content(root/binary_path,binary_path),'binary exception content differs'))
        for key, value, reason in [('status','DRAFT_NOT_AUTHORIZED','inputs not authorized'),
                                   ('excluded_scopes',None,'missing exclusions'),
                                   ('commit_message',{},'missing reviewed prose'),
                                   ('required_json',[],'missing closure guards')]:
            changed=copy.deepcopy(auth); changed[key]=value
            test('invalid_authorization_rejected:'+key, lambda changed=changed,reason=reason:rejected(lambda:c.validate_authorization(changed),reason))
        for path in c.REQUIRED_CLOSURES:
            changed=copy.deepcopy(auth)
            changed['required_json']=[item for item in changed['required_json'] if item['path'] != path]
            test('missing_component_closure_rejected:'+path,
                 lambda changed=changed:rejected(lambda:c.validate_authorization(changed),
                     'component, physical check and package closure receipts required'))
    receipt=dict(recorded_utc=c.utc(), outcome='PASS_OFFLINE_TOOLING_CONTROLS', controls=results,
                 count=len(results), production_helpers={name:c.sha(c.OUT/name) for name in
                    ('common.py','prepare_snapshot.py','guard.py','commit_and_gate.sh','publish.py','activate_shared.py')},
                 control_source_sha256=c.sha(Path(__file__)),
                 scope='Synthetic temporary local Git fixture only; no network, publication snapshot, documentation gate, commit/push/activation on actual repositories, or runtime validation.')
    c.write_new(output/'receipt.json',receipt)
except BaseException as error:
    c.write_new(output/'failure.json',dict(recorded_utc=c.utc(),outcome='FAIL',error=repr(error),completed=results))
    raise
finally:
    c.SRC=real_src
print('OFFLINE_TOOLING_CONTROLS PASSED',len(results))
