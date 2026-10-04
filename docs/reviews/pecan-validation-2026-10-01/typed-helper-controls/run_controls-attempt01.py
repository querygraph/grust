"""Offline helper controls; no pytest suites, server, Spark query or build."""
from __future__ import annotations

import ast
from collections import Counter
import copy
from dataclasses import asdict
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
from typing import Any

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
GATE = runpy.run_path(str(ROOT/'run_typed_gate.py'))
BASE = GATE['BASE']
BASELINE = Path('/private/tmp/sail-pecan-typed-baseline')
BEFORE = BASE['source_identity'](BASELINE, GATE['BASELINE_HEAD'], GATE['BASELINE_TREE'], 'exact')
OLD_PINS = {p.name: BASE['sha'](p) for p in (ROOT/'run_gate.py', ROOT/'action_probe.py')}
START = BASE['utc']()
RESULTS: list[dict[str, Any]] = []
ENV = BASE['client_environment'](BASELINE/'examples/extensions/benchmarks', BASELINE)
ENV['PYTHONPATH'] = os.pathsep.join(map(str, [BASELINE/'examples/extensions/graph-algorithms/src',
    BASELINE/'examples/extensions/nutmeg/python', GATE['TOOLS'], BASE['CLIENT']]))
ENV['PYTEST_ADDOPTS'] = ''


def command(label: str, argv: list[str]) -> None:
    with (OUT/(label+'.log')).open('x') as stream:
        result = subprocess.run(argv, env=ENV, cwd=BASELINE, stdout=stream, stderr=subprocess.STDOUT, timeout=60)
    assert result.returncode == 0, label
    RESULTS.append(dict(case=label, outcome='PASS', command=argv))


for path in (ROOT/'run_typed_gate.py', ROOT/'typed_action_probe.py'):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.returns is not None, (path, node.name)
            args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            args += [arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None]
            assert all(arg.arg in ('self', 'cls') or arg.annotation is not None for arg in args)
            assert not any(isinstance(child, (ast.Import, ast.ImportFrom)) for child in ast.walk(node))
RESULTS.append(dict(case='helpers-parsed-typed-and-module-imports', outcome='PASS'))
command('tool-origins', [str(BASE['PYTHON']), '-B', str(ROOT/'run_typed_gate.py'), '--module-origin-probe', str(BASELINE)])
command('gate-cli', [str(BASE['PYTHON']), '-B', str(ROOT/'run_typed_gate.py'), '--help'])
command('probe-cli', [str(BASE['PYTHON']), '-B', str(ROOT/'typed_action_probe.py'), '--help'])
# Import the pure comparison/protocol helpers in the same pinned environment.
command('action-protocol', [str(BASE['PYTHON']), '-B', str(OUT/'protocol_control.py')])
assert OLD_PINS == {p.name: BASE['sha'](p) for p in (ROOT/'run_gate.py', ROOT/'action_probe.py')}
assert BEFORE == BASE['source_identity'](BASELINE, GATE['BASELINE_HEAD'], GATE['BASELINE_TREE'], 'exact')
BASE['save'](OUT/'receipt.json', dict(outcome='PASS_OFFLINE_TYPED_HELPER_CONTROLS', started_utc=START,
    finished_utc=BASE['utc'](), results=RESULTS, historical_helpers_unchanged=True, baseline_source_unchanged=True,
    old_helper_hashes=OLD_PINS, helper_hashes={p.name:BASE['sha'](p) for p in (ROOT/'run_typed_gate.py', ROOT/'typed_action_probe.py')},
    files_sha256={p.name: BASE['sha'](p) for p in OUT.iterdir() if p.is_file()},
    scope='Only synthetic protocol/CLI/tool-import/AST controls; no package tests, SQL, server or builds.')))
print('PASS_OFFLINE_TYPED_HELPER_CONTROLS')
