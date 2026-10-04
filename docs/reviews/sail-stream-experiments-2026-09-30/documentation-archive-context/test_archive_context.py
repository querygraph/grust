"""Offline controls for the exact verifier's archived Markdown link handling."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent/'verify_documentation_snapshot.py'
spec = importlib.util.spec_from_file_location('snapshot_verifier', SOURCE)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
ARCHIVE = 'evidence/attempt/RESULTS.md'
ORIGINAL = 'docs/RESULTS.md'
SOURCE_MANIFEST = 'evidence/attempt/MANIFEST.json'
BODY = b'[local](target.json) [parent](../other.md) [external](https://example.invalid) [anchor](#ok)\n'


def row(path, data):
    return dict(path=path, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


class ArchiveContext(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='archive-context-control-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        values = {ARCHIVE:BODY, ORIGINAL: b'Current prose intentionally differs.\n',
                  'docs/target.json':b'{}\n', 'other.md':b'Target\n'}
        values[SOURCE_MANIFEST] = json.dumps({'files':[row(ORIGINAL,BODY)]}).encode()
        for name, data in values.items():
            p = self.root/name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        self.manifest = dict(files=[row(n,d) for n,d in values.items()],
            archived_markdown_link_contexts={ARCHIVE:dict(original_path=ORIGINAL,source_manifest=SOURCE_MANIFEST)})

    def contexts(self):
        return v.markdown_link_contexts(self.root,self.manifest)

    def check_links(self, body=BODY):
        bases = self.contexts()
        return v.check_markdown_links(self.root,self.root/ARCHIVE,body,bases[ARCHIVE])

    def repin(self,name):
        self.manifest['files'] = [r for r in self.manifest['files'] if r['path']!=name]
        self.manifest['files'].append(row(name,(self.root/name).read_bytes()))

    def test_valid_context_checks_both_relative_targets(self):
        self.assertEqual(self.check_links(),2)

    def test_absent_context_reproduces_original_missing_link(self):
        self.manifest.pop('archived_markdown_link_contexts')
        self.assertEqual(self.contexts(),{})
        with self.assertRaisesRegex(AssertionError,'missing link'):
            v.check_markdown_links(self.root,self.root/ARCHIVE,BODY)

    def test_missing_mapped_target_still_fails(self):
        (self.root/'docs/target.json').unlink()
        with self.assertRaisesRegex(AssertionError,'missing link'):
            self.check_links()

    def test_archive_current_hash_mismatch_fails(self):
        (self.root/ARCHIVE).write_bytes(BODY+b'changed')
        with self.assertRaisesRegex(AssertionError,'context source bytes differ'):
            self.contexts()

    def test_rehashed_archive_without_original_proof_fails(self):
        (self.root/ARCHIVE).write_bytes(BODY+b'changed');self.repin(ARCHIVE)
        with self.assertRaisesRegex(AssertionError,'archive differs from original source row'):
            self.contexts()

    def test_source_manifest_current_hash_mismatch_fails(self):
        (self.root/SOURCE_MANIFEST).write_text('{}')
        with self.assertRaisesRegex(AssertionError,'context source bytes differ'):
            self.contexts()

    def test_wrong_historical_bytes_or_hash_fails(self):
        for key,value in [('bytes',len(BODY)+1),('sha256','0'*64)]:
            with self.subTest(key=key):
                proof=row(ORIGINAL,BODY);proof[key]=value
                (self.root/SOURCE_MANIFEST).write_text(json.dumps({'files':[proof]}));self.repin(SOURCE_MANIFEST)
                with self.assertRaisesRegex(AssertionError,'archive differs from original source row'):
                    self.contexts()

    def test_wrong_original_without_historical_row_fails(self):
        self.manifest['archived_markdown_link_contexts'][ARCHIVE]['original_path']='other.md'
        with self.assertRaisesRegex(AssertionError,'original path absent'):
            self.contexts()

    def test_unknown_mapping_paths_fields_and_type_fail(self):
        for mutation in ['archive','original','source','field','type']:
            with self.subTest(mutation=mutation):
                old=copy.deepcopy(self.manifest)
                c=self.manifest['archived_markdown_link_contexts']
                if mutation=='archive':c['missing.md']=c.pop(ARCHIVE)
                elif mutation=='original':c[ARCHIVE]['original_path']='missing.md'
                elif mutation=='source':c[ARCHIVE]['source_manifest']='missing.json'
                elif mutation=='field':c[ARCHIVE]['ignore_missing']=True
                else:self.manifest['archived_markdown_link_contexts']=[]
                with self.assertRaises(AssertionError):self.contexts()
                self.manifest=old

    def test_mapping_paths_are_canonical(self):
        for name in ['../RESULTS.md','/tmp/RESULTS.md','docs/../RESULTS.md','docs//RESULTS.md','./docs/RESULTS.md','docs\\RESULTS.md']:
            with self.subTest(name=name):
                self.manifest['archived_markdown_link_contexts'][ARCHIVE]['original_path']=name
                with self.assertRaises(AssertionError):self.contexts()

    def test_duplicate_source_manifest_rows_fail(self):
        proof=row(ORIGINAL,BODY)
        (self.root/SOURCE_MANIFEST).write_text(json.dumps({'files':[proof,proof]}));self.repin(SOURCE_MANIFEST)
        with self.assertRaisesRegex(AssertionError,'duplicate manifest path'):self.contexts()

    def test_source_manifest_and_original_symlinks_fail(self):
        for name in [SOURCE_MANIFEST,ORIGINAL]:
            with self.subTest(name=name):
                p=self.root/name; data=p.read_bytes(); p.unlink()
                target=self.root/'actual';target.write_bytes(data);p.symlink_to(target)
                with self.assertRaisesRegex(AssertionError,'symlink'):self.contexts()
                p.unlink();p.write_bytes(data);target.unlink()

    def test_symlink_ancestor_fails(self):
        docs=self.root/'docs';moved=self.root/'real-docs';docs.rename(moved);docs.symlink_to(moved,target_is_directory=True)
        with self.assertRaisesRegex(AssertionError,'symlink'):self.contexts()

    def test_mapped_link_cannot_escape_repository(self):
        for body in [b'[bad](../../outside.md)',b'[bad](%2Ftmp/outside.md)',b'[bad](..%2F..%2Foutside.md)']:
            with self.subTest(body=body),self.assertRaises(AssertionError):self.check_links(body)

    def test_mapped_link_cannot_follow_symlink(self):
        p=self.root/'docs/target.json';p.unlink();p.symlink_to(self.root/'other.md')
        with self.assertRaisesRegex(AssertionError,'symlink'):self.check_links()

    def test_ordinary_document_missing_target_still_fails(self):
        with self.assertRaisesRegex(AssertionError,'missing link'):
            v.check_markdown_links(self.root,self.root/ORIGINAL,b'[bad](absent.json)')


if __name__=='__main__':
    unittest.main()
