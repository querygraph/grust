"""Local filesystem and mocked container-identity controls; no Docker calls."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p, s, entry = load('prepare'), load('supervise'), load('container_check')


class Permissions(unittest.TestCase):
    def test_restrictive_umask_new_bundle_and_output_modes(self):
        with tempfile.TemporaryDirectory(prefix='physical-modes-') as directory:
            root = Path(directory)
            src = root / 'source'; src.write_text('preserved bytes')
            bundle, output = root / 'bundle', root / 'evidence'
            old = os.umask(0o077)
            try:
                p.create_bundle_directory(bundle)
                pin = p.copy_bundle({'entry.py': src}, {'entry.py': p.sha(src)}, bundle)
                p.save(bundle / 'request.json', {'execution_identity': s.IDENTITY, 'files': pin})
                s.create_evidence_directory(output)
            finally:
                os.umask(old)
            self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o755)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            for name in ('entry.py', 'request.json'):
                self.assertEqual(stat.S_IMODE((bundle / name).stat().st_mode), 0o644)
            self.assertEqual((bundle / 'entry.py').read_bytes(), src.read_bytes())
            with patch.object(s.os, 'getuid', return_value=501), patch.object(s.os, 'getgid', return_value=20):
                s.validate_bundle_permissions(bundle, json.loads((bundle / 'request.json').read_text()))

    def test_wrong_staging_mode_rejected_without_repair(self):
        with tempfile.TemporaryDirectory(prefix='physical-modes-') as directory:
            root = Path(directory); root.chmod(0o700)
            req = {'execution_identity': s.IDENTITY, 'files': {}}
            (root / 'request.json').write_text('{}'); (root / 'request.json').chmod(0o644)
            with patch.object(s.os, 'getuid', return_value=501), patch.object(s.os, 'getgid', return_value=20):
                with self.assertRaisesRegex(ValueError, 'bundle mode'):
                    s.validate_bundle_permissions(root, req)
                self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
                root.chmod(0o755); (root / 'request.json').chmod(0o600)
                with self.assertRaisesRegex(ValueError, 'file mode'):
                    s.validate_bundle_permissions(root, req)
                self.assertEqual(stat.S_IMODE((root / 'request.json').stat().st_mode), 0o600)

    def test_existing_output_never_chmod_or_reused(self):
        with tempfile.TemporaryDirectory(prefix='physical-modes-') as directory:
            p = Path(directory) / 'existing'; p.mkdir(); p.chmod(0o755)
            (p / 'old').write_text('old evidence')
            with self.assertRaises(FileExistsError): s.create_evidence_directory(p)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o755)
            self.assertEqual((p / 'old').read_text(), 'old evidence')

    def test_host_or_request_identity_mismatch_rejected(self):
        req = {'execution_identity': s.IDENTITY, 'files': {}}
        with patch.object(s.os, 'getuid', return_value=0), patch.object(s.os, 'getgid', return_value=20):
            with self.assertRaisesRegex(ValueError, 'host UID/GID'):
                s.validate_bundle_permissions(Path('/unused'), req)
        req = copy.deepcopy(req); req['execution_identity']['container_user'] = '0:0'
        with self.assertRaisesRegex(ValueError, 'execution identity'):
            s.validate_bundle_permissions(Path('/unused'), req)

    def test_container_identity_and_mounted_modes_actual_fixture(self):
        with tempfile.TemporaryDirectory(prefix='physical-mounts-') as directory:
            root = Path(directory); work = root / 'work'; work.mkdir(); work.chmod(0o755)
            file = work / 'container_check.py'; file.write_text('fixture'); file.chmod(0o644)
            evidence = root / 'evidence'; s.create_evidence_directory(evidence)
            self.assertEqual(evidence.stat().st_uid, 501, 'control requires disclosed local UID501')
            mapping = {'/work': work, '/work/container_check.py': file, '/evidence': evidence}
            with patch.object(entry, 'Path', side_effect=lambda path: mapping[path]), patch.object(entry.os, 'getuid', return_value=501), patch.object(entry.os, 'getgid', return_value=20):
                report = {}; entry.validate_reader_permissions({'execution_identity': s.IDENTITY}, report)
                self.assertEqual(report['reader_identity'], {'uid':501,'gid':20})
                evidence.chmod(0o777)
                with self.assertRaisesRegex(ValueError, 'evidence owner/mode'):
                    entry.validate_reader_permissions({'execution_identity': s.IDENTITY}, {})
            with patch.object(entry.os, 'getuid', return_value=0), patch.object(entry.os, 'getgid', return_value=0):
                with self.assertRaisesRegex(ValueError, 'container UID/GID'):
                    entry.validate_reader_permissions({'execution_identity': s.IDENTITY}, {})

    def test_recorded_failure_mode_has_no_other_search_permission(self):
        # POSIX mode arithmetic only: does not claim a second UID/container was run.
        self.assertEqual(0o700 & stat.S_IXOTH, 0)
        self.assertNotEqual(0o755 & stat.S_IXOTH, 0)
        self.assertEqual(0o700 & stat.S_IWOTH, 0)
        self.assertNotEqual(0o700 & stat.S_IWUSR, 0)


if __name__ == '__main__':
    unittest.main()
