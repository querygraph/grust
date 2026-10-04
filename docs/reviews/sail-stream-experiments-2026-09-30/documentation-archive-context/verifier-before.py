"""Verify this documentation snapshot; no runtime benchmark verdict is implied."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head', required=True)
    args = parser.parse_args()
    root = Path(git('rev-parse', '--show-toplevel'))
    assert git('rev-parse', 'HEAD') == args.expected_head
    assert subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'],
                          capture_output=True).returncode == 1, 'gate must be detached'
    manifest_path = Path(__file__).with_name('DOCUMENTATION-SNAPSHOT.json')
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    paths = {row['path'] for row in manifest['files']}
    assert len(paths) == len(manifest['files'])
    allowed = paths | {str(manifest_path.relative_to(root))}
    changed = set(git('diff', '--name-only', manifest['base_commit']).splitlines())
    untracked = set(git('ls-files', '--others', '--exclude-standard').splitlines())
    assert changed | untracked <= allowed, sorted((changed | untracked) - allowed)
    checked_links = json_files = 0
    credential_patterns = [
        rb'AIza[0-9A-Za-z_-]{30,}',
        rb'\b(?:sk|ghp|gho|github_pat)-[A-Za-z0-9_-]{20,}',
        rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        rb'(?i)authorization\s*[:=]\s*["\x27]?(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{16,}',
    ]
    for row in manifest['files']:
        path = root / row['path']
        assert path.is_file() and not path.is_symlink(), row['path']
        data = path.read_bytes()
        assert len(data) == row['bytes'], row['path']
        assert hashlib.sha256(data).hexdigest() == row['sha256'], row['path']
        assert not any(re.search(pattern, data) for pattern in credential_patterns), (
            'credential-pattern match; inspect privately', row['path'])
        if path.suffix == '.json':
            json.loads(data)
            json_files += 1
        if path.suffix == '.md' and path.name != 'codex-to-codex.md':
            for link in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', data.decode()):
                if link.startswith(('https:', 'http:', 'mailto:', '#')):
                    continue
                target = unquote(link.strip('<>').split('#', 1)[0])
                if not target:
                    continue
                assert not Path(target).is_absolute(), ('nonportable link', row['path'], target)
                assert (path.parent / target).exists(), ('missing link', row['path'], target)
                checked_links += 1
    coordination = (root / 'codex-to-codex.md').read_text()
    assert not re.search(r'^(<<<<<<<|=======|>>>>>>>)( |$)', coordination, re.M)
    subprocess.run(['git', 'diff', '--check', manifest['base_commit'], '--',
                    '*.md', '*.py', '*.rs', '*.toml'], check=True)
    assert manifest_path.read_bytes() == manifest_bytes
    assert git('rev-parse', 'HEAD') == args.expected_head
    print(json.dumps({
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'head': args.expected_head, 'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
        'files': len(paths), 'bytes': sum(row['bytes'] for row in manifest['files']),
        'json_files': json_files, 'local_markdown_links': checked_links,
        'scope': 'documentation hashes, local links, JSON syntax, conflict markers, selected whitespace and heuristic credential patterns; no new runtime gate',
    }, indent=2))
    print('SAIL_REVIEW_DOCUMENTATION PASSED ' + args.expected_head)


if __name__ == '__main__':
    main()
