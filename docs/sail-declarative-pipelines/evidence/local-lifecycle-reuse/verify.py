from pathlib import Path
import hashlib
import json
import subprocess
import sys

root = Path(sys.argv[1])
packet = root / 'docs/sail-declarative-pipelines/evidence/local-lifecycle-reuse'
def digest(data):
    return hashlib.sha256(data).hexdigest()
manifest = json.loads((packet / 'provenance.json').read_text())
files = {p.relative_to(packet).as_posix() for p in packet.rglob('*') if p.is_file()}
assert files == {f['path'] for f in manifest['files']} | {'provenance.json'}
for item in manifest['files']:
    data = (packet / item['path']).read_bytes()
    assert len(data) == item['bytes'] and digest(data) == item['sha256'], item['path']
sources = json.loads((packet / 'sources.json').read_text())
for entry in sources['sources']:
    repo = sources['repositories'][entry['repository']]['path']
    obj = entry['commit'] + ':' + entry['path']
    data = subprocess.check_output(['git', '-C', repo, 'show', obj])
    assert digest(data) == entry['full_source_sha256']
    assert subprocess.check_output(['git', '-C', repo, 'rev-parse', obj]).decode().strip() == entry['git_blob_id']
    for window in entry['windows']:
        excerpt = b''.join(data.splitlines(keepends=True)[window['start_line'] - 1:window['end_line']])
        assert excerpt == (packet / window['file']).read_bytes()
        assert digest(excerpt) == window['sha256']
additional = json.loads((packet / 'lakecat-additional-sources.json').read_text())
for entry in additional['sources']:
    obj = additional['commit'] + ':' + entry['path']
    data = subprocess.check_output(['git', '-C', additional['repo'], 'show', obj])
    assert digest(data) == entry['sha256']
    assert subprocess.check_output(['git', '-C', additional['repo'], 'rev-parse', obj]).decode().strip() == entry['blob']
print('PASS lifecycle reuse source inventory; exact pinned excerpts and manifest, no runtime verdict')
