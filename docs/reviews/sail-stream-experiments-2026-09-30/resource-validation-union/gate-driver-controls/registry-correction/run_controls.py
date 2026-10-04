"""Offline parser controls; does not execute Cargo, a native binary, or SQL."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
SCRIPT = ROOT/'run_gate.py'
FAILED = ROOT/'candidate-gate/native-release.log'
spec = importlib.util.spec_from_file_location('union_gate', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
text = FAILED.read_text()
names = re.findall(r'\btest ([A-Za-z0-9_:]+) \.\.\.', text)
assert len(names) == len(set(names)) == 51
assert sum(name.startswith('argentea::') for name in names) == 45
anchored = re.findall(r'^test argentea::\S+ \.\.\. ok$', text, re.M)
assert len(anchored) == 42
interrupted = [line.split(' ... ', 1)[0] for line in text.splitlines()
               if line.startswith('test argentea::') and ' ... ARGENTEA_RECEIPT ' in line]
assert len(interrupted) == 3
# This is deliberately SYNTHETIC --list text, based on the observed test names.
# The retry gate must capture a real registry from its pinned release binary.
registry_text = '\n'.join(name+': test' for name in sorted(names))+'\n\n51 tests, 0 benchmarks\n'
(OUT/'synthetic-registry.txt').write_text(registry_text)
checks = []

def good(name, function):
    result = function()
    checks.append(dict(name=name, outcome='PASS'))
    return result


def bad(name, function):
    try:
        function()
    except RuntimeError as error:
        checks.append(dict(name=name, outcome='EXPECTED_REJECTION', error=str(error)))
    else:
        raise AssertionError('accepted '+name)

proof = good('synthetic_registry51_argentea45', lambda: module.native_registry(registry_text))
summary = good('real_interleaved_log_complete51', lambda: module.test_summaries(text, 51))
assert summary == [(51,0,0,0,0)]
rows = registry_text.splitlines()
bad('missing_registry_test', lambda: module.native_registry('\n'.join(rows[1:])))
duplicate = list(rows);duplicate[0] = duplicate[1]
bad('duplicate_registry_test', lambda: module.native_registry('\n'.join(duplicate)))
bad('argentea_identity_mismatch', lambda: module.native_registry(registry_text.replace('argentea::', 'unexpected::', 1)))
bad('footer_count_mismatch', lambda: module.native_registry(registry_text.replace('51 tests,', '50 tests,')))
bad('extra_registry_line', lambda: module.native_registry('unexpected log\n'+registry_text))
bad('benchmark_registry_mismatch', lambda: module.native_registry(registry_text.replace('0 benchmarks', '1 benchmarks')))
for column in ('failed','ignored','measured','filtered out'):
    bad('nonzero_'+column.replace(' ','_'), lambda c=column: module.test_summaries(text.replace('0 '+c+';', '1 '+c+';'),51))
bad('missing_summary', lambda: module.test_summaries(re.sub(r'^test result:.*$', '', text, flags=re.M),51))
bad('pass_count_mismatch', lambda: module.test_summaries(text.replace('51 passed;', '50 passed;'),51))
bad('duplicate_summary', lambda: module.test_summaries(text+text,51))
with tempfile.TemporaryDirectory(prefix='native-inventory-control-') as directory:
    binary = Path(directory)/'test-binary-standin'
    binary.write_bytes(b'not executable: hash binding control only')
    pin = dict(binary=str(binary), binary_sha256=module.sha(binary))
    good('binary_pin_matches', lambda: module.native_binary_guard(pin))
    binary.write_bytes(b'changed standin')
    bad('registry_binary_pin_mismatch', lambda: module.native_binary_guard(pin))
receipt = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), outcome='PASS_OFFLINE_PARSER_CONTROLS',
    driver_sha256=module.sha(SCRIPT), failed_log_sha256=module.sha(FAILED),
    prior_driver_sha256=module.sha(ROOT/'candidate-attempt01-driver.py'),
    scope='Real failed log proves51 successful unfiltered tests and45 distinct Argentea prefixes, but only42 anchored ok lines. Synthetic registry mutation controls do not replace the required real --list capture in the retry gate.',
    actual_failed_log=dict(unfiltered_summary=summary, unique_tests=len(set(names)), argentea_prefixes=45,
                          fragile_anchored_ok_lines=42, interrupted_prefixes=interrupted),
    checks=checks, synthetic_registry_sha256=module.sha(OUT/'synthetic-registry.txt'))
(OUT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(dict(outcome=receipt['outcome'],checks=len(checks),driver_sha256=receipt['driver_sha256'],receipt=str(OUT/'receipt.json')),indent=2))
