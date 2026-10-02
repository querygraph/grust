"""Own one full Linux functional gate and gracefully stop its separate VM."""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
import traceback
import uuid
from pathlib import Path
from types import FrameType
from typing import Literal

import native_io as io
from native_models import Pin, Record
from pydantic import Field

BASE = Path('/Volumes/Apo/graph-tests/results/sem-review-20261001')


class Plan(Record):
    observed_utc: str
    repository: Literal['querygraph/grust']
    source_commit: Literal['d2668ec7c7dbd7dd728e3976bcfaba3ae51d14ad']
    source_tree: Literal['2674baf6d93109d5b6d1bf49a77a35b4bc7f115a']
    release_tag: Literal['v0.24.0']
    release_source: str
    superseded_requested_commit: str
    gate_dir: Path
    result_dir: Path
    profile: Literal['grust-linux-f1-024']
    socket: Literal['unix:///Users/alexy/.colima/grust-linux-f1-024/docker.sock']
    vm_cpus: Literal[8]
    vm_memory_gib: Literal[40]
    container_cpus: Literal[8]
    container_memory: Literal['32g']
    build_jobs: Literal[2]
    rust_version: Literal['1.99.0']
    production_default_config: Pin
    selected_docker_context: str
    minimum_free_host_bytes: int
    scope: str


class Step(Record):
    name: str
    argv: list[str]
    log: Path
    started_utc: str
    pid: int
    returncode: int | None = None
    closed_utc: str | None = None


class Receipt(Record):
    observed_utc: str
    started_utc: str
    owner_pid: int
    plan: Pin
    source: Pin
    image_recipe: Pin
    outcome: Literal['running', 'passed_full_linux_functional_gate', 'failed'] = 'running'
    active_step: str | None = None
    steps: list[Step] = Field(default_factory=list)
    free_host_bytes: int = 0
    base_image_digest: str | None = None
    image_id: str | None = None
    event_watcher_returncode: int | None = None
    container_inspections: list[Pin] = Field(default_factory=list)
    exact_verdict: str | None = None
    unchanged_detached_sources: bool = False
    owned_profile_stopped: bool = False
    production_config_and_context_preserved: bool = False
    shared_locks_released: bool = False
    errors: list[str] = Field(default_factory=list)
    scope: str = 'Full unmodified functional gate, not a VM benchmark or crate publication.'


def pin(path: Path) -> Pin:
    return Pin(path=path, **io.identity(path).model_dump())


def environment(docker: bool = True) -> dict[str, str]:
    result = dict(os.environ)
    for name in ('DOCKER_CONTEXT', 'DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH',
                 'COLIMA_PROFILE', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'RUSTUP_TOOLCHAIN'):
        result.pop(name, None)
    if docker:
        result['DOCKER_HOST'] = 'unix:///Users/alexy/.colima/grust-linux-f1-024/docker.sock'
    return result


def production(plan: Plan) -> None:
    io.verify(plan.production_default_config)
    selected = json.loads(Path('/Users/alexy/.docker/config.json').read_text()).get('currentContext', 'default')
    io.require(selected == plan.selected_docker_context, 'production Docker context changed')


def source(path: Path, plan: Plan) -> None:
    for args, expected in ((['rev-parse', 'HEAD'], plan.source_commit),
                           (['rev-parse', 'HEAD^{tree}'], plan.source_tree),
                           (['status', '--porcelain'], '')):
        actual = io.command(['git', '-C', str(path), *args]).strip()
        io.require(actual == expected, 'gate source HEAD/tree/clean state differs')
    branch = subprocess.run(['git', '-C', str(path), 'symbolic-ref', '-q', 'HEAD'],
                            capture_output=True, timeout=30, check=False)
    io.require(branch.returncode == 1, 'gate checkout must be detached')


def interrupted(signum: int, _frame: FrameType | None) -> None:
    raise InterruptedError(f'gate interrupted by signal {signum}')


class Owner:
    def __init__(self, plan: Plan, receipt: Receipt) -> None:
        self.plan = plan
        self.receipt = receipt
        self.path = plan.result_dir / 'receipt.json'
        self.child: subprocess.Popen[bytes] | None = None
        self.events: subprocess.Popen[bytes] | None = None
        self.seen: set[str] = set()

    def save(self) -> None:
        self.receipt.observed_utc = io.utc()
        self.receipt.free_host_bytes = os.statvfs(self.plan.gate_dir).f_bavail * os.statvfs(self.plan.gate_dir).f_frsize
        io.write(self.path, self.receipt)

    def capture_container(self) -> None:
        image = self.receipt.image_id
        if image is None:
            return
        ids = io.command(['docker', 'ps', '-q', '--filter', 'ancestor=' + image], env=environment()).split()
        for cid in ids:
            if cid in self.seen:
                continue
            raw = io.command(['docker', 'inspect', cid], env=environment())
            value = json.loads(raw)[0]
            host = value['HostConfig']
            io.require(value['Config']['Image'] == image and host['Memory'] == 32 * 2**30
                       and host['MemorySwap'] == 32 * 2**30 and host['NanoCpus'] == 8 * 10**9,
                       'actual gate container resource/image settings differ')
            p = self.plan.result_dir / ('container-' + cid + '.json')
            with p.open('x') as stream:
                stream.write(raw)
            self.receipt.container_inspections.append(pin(p))
            self.seen.add(cid)
            self.save()

    def execute(self, name: str, argv: list[str], seconds: int, *, docker: bool = True,
                extra: dict[str, str] | None = None, watch: bool = False) -> Path:
        path = self.plan.result_dir / (f'{len(self.receipt.steps)+1:02d}-' + name + '.log')
        env = environment(docker)
        if extra:
            env.update(extra)
        with path.open('xb') as output:
            self.child = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT,
                                          env=env, start_new_session=True, stdin=subprocess.DEVNULL)
            step = Step(name=name, argv=argv, log=path, started_utc=io.utc(), pid=self.child.pid)
            self.receipt.steps.append(step)
            self.receipt.active_step = name
            self.save()
            print(name + ' started ' + str(step.pid), flush=True)
            started = time.monotonic()
            updated = started
            try:
                while self.child.poll() is None:
                    io.require(time.monotonic()-started < seconds, name + ' deadline exceeded')
                    if watch:
                        self.capture_container()
                        stat = os.statvfs(self.plan.gate_dir)
                        io.require(stat.f_bavail * stat.f_frsize >= self.plan.minimum_free_host_bytes,
                                   'host free disk fell below reserved64GiB')
                    if time.monotonic()-updated >= 30:
                        self.save()
                        updated = time.monotonic()
                    time.sleep(2)
            except BaseException:
                io.close_group(self.child.pid)
                self.child.wait(timeout=10)
                step.returncode = self.child.returncode
                step.closed_utc = io.utc()
                self.save()
                raise
            step.returncode = self.child.wait(timeout=10)
            step.closed_utc = io.utc()
            self.child = None
            self.save()
            print(name + ' returncode=' + str(step.returncode), flush=True)
            io.require(step.returncode == 0, name + ' failed rc=' + str(step.returncode))
        return path

    def event_start(self) -> None:
        path = self.plan.result_dir / 'docker-events.jsonl'
        with path.open('xb') as stream:
            self.events = subprocess.Popen(['docker', 'events', '--format', '{{json .}}'],
                                          env=environment(), stdout=stream, stderr=subprocess.STDOUT,
                                          start_new_session=True, stdin=subprocess.DEVNULL)
        io.write(self.plan.result_dir / 'event-launch.json',
                 {'pid': self.events.pid, 'observed_utc': io.utc(), 'scope': 'owned isolated Docker daemon events'})

    def cleanup(self, attempted: bool) -> None:
        if self.events is not None:
            if self.events.poll() is None:
                self.events.terminate()
            self.receipt.event_watcher_returncode = self.events.wait(timeout=10)
        if not attempted:
            return
        try:
            ids = io.command(['docker', 'ps', '-q'], env=environment()).split()
        except Exception:  # noqa: BLE001 - a failed startup may have no Docker daemon
            io.require(self.receipt.outcome == 'failed', 'runtime unavailable after positive gate')
            ids = []
        if ids:
            io.require(self.receipt.outcome == 'failed', 'containers remain after positive gate exit')
            image = self.receipt.image_id
            owned = io.command(['docker', 'ps', '-q', '--filter', 'ancestor=' + image],
                               env=environment()).split() if image else []
            io.require(set(ids) == set(owned), 'unknown container on owned profile; refuse stopping it')
            io.command(['docker', 'stop', '--time', '15', *owned], env=environment(), seconds=90)
        self.execute('stop-owned-profile', ['colima', 'stop', '--profile', self.plan.profile], 300, docker=False)
        raw = io.command(['colima', 'list', '--json'], env=environment(False))
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        io.require(any(r['name'] == self.plan.profile and r['status'] == 'Stopped' for r in rows),
                   'owned VM is not observed stopped')
        self.receipt.owned_profile_stopped = True
        production(self.plan)
        self.receipt.production_config_and_context_preserved = True


def run(configuration: Path) -> int:
    plan = Plan.model_validate_json(configuration.read_bytes())
    io.require(plan.result_dir == configuration.parent and Path(__file__).parent == plan.result_dir,
               'owner/result configuration root differs')
    io.require(plan.gate_dir == Path('/Users/alexy/gates-linux-f1-024-run02')
               and not plan.gate_dir.is_symlink(), 'fresh explicit HOME gate namespace required')
    profile_rows = [json.loads(line) for line in io.command(['colima', 'list', '--json'], env=environment(False)).splitlines() if line.strip()]
    io.require(any(row['name'] == plan.profile and row['status'] == 'Stopped' and row['cpus'] == 8 and row['memory'] == 40 * 2**30 for row in profile_rows), 'owned profile must be stopped with its established settings')
    production(plan)
    source(plan.gate_dir / 'driver', plan)
    now = io.utc()
    receipt = Receipt(observed_utc=now, started_utc=now, owner_pid=os.getpid(),
                      plan=pin(configuration), source=pin(Path(__file__)), image_recipe=pin(plan.result_dir / 'image/Dockerfile'))
    owner = Owner(plan, receipt)
    locks = (BASE / 'gate.lock', BASE / 'serial-queue.lock')
    identity = io.Owner(pid=os.getpid(), config_sha256=receipt.plan.sha256, token=uuid.uuid4().hex)
    io.acquire(locks, identity)
    attempted = False
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        owner.save()
        io.require(receipt.free_host_bytes >= plan.minimum_free_host_bytes, 'insufficient host free disk')
        attempted = True
        owner.execute('start-owned-profile', ['colima', 'start', '--profile', plan.profile, '--activate=false',
            '--template=false', '--ssh-config=false', '--runtime', 'docker', '--arch', 'x86_64',
            '--vm-type', 'vz', '--mount-type', 'virtiofs', '--cpus', '8', '--memory', '40',
            '--disk', '60', '--root-disk', '20', '--mount', str(plan.gate_dir) + ':w'], 600, docker=False)
        production(plan)
        io.require(not io.command(['docker', 'ps', '-q'], env=environment()).strip(), 'fresh runtime is not empty')
        owner.execute('pull-rust-trixie', ['docker', 'pull', '--platform', 'linux/amd64', 'rust:1-trixie'], 1200)
        raw = io.command(['docker', 'image', 'inspect', 'rust:1-trixie'], env=environment())
        (plan.result_dir / 'base-image.json').write_text(raw)
        base = json.loads(raw)[0]
        io.require(base['Architecture'] == 'amd64' and base['Os'] == 'linux' and bool(base['RepoDigests']),
                   'selected base platform/digest unavailable')
        receipt.base_image_digest = base['RepoDigests'][0]
        owner.execute('build-package-image', ['docker', 'build', '--platform', 'linux/amd64',
            '--build-arg', 'RUST_BASE=' + str(receipt.base_image_digest),
            '--iidfile', str(plan.result_dir / 'image-id.txt'), '-t', 'grust-linux-f1-024:run01',
            str(plan.result_dir / 'image')], 1800)
        image = (plan.result_dir / 'image-id.txt').read_text().strip()
        io.require(bool(re.fullmatch(r'sha256:[0-9a-f]{64}', image)), 'immutable image ID missing')
        receipt.image_id = image
        raw = io.command(['docker', 'image', 'inspect', image], env=environment())
        (plan.result_dir / 'package-image.json').write_text(raw)
        built = json.loads(raw)[0]
        io.require(built['Architecture'] == 'amd64' and 'CARGO_BUILD_JOBS=2' in built['Config']['Env'],
                   'actual package platform/jobs differ')
        info = io.command(['docker', 'info', '--format',
            '{"architecture":"{{.Architecture}}","cpus":{{.NCPU}},"memory_bytes":{{.MemTotal}},"server_version":"{{.ServerVersion}}"}'], env=environment())
        (plan.result_dir / 'guest-docker-info.json').write_text(info)
        guest = json.loads(info)
        io.require(guest['architecture'] == 'x86_64' and guest['cpus'] == 8
                   and guest['memory_bytes'] >= 34 * 2**30, 'actual guest architecture/resources differ')
        owner.execute('verify-toolchain', ['docker', 'run', '--rm', image, 'bash', '-c',
            'set -e; test -r /usr/include/google/protobuf/empty.proto; protoc -I/usr/include --descriptor_set_out=/tmp/protobuf-headers.pb /usr/include/google/protobuf/empty.proto; test "$(rustc --version | cut -d" " -f2)" = 1.99.0; test "$CARGO_BUILD_JOBS" = 2; uname -sm; rustc -vV; cargo -V; cargo clippy -V; rustfmt -V; protoc --version'], 120)
        owner.event_start()
        script = plan.gate_dir / 'driver/scripts/gate-linux-container.sh'
        log = owner.execute('full-linux-gate', ['bash', str(script), plan.source_commit], 14400,
            extra={'GATE_DIR': str(plan.gate_dir), 'GATE_IMAGE': image, 'GATE_CPUS': '8', 'GATE_MEM': '32g'}, watch=True)
        expected = r'^ci-local: PASSED every gate at ' + plan.source_commit[:7] + r' on Linux x86_64 in [0-9]+s$'
        verdicts = [line for line in log.read_text().splitlines() if re.fullmatch(expected, line)]
        io.require(len(verdicts) == 1 and bool(receipt.container_inspections), 'exact clean full Linux verdict/resources missing')
        receipt.exact_verdict = verdicts[0]
        source(plan.gate_dir / 'driver', plan)
        source(plan.gate_dir / plan.source_commit, plan)
        receipt.unchanged_detached_sources = True
        receipt.outcome = 'passed_full_linux_functional_gate'
    except BaseException as error:  # noqa: BLE001 - retain failed steps and interrupts
        receipt.outcome = 'failed'
        receipt.errors.append(f'{type(error).__name__}: {error}')
        (plan.result_dir / 'failure-traceback.txt').write_text(traceback.format_exc())
    finally:
        try:
            owner.cleanup(attempted)
        except BaseException as error:  # noqa: BLE001 - retain failed steps and interrupts
            receipt.outcome = 'failed'
            receipt.errors.append(f'cleanup {type(error).__name__}: {error}')
        try:
            io.release(locks, identity)
            receipt.shared_locks_released = True
        except BaseException as error:  # noqa: BLE001 - retain failed steps and interrupts
            receipt.outcome = 'failed'
            receipt.errors.append(f'lock release {type(error).__name__}: {error}')
        io.verify(receipt.source)
        io.verify(receipt.plan)
        io.verify(receipt.image_recipe)
        receipt.active_step = None
        owner.save()
    print(receipt.outcome + ' ' + str(owner.path), flush=True)
    return 0 if receipt.outcome == 'passed_full_linux_functional_gate' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    raise SystemExit(run(parser.parse_args().plan))
