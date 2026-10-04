"""Small private fixtures; no production collection or remote access."""
import gzip
import io
import json
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch
import rehydrate as r


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='logging03-package-controls-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package = self.root / 'package'
        self.package.mkdir()
        self.destination = self.root / 'restored'
        self.raw_tar = self.root / 'raw.tar'
        self.make_archive([('receipt.json', b'{"outcome":"fixture"}\n', 'file')])
        (self.package / 'metadata').mkdir()
        (self.package / 'metadata/result.json').write_bytes(b'{"fixture":true}\n')
        self.seal()

    def make_archive(self, entries):
        with tarfile.open(self.raw_tar, 'w') as archive:
            for name, data, kind in entries:
                item = tarfile.TarInfo(name)
                if kind == 'symlink':
                    item.type = tarfile.SYMTYPE
                    item.linkname = '/tmp/outside'
                    archive.addfile(item)
                else:
                    item.size = len(data)
                    archive.addfile(item, io.BytesIO(data))
        with (self.package / 'diagnostics.tar.gz').open('wb') as target:
            with gzip.GzipFile(filename='', mode='wb', mtime=0, compresslevel=9, fileobj=target) as zipped:
                zipped.write(self.raw_tar.read_bytes())

    def seal(self, members=None):
        if members is None:
            members = r.archive_members(self.raw_tar)
        raw = {'diagnostics.tar': r.fingerprint(self.raw_tar),
               'result.json': r.fingerprint(self.package / 'metadata/result.json')}
        raw.update({'diagnostics/' + name: pin for name, pin in members.items()})
        manifest = {'schema': 'logging03-lossless-package-v1', 'raw_tree': raw,
                    'archive_members': members, 'rehydration_helper': r.fingerprint(Path(r.__file__)),
                    'package_files': {name: r.fingerprint(self.package / name) for name in ['diagnostics.tar.gz', 'metadata/result.json']}}
        (self.package / 'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def test_exact_roundtrip(self):
        report = r.restore(self.package, self.destination)
        self.assertEqual(report['outcome'], 'EXACT_RAW_COLLECTION_RESTORED')
        self.assertEqual((self.destination / 'diagnostics.tar').read_bytes(), self.raw_tar.read_bytes())
        self.assertEqual((self.destination / 'diagnostics/receipt.json').read_bytes(), b'{"outcome":"fixture"}\n')

    def test_wrong_gzip_hash(self):
        with (self.package / 'diagnostics.tar.gz').open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'package file hash'):
            r.restore(self.package, self.destination)
        self.assertFalse(self.destination.exists())

    def test_wrong_raw_hash(self):
        manifest = self.seal()
        manifest['raw_tree']['diagnostics.tar']['sha256'] = '0' * 64
        (self.package / 'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'original archive hash'):
            r.restore(self.package, self.destination)

    def test_symlink_archive(self):
        self.make_archive([('receipt.json', b'', 'symlink')])
        self.seal({})
        with self.assertRaisesRegex(ValueError, 'regular files'):
            r.restore(self.package, self.destination)
        self.assertFalse((self.root / 'outside').exists())

    def test_path_traversal(self):
        self.make_archive([('../escaped', b'bad', 'file')])
        self.seal({})
        with self.assertRaisesRegex(ValueError, 'noncanonical'):
            r.restore(self.package, self.destination)
        self.assertFalse((self.root / 'escaped').exists())

    def test_duplicate_member(self):
        self.make_archive([('receipt.json', b'a', 'file'), ('receipt.json', b'b', 'file')])
        self.seal({})
        with self.assertRaisesRegex(ValueError, 'unique flat'):
            r.restore(self.package, self.destination)

    def test_missing_metadata(self):
        (self.package / 'metadata/result.json').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            r.restore(self.package, self.destination)

    def test_no_overwrite(self):
        self.destination.mkdir()
        with self.assertRaisesRegex(ValueError, 'must not exist'):
            r.restore(self.package, self.destination)

    def test_package_symlink(self):
        path = self.package / 'metadata/result.json'
        path.unlink()
        target = self.root / 'other'
        target.write_text('{}')
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            r.restore(self.package, self.destination)

    def test_disk_admission(self):
        with patch.object(r.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 0})()):
            with self.assertRaisesRegex(ValueError, 'insufficient'):
                r.restore(self.package, self.destination)
        self.assertFalse(self.destination.exists())


if __name__ == '__main__':
    unittest.main()
