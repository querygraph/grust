#!/usr/bin/env python3
"""Run tiny local diagnostic controls and retain every log and build identity."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--hyper-tracing', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parent
filters = {
    'handoff': 'info,h2::proto::connection=debug,h2::proto::streams=warn,hyper::proto::h2=debug',
    'control_frames': 'info,h2::proto::connection=debug,h2::proto::streams=warn,'
        'h2::frame::go_away=trace,h2::frame::reset=trace,h2::frame::ping=trace,'
        'h2::proto::ping_pong=trace,hyper::proto::h2=debug',
}
results = []
for label, log_filter in filters.items():
    for mode in ('keepalive', 'reset'):
        start = datetime.now(timezone.utc).isoformat()
        done = subprocess.run([str(args.binary), mode], env=dict(os.environ, RUST_LOG=log_filter),
                              text=True, capture_output=True, timeout=15)
        log = done.stdout + done.stderr
        log_file = root / f'{args.label}-{label}-{mode}.log'
        log_file.write_text(log)
        row = dict(filter_name=label, log_filter=log_filter, mode=mode, started_utc=start,
                   finished_utc=datetime.now(timezone.utc).isoformat(), returncode=done.returncode,
                   log_file=log_file.name, log_lines=len(log.splitlines()),
                   matching_outer_message='h2 protocol error: error reading a body from connection' in log,
                   goaway_logged='encoding GO_AWAY' in log, reset_logged='encoding RESET' in log,
                   hyper_timeout_log='hyper::proto::h2::server: keep-alive timed out' in log)
        results.append(row)
        print(json.dumps(row), flush=True)
evidence = dict(recorded_utc=datetime.now(timezone.utc).isoformat(),
                scope='Exact-version local in-memory proxy diagnostic controls, not Sail qualification',
                hyper_tracing_feature=args.hyper_tracing,
                binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                source_sha256=hashlib.sha256((root / 'src/main.rs').read_bytes()).hexdigest(),
                lock_sha256=hashlib.sha256((root / 'Cargo.lock').read_bytes()).hexdigest(), runs=results)
(root / f'{args.label}-results.json').write_text(json.dumps(evidence, indent=2) + '\n')
assert all(row['returncode'] == 0 and row['matching_outer_message'] for row in results)
