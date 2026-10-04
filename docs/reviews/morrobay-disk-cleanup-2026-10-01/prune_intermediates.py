"""Remove explicitly inventoried Cargo intermediates, preserving executable files."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys

plan = json.loads(sys.argv[1])
roots = [Path(p) for p in plan['roots']]
evidence = Path(plan['evidence'])
evidence.mkdir(parents=True, exist_ok=False)
suffixes = {'.rlib', '.rmeta', '.o', '.d'}


def identity(path):
    s = path.lstat()
    return dict(device=s.st_dev, inode=s.st_ino, bytes=s.st_size,
                mtime_ns=s.st_mtime_ns, mode=s.st_mode, allocated_bytes=s.st_blocks*512)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


protected = {str(Path(p)): sha(Path(p)) for p in plan.get('protected_files', [])}
selected, preserved = [], {}
for root in roots:
    assert root.is_dir() and not root.is_symlink() and root.resolve() == root, root
    assert root.name in ('deps', 'incremental'), root
    assert root.parent.name in ('debug', 'release'), root
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(directory)/d).is_symlink()]
        for name in files:
            p = Path(directory)/name
            s = identity(p)
            if stat.S_ISREG(s['mode']) and not (s['mode'] & 0o111) and p.suffix in suffixes:
                selected.append(dict(path=str(p), **s))
            else:
                preserved[str(p)] = s
    for p in root.parent.iterdir():
        if p.is_file():
            preserved[str(p)] = identity(p)

receipt = dict(started_utc=datetime.now(timezone.utc).isoformat(), plan=plan,
    before_free_bytes=shutil.disk_usage(roots[0]).free, selected_files=len(selected),
    selected_logical_bytes=sum(r['bytes'] for r in selected),
    selected_allocated_bytes=sum(r['allocated_bytes'] for r in selected),
    protected_sha256_before=protected, deleted_files=0, outcome='error')
with (evidence/'selected.jsonl').open('x') as f:
    for r in selected:
        f.write(json.dumps(r)+'\n')
    f.flush()
    os.fsync(f.fileno())
try:
    for row in selected:
        p = Path(row['path'])
        assert identity(p) == {k:v for k,v in row.items() if k != 'path'}, 'candidate changed: '+str(p)
        p.unlink()
        receipt['deleted_files'] += 1
    assert all(identity(Path(p)) == s for p,s in preserved.items()), 'preserved artifact changed'
    receipt['protected_sha256_after'] = {p:sha(Path(p)) for p in protected}
    assert receipt['protected_sha256_after'] == protected, 'protected input/runtime changed'
    receipt.update(outcome='passed', preserved_files_checked=len(preserved))
finally:
    receipt.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                   after_free_bytes=shutil.disk_usage(roots[0]).free,
                   selected_manifest_sha256=sha(evidence/'selected.jsonl'))
    with (evidence/'receipt.json').open('x') as f:
        json.dump(receipt,f,indent=2)
        f.write('\n')
    print(json.dumps(receipt),flush=True)
