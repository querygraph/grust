#!/usr/bin/env python3
"""Run an owned ArcadeDB diagnostic with retained client/server runtime evidence.

Creates the benchmark database on an explicitly selected disposable server and
never clears one. A failed cell stops that server. This runner does not issue
publication receipts. ArcadeDB is driven over its HTTP API only.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

# The pinned server: tag plus the platform image digests its multi-platform
# index names. ArcadeDB 26.10.2 (Temurin 25; has #9680 and #9953).
# Anything else runs only with --diagnostic-server-image, marked unpinned.
SERVER_IMAGE_TAG = 'arcadedata/arcadedb:26.10.2'
SERVER_IMAGE_DIGESTS = {
    'aarch64': 'sha256:a8d755d0ef09efdaf769765833f15e4ecd15f19bae56f5f94d019bb666e9cbc2',
    'x86_64': 'sha256:51303393dab3597317cbe6f364a409a4f81a87ab912e8627e3b8cfd7fbb2c3ac',
}
SERVER_IMAGES = {f'{SERVER_IMAGE_TAG}@{digest}' for digest in SERVER_IMAGE_DIGESTS.values()}
MEMORY = 6 * 1024**3
NANO_CPUS = 8_000_000_000
NETWORK = 'grust-lsqb-arcadedb-qualification'
# The server must bound its own work by the same 60-second deadline the
# coordinator applies, and accept the single streamed import request.
REQUIRED_JAVA_OPTS = ('-Darcadedb.command.timeout=60000',)
BODY_LIMIT = re.compile(r'-Darcadedb\.server\.httpBodyContentMaxSize=(-1|[0-9]+)')
MIN_BODY_LIMIT = 2 * 1024**3


def require_host_preflight(output):
    """Fail before client creation; retain the screen even on contention."""
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name('host_preflight.py')),
         '--output', str(output / 'host-preflight.json')], check=False, timeout=45)
    if result.returncode != 0:
        raise ValueError('host CPU preflight failed; no benchmark client created')


def validate_network(server, network):
    if network.get('Name') != NETWORK or network.get('Internal') is not True:
        raise ValueError('ArcadeDB qualification network must be internal')
    attached = server['NetworkSettings']['Networks']
    if set(attached) != {NETWORK} or server['HostConfig']['NetworkMode'] != NETWORK:
        raise ValueError('server must be attached only to the qualification network')
    if attached[NETWORK].get('NetworkID') != network.get('Id'):
        raise ValueError('server network identity differs')


def validate_server_options(env):
    """Check the required server settings without exporting any environment."""
    options = next((item.split('=', 1)[1] for item in env if item.startswith('JAVA_OPTS=')), '')
    tokens = options.split()
    if any(required not in tokens for required in REQUIRED_JAVA_OPTS):
        raise ValueError('server must run with -Darcadedb.command.timeout=60000')
    limits = [BODY_LIMIT.fullmatch(token) for token in tokens]
    limits = [int(match.group(1)) for match in limits if match]
    if len(limits) != 1 or 0 <= limits[0] < MIN_BODY_LIMIT:
        raise ValueError('server must accept a streamed import of at least 2 GiB '
                         '(-Darcadedb.server.httpBodyContentMaxSize)')
    if not any(token.startswith('-Darcadedb.server.rootPassword=') for token in tokens):
        raise ValueError('server must set a disposable root password')


def inspect(target, image=False):
    command = ['docker', 'image', 'inspect'] if image else ['docker', 'inspect']
    return json.loads(subprocess.check_output([*command, target], timeout=20))[0]


def snapshot(raw):
    """Allowlist runtime metadata; never export arbitrary environment variables."""
    host = raw['HostConfig']
    return dict(container_id=raw['Id'], image_id=raw['Image'], name=raw['Name'],
                state={key: raw['State'].get(key) for key in
                       ('Status', 'Running', 'OOMKilled', 'ExitCode', 'StartedAt', 'FinishedAt')},
                resources={key: host.get(key) for key in
                           ('Memory', 'MemorySwap', 'NanoCpus', 'CpusetCpus', 'ReadonlyRootfs', 'NetworkMode')},
                labels=raw['Config'].get('Labels', {}))


def stop_owned(client_id, server_id):
    """Always attempt remote shutdown, even if stopping the client fails."""
    try:
        subprocess.run(['docker', 'stop', client_id], check=True, timeout=30)
    finally:
        subprocess.run(['docker', 'stop', server_id], check=True, timeout=60)


def wait_ready(server_id, timeout=120):
    """Probe the HTTP readiness endpoint before measurement; a running container is not a ready DB.

    Retain only probe status, never unfiltered command output. Each attempt is
    bounded and emits progress.
    """
    started = time.monotonic()
    attempts = 0
    while True:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise RuntimeError('ArcadeDB readiness deadline exceeded before benchmark start')
        attempts += 1
        try:
            result = subprocess.run(
                ['docker', 'exec', server_id, 'wget', '-q', '-S', '-O', '/dev/null',
                 'http://127.0.0.1:2480/api/v1/ready'], capture_output=True, text=True,
                timeout=min(10, remaining), check=False)
            ready = result.returncode == 0 and re.search(r'HTTP/1\.1 20[04]', result.stderr) is not None
        except subprocess.TimeoutExpired:
            ready = False
        record = dict(event='arcadedb-readiness', attempt=attempts, ready=ready,
                      elapsed_ms=round((time.monotonic() - started) * 1000))
        print(json.dumps(record), flush=True)
        if ready:
            return record
        remaining = timeout - (time.monotonic() - started)
        if remaining > 0:
            time.sleep(min(2, remaining))


def start_recorded(client_id, output):
    """Capture exit metadata before the watchdog removes its owned container."""
    if not re.fullmatch(r'[0-9a-f]{64}', client_id):
        raise ValueError('invalid client identity')
    status = subprocess.run(['docker', 'start', '--attach', client_id]).returncode
    with (Path(output) / 'client-after.json').open('x') as stream:
        json.dump(snapshot(inspect(client_id)), stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scale', choices=('example', '0.1', '0.3'), default='example')
    parser.add_argument('--mode', choices=('qualify', 'deadline-probe', 'recovery-probe'), default='qualify')
    parser.add_argument('--warmups', type=int)
    parser.add_argument('--runs', type=int)
    parser.add_argument('--diagnostic-server-image', action='store_true',
                        help='accept an unpinned server image; the run is marked and cannot be bundled')
    args = parser.parse_args()
    sampled = args.warmups is not None or args.runs is not None
    if sampled and (args.mode != 'qualify' or args.warmups is None or args.runs is None or
                    not 0 <= args.warmups <= 5 or not 1 <= args.runs <= 10):
        parser.error('sampling requires qualify mode, --warmups 0..5 and --runs 1..10 together')
    if not re.fullmatch(r'grust-lsqb-arcadedb-[a-zA-Z0-9-]+', args.server):
        parser.error('server must be an explicitly owned grust-lsqb-arcadedb-* container')
    if not re.fullmatch(r'[0-9a-f]{40}', args.source_revision):
        parser.error('source revision must be a full commit SHA')
    if 'ARCADEDB_PASSWORD' not in os.environ:
        parser.error('ARCADEDB_PASSWORD must hold the disposable server root password')
    server, image = inspect(args.server), inspect(args.image, image=True)
    if not server['State']['Running'] or server['State']['OOMKilled']:
        parser.error('server is not healthy/running')
    if server['Config']['Image'] not in SERVER_IMAGES and not args.diagnostic_server_image:
        parser.error('server must be the pinned release image (or pass --diagnostic-server-image)')
    try:
        validate_server_options(server['Config']['Env'])
    except ValueError as error:
        parser.error(str(error))
    host = server['HostConfig']
    if host['PortBindings'] or host['Memory'] != MEMORY or host['MemorySwap'] != MEMORY or host['NanoCpus'] != NANO_CPUS:
        parser.error('server must have no host ports and 8 CPU / 6 GiB without swap')
    labels = image['Config'].get('Labels', {})
    if labels.get('org.opencontainers.image.revision') != args.source_revision or labels.get('io.adversarial.grust.benchmark-feature') != 'arcadedb-native':
        parser.error('client image source/feature labels differ')
    network_record = json.loads(subprocess.check_output(
        ['docker', 'network', 'inspect', NETWORK], timeout=20))[0]
    try:
        validate_network(server, network_record)
    except ValueError as error:
        parser.error(str(error))
    address = server['NetworkSettings']['Networks'].get(NETWORK, {}).get('IPAddress')
    if not address:
        parser.error('server must be on the private qualification network')
    root = Path(__file__).resolve().parent
    datasets = root / ('upstream/lsqb/data' if args.scale == 'example' else 'data')
    output = args.output.resolve()
    output.mkdir(exist_ok=False)

    def save(name, value):
        with (output / name).open('x') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())

    if args.mode == 'qualify':
        require_host_preflight(output)

    project = f'grust-lsqb-native-{os.getpid()}'
    container = project + '-arcadedb-cell'
    # The probes use their own database so they never touch the benchmark one.
    database = 'lsqb' if args.mode == 'qualify' else 'grust_probe'
    # --env NAME passes the value from this process without recording it.
    command = ['docker', 'create', '--name', container, '--init',
               '--label', f'com.docker.compose.project={project}', '--label', 'com.docker.compose.service=benchmark',
               '--network', NETWORK, '--cpus', '8', '--memory', '6g', '--memory-swap', '6g',
               '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=1g', '--user', f'{os.getuid()}:{os.getgid()}',
               '--mount', f'type=bind,src={output},dst=/out',
               '--mount', f'type=bind,src={datasets},dst=/datasets,readonly',
               '--env', f'ARCADEDB_URL=http://{address}:2480', '--env', 'ARCADEDB_USER=root',
               '--env', 'ARCADEDB_PASSWORD', '--env', f'ARCADEDB_DATABASE={database}',
               '--env', 'ARCADEDB_BENCHMARK_DISPOSABLE=1',
               '--entrypoint', '/usr/local/bin/grust-lsqb-arcadedb', image['Id'], args.mode]
    if args.mode == 'qualify':
        command += ['/opt/lsqb-mounted', '/opt/grust-attacks', args.scale, '/out/result']
        if sampled:
            command += [str(args.warmups), str(args.runs)]
    save('invocation.json', dict(diagnostic_only=True, command=command, source_revision=args.source_revision,
                                 client_image_id=image['Id'], client_labels=labels, server_image=server['Config']['Image'],
                                 server_image_pinned=server['Config']['Image'] in SERVER_IMAGES))
    save('server-before.json', snapshot(server))
    save('network-before.json', {key: network_record[key] for key in ('Name', 'Id', 'Internal')})
    # No client exists yet and no dataset has been touched. A startup failure
    # therefore cannot be mistaken for a query failure or a measured sample.
    try:
        wait_ready(server['Id'])
    except Exception:
        subprocess.run(['docker', 'stop', server['Id']], check=True, timeout=60)
        raise
    client_id = subprocess.check_output(command, text=True, timeout=30).strip()
    if not re.fullmatch(r'[0-9a-f]{64}', client_id):
        raise RuntimeError('invalid created client identity')
    save('client-before.json', snapshot(inspect(client_id)))
    # Import allowance plus all per-sample READY/query/reap/recovery bounds.
    # This is an emergency ceiling, not an estimate of expected wall time.
    timeout = (600000 + 22 * (args.warmups + args.runs) * 110250) if sampled else (
        600000 if args.scale == 'example' else 3100000)
    status = 125
    try:
        with (output / 'watchdog.json').open('xb', buffering=0) as watchdog, (output / 'cell.log').open('xb', buffering=0) as log:
            supervised = [sys.executable, str(root / 'cell-watchdog.py'), '--timeout-ms', str(timeout),
                          '--heartbeat-ms', '30000', '--container', container, '--project', project,
                          '--service', 'benchmark', '--record-fd', str(watchdog.fileno()),
                          '--', sys.executable, str(Path(__file__).resolve()),
                          '_start-recorded', client_id, str(output)]
            process = subprocess.Popen(supervised, pass_fds=(watchdog.fileno(),), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            for line in process.stdout:
                log.write(line)
                os.fsync(log.fileno())
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
            status = process.wait()
    finally:
        # The child wrapper captures a normal exit before watchdog cleanup.
        # Missing evidence after an outer timeout is never forged into a snapshot.
        try:
            client_after = json.loads((output / 'client-after.json').read_text())
        except Exception:
            try:
                stop_owned(client_id, server['Id'])
            finally:
                save('client-after.json', dict(container_id=client_id,
                                               capture_error='container inspection unavailable'))
                save('server-after.json', snapshot(inspect(server['Id'])))
            raise
        state = client_after['state']
        if status == 0 and (state['Running'] or state['OOMKilled'] or state['ExitCode'] != 0):
            status = 125
        if status:
            subprocess.run(['docker', 'stop', server['Id']], check=True, timeout=60)
        save('server-after.json', snapshot(inspect(server['Id'])))
    print(json.dumps(dict(event='native-cell-finished', exit=status, output=str(output))), flush=True)
    return status


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '_start-recorded':
        raise SystemExit(start_recorded(sys.argv[2], sys.argv[3]))
    raise SystemExit(main())
