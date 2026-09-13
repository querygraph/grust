#!/usr/bin/env python3
"""Record one local full-path run with disclosed process resource boundaries."""
import argparse
import datetime
import json
import hashlib
import os
from pathlib import Path
import platform
import resource
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('mode', choices=['direct', 'cypher'])
parser.add_argument('nodes', type=int)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
binary = root / 'target/release/examples/full_path_receipt'
cpus = sorted(os.sched_getaffinity(0))[:2]
address_space_bytes = 4 * 1024**3

def envelope():
    os.sched_setaffinity(0, cpus)
    resource.setrlimit(resource.RLIMIT_AS, (address_space_bytes, address_space_bytes))

binary_sha256 = hashlib.sha256(binary.read_bytes()).hexdigest()
source_hash = hashlib.sha256()
source_paths = [root / 'Cargo.toml', root / 'Cargo.lock']
for name in ['grust-core', 'grust-procedures', 'grust-algorithms', 'grust-cypher', 'grust-algorithm-procedures']:
    crate = root / 'crates' / name
    source_paths.extend(crate.rglob('*.rs'))
    source_paths.append(crate / 'Cargo.toml')
for path in sorted(source_paths):
    source_hash.update(str(path.relative_to(root)).encode())
    source_hash.update(b'\0')
    source_hash.update(path.read_bytes())
source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
previous_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
started = time.monotonic()
command = [str(binary), args.mode, str(args.nodes)]
result = subprocess.run(command, text=True, capture_output=True, preexec_fn=envelope, check=False)
usage = resource.getrusage(resource.RUSAGE_CHILDREN)
try:
    payload = json.loads(result.stdout)
except json.JSONDecodeError:
    payload = None
receipt = {
    'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'execution_class': 'local_materialized_snapshot',
    'command': command,
    'binary_sha256': binary_sha256,
    'source_commit': source_commit,
    'source_tree_sha256': source_hash.hexdigest(),
    'source_boundary': 'working source tree digest; commit may predate uncommitted implementation',
    'platform': platform.platform(),
    'cpu_affinity': cpus,
    'cpu_boundary': 'two logical CPUs by affinity; not a container CPU quota',
    'address_space_limit_bytes': address_space_bytes,
    'memory_boundary': 'RLIMIT_AS virtual address space plus application admission; not a cgroup RSS ceiling',
    'wall_seconds': time.monotonic() - started,
    'user_seconds': usage.ru_utime - previous_usage.ru_utime,
    'system_seconds': usage.ru_stime - previous_usage.ru_stime,
    'max_rss_kib': usage.ru_maxrss,
    'exit_code': result.returncode,
    'status': 'pass' if result.returncode == 0 and payload is not None else 'error',
    'result': payload,
    'stdout': result.stdout,
    'stderr': result.stderr,
}
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open('x') as handle:
    json.dump(receipt, handle, indent=2)
    handle.write('\n')
print(json.dumps(receipt))
raise SystemExit(result.returncode)
