"""Verify this documentation snapshot; no runtime benchmark verdict is implied."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.parse import unquote


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def canonical_relative(name):
    assert isinstance(name, str) and name and '\\' not in name, 'invalid context path'
    path = PurePosixPath(name)
    assert not path.is_absolute() and '..' not in path.parts and path.as_posix() == name, (
        'noncanonical context path', name)
    return Path(name)


def safe_path(root, name):
    current = root
    for part in canonical_relative(name).parts:
        current /= part
        assert not current.is_symlink(), ('symlink in documentation path', name)
    return current


def rows_by_path(manifest):
    rows = manifest['files']
    assert isinstance(rows, list), 'manifest files must be a list'
    result = {}
    for row in rows:
        name = row['path']
        canonical_relative(name)
        assert name not in result, ('duplicate manifest path', name)
        result[name] = row
    return result


def checked_bytes(root, name, rows):
    assert name in rows, ('context source not in snapshot', name)
    path = safe_path(root, name)
    assert path.is_file(), ('context source missing', name)
    data = path.read_bytes()
    row = rows[name]
    assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], (
        'context source bytes differ', name)
    return data


def markdown_link_contexts(root, manifest):
    """Prove retained Markdown bytes against their original source manifest.

    This changes only a verified archive's link base. Every link is still checked.
    The current snapshot hashes the archive and retained source manifest as files.
    """
    contexts = manifest.get('archived_markdown_link_contexts', {})
    assert isinstance(contexts, dict), 'archive contexts must be an object'
    rows = rows_by_path(manifest)
    bases = {}
    for archived, context in contexts.items():
        assert isinstance(context, dict) and set(context) == {'original_path', 'source_manifest'}, (
            'unknown archive context fields', archived)
        original, source = context['original_path'], context['source_manifest']
        for name in (archived, original, source):
            canonical_relative(name)
            assert name in rows, ('unknown archive context path', name)
        assert archived != original and Path(archived).suffix == Path(original).suffix == '.md', (
            'archive context requires distinct Markdown paths', archived)
        assert Path(source).suffix == '.json', 'source manifest must be JSON'
        data = checked_bytes(root, archived, rows)
        historical = rows_by_path(json.loads(checked_bytes(root, source, rows)))
        assert original in historical, ('original path absent from source manifest', original)
        proof = historical[original]
        assert proof['bytes'] == len(data) and proof['sha256'] == hashlib.sha256(data).hexdigest(), (
            'archive differs from original source row', archived)
        origin = safe_path(root, original)
        assert origin.is_file(), ('original link context absent', original)
        bases[archived] = origin.parent
    return bases


def check_markdown_links(root, path, data, base=None):
    count = 0
    for link in re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', data.decode()):
        if link.startswith(('https:', 'http:', 'mailto:', '#')):
            continue
        target = unquote(link.strip('<>').split('#', 1)[0])
        if not target:
            continue
        assert not Path(target).is_absolute() and '\\' not in target, ('nonportable link', path, target)
        resolved = Path(os.path.normpath((base or path.parent) / target))
        assert resolved.is_relative_to(root), ('link escapes repository', path, target)
        checked = safe_path(root, str(resolved.relative_to(root)))
        assert checked.exists(), ('missing link', path, target)
        count += 1
    return count


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
    link_contexts = markdown_link_contexts(root, manifest)
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
            checked_links += check_markdown_links(root, path, data, link_contexts.get(row['path']))
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
        'archived_markdown_contexts': len(link_contexts),
        'scope': 'documentation hashes, local links, JSON syntax, conflict markers, selected whitespace and heuristic credential patterns; no new runtime gate',
    }, indent=2))
    print('SAIL_REVIEW_DOCUMENTATION PASSED ' + args.expected_head)


if __name__ == '__main__':
    main()
