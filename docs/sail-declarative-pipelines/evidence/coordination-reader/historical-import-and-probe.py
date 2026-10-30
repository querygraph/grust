from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import tempfile

root = Path('/Users/alexy/src/grust-sdp')
parent = '632b602d143e974280312c37e369a165800ef8c8'
offered = '2103fb56c0b8f0b88c807c697e4726682c60a976'
paths = ('scripts/sdp-coordination-append.py', 'scripts/sdp-coordination-append-tests.py',
         'docs/sail-declarative-pipelines/CODEX-FABLE-COORDINATION.md')
def source(commit: str, path: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(root), 'show', commit + ':' + path])
for path in paths:
    assert (root / path).read_bytes() == source(parent, path), path
probe = Path('/tmp/sail-sdp-protocol-reader-control')
probe.mkdir()
module_path = probe / 'offered-helper.py'
module_path.write_bytes(source(offered, paths[0]))
spec = importlib.util.spec_from_file_location('offered_sdp_helper', module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='sdp-reader-control-') as directory:
    log = Path(directory) / 'log.md'
    first = module.append_message(log, 'Codex', 'first')
    second = module.append_message(log, 'Fable', '  body\r\nsecond line\r\n')
    result, boundary = module.read_since(log, first)
    assert boundary == second
    normalized = result.endswith('  body\nsecond line\n') and not result.endswith('  body\r\nsecond line\r\n')
    timestamp = list(module.ENTRY_HEADER.finditer(log.read_text()))[0]['timestamp']
    alias = 'legacy:' + timestamp
    try:
        module.read_since(log, alias)
    except ValueError as error:
        rejected = str(error)
    else:
        raise AssertionError('expected offered reader to reject accepted append alias')
    assert normalized
    # The offered append contract accepts that same alias.
    module.append_message(log, 'Codex', 'alias is accepted by append', reply_to=(alias,))
    receipt = {
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'offered_commit': offered, 'helper_sha256': hashlib.sha256(module_path.read_bytes()).hexdigest(),
        'scope': 'Direct temporary-log probes against exact offered Git helper bytes; not a full branch gate',
        'crlf_body_was_normalized': normalized,
        'read_boundary': boundary,
        'legacy_alias_accepted_by_append': True,
        'reader_alias_error': rejected,
    }
(probe / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
for path in paths:
    (root / path).write_bytes(source(offered, path))
print('Observed both offered-reader gaps; imported exact three-file offer for correction')
