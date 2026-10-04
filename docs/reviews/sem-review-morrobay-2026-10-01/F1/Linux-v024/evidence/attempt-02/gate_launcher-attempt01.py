"""Durably wait the functional-gate controller and retain its actual exit code."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess


@dataclass(frozen=True, slots=True)
class Pin:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Launch:
    observed_utc: str
    pid: int
    launcher_pid: int
    command: list[str]
    source: Pin
    scope: str


@dataclass(frozen=True, slots=True)
class Exit:
    observed_utc: str
    owner_pid: int
    launcher_pid: int
    returncode: int
    wait_completed: bool


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    root = Path(__file__).parent
    base = root.parent
    source = root / 'gate_owner.py'
    raw = source.read_bytes()
    argv = [str(base / 'native-optimized-build01/venv/bin/python'), '-I', '-B', '-c',
            'import runpy,sys;r,h=sys.argv[1:3];sys.path[:0]=[r,h];sys.argv=[r+"/gate_owner.py"]+sys.argv[3:];runpy.run_path(sys.argv[0],run_name="__main__")',
            str(root), str(base / 'A5-native-matched-supervisor01'), '--plan', str(root / 'plan.json')]
    env = dict(os.environ)
    env['DYLD_LIBRARY_PATH'] = '/Users/alexy/.asdf/installs/python/3.12.6/lib'
    with (root / 'owner.log').open('xb') as log:
        child = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    launch = Launch(utc(), child.pid, os.getpid(), argv,
                    Pin(str(source), len(raw), hashlib.sha256(raw).hexdigest()),
                    'Full corrected functional gate, parent-owned wait and isolated VM shutdown')
    with (root / 'launch01.json').open('x') as stream:
        json.dump(asdict(launch), stream, indent=2)
    rc = child.wait()
    observed = Exit(utc(), child.pid, os.getpid(), rc, True)
    with (root / 'owner-exit01.json').open('x') as stream:
        json.dump(asdict(observed), stream, indent=2)
    print('controller returncode=' + str(rc), flush=True)
    raise SystemExit(rc if rc >= 0 else 128 - rc)


if __name__ == '__main__':
    main()
