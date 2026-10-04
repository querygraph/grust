"""Package local immutable logging03 evidence; never delete, stage or read remotely."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import zlib
from rehydrate import archive_members, fingerprint

OUT = Path(__file__).resolve().parent
EXP = OUT.parent
RAW = EXP / 'logging03-compact'
SUPPORT = [
    'logging03-admission01.json', 'logging03-collection.json', 'logging03-compact.json',
    'logging03-host-closure.json', 'logging03-launch.json', 'logging03-preparation.json',
    'logging03-recovery01.json', 'logging03-recovery02.json', 'logging03-wrapper-exit.json',
    'closed-cell-audit/logging03-verification.json',
]
PATTERNS = {
    'private_key': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
    'aws_access_key': rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'github_token': rb'\b(?:gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b',
    'openai_style_token': rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}',
    'authorization': rb'(?i)authorization\s*[:=]\s*["\x27]?(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{16,}',
}


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('special input: ' + str(path))
        if path.is_file():
            result[str(path.relative_to(root))] = fingerprint(path)
    return result


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as reader, target.open('xb') as writer:
        shutil.copyfileobj(reader, writer, 1 << 20)
    if fingerprint(source) != fingerprint(target):
        raise ValueError('copy differs')


def main():
    receipt = {'started_utc': datetime.now(timezone.utc).isoformat(), 'outcome': 'PACKAGING_INCOMPLETE'}
    try:
        if any((OUT / x).exists() for x in ['manifest.json', 'diagnostics.tar.gz', 'metadata', 'support', 'packaging-receipt.json']):
            raise ValueError('package outputs already exist; do not retry into them')
        raw = inventory(RAW)
        receipt['original_tree'] = raw
        receipt['original_total_bytes'] = sum(pin['bytes'] for pin in raw.values())
        receipt['free_disk_before_bytes'] = shutil.disk_usage(OUT).free
        if receipt['free_disk_before_bytes'] < (2 << 30):
            raise ValueError('less than 2 GiB package disk admission')
        members = archive_members(RAW / 'diagnostics.tar')
        if set(members) != {'receipt.json', 'server.log', 'server-settings.json', 'memory-samples.jsonl'}:
            raise ValueError('unexpected diagnostic inventory')
        if any(raw['diagnostics/' + name] != pin for name, pin in members.items()):
            raise ValueError('archive differs from raw extracted collection')
        for name in raw:
            if name != 'diagnostics.tar' and not name.startswith('diagnostics/'):
                copy(RAW / name, OUT / 'metadata' / name)
        support = SUPPORT + [str(p.relative_to(EXP)) for p in sorted((EXP / 'logging03-closed-review').rglob('*')) if p.is_file()]
        source_support = {}
        for name in support:
            source = EXP / name
            if source.is_symlink() or not source.is_file():
                raise ValueError('support must be a regular file')
            source_support[name] = fingerprint(source)
            copy(source, OUT / 'support' / name)
        # Scan decoded text once per unique retained file, not the compressed representation.
        patterns = {name: re.compile(value) for name, value in PATTERNS.items()}
        hits = {}
        scans = []
        for path in [RAW / name for name in raw if name != 'diagnostics.tar'] + [EXP / name for name in support]:
            line_count = 0
            local_hits = {}
            with path.open('rb') as stream:
                for line in stream:
                    line_count += 1
                    line.decode('utf-8')
                    for name, pattern in patterns.items():
                        if pattern.search(line):
                            local_hits[name] = local_hits.get(name, 0) + 1
            scans.append({'path': str(path.relative_to(EXP)), 'lines': line_count})
            if local_hits:
                hits[str(path.relative_to(EXP))] = local_hits
        receipt['privacy'] = {'decoded_text_files': len(scans), 'scans': scans,
                              'credential_pattern_matches': hits, 'families': list(patterns),
                              'scope': 'Five explicit credential families over original UTF-8 text, including every archive member; no matching values emitted. Not exhaustive sensitive-information proof.'}
        if hits:
            raise ValueError('credential-pattern review required; no package sealed')
        with (RAW / 'diagnostics.tar').open('rb') as source, (OUT / 'diagnostics.tar.gz').open('xb') as target:
            with gzip.GzipFile(filename='', mode='wb', compresslevel=9, mtime=0, fileobj=target) as compressed:
                shutil.copyfileobj(source, compressed, 1 << 20)
        digest = hashlib.sha256()
        count = 0
        with gzip.open(OUT / 'diagnostics.tar.gz', 'rb') as decoded:
            for block in iter(lambda: decoded.read(1 << 20), b''):
                digest.update(block)
                count += len(block)
        if {'bytes': count, 'sha256': digest.hexdigest()} != raw['diagnostics.tar']:
            raise ValueError('gzip roundtrip differs')
        if inventory(RAW) != raw:
            raise ValueError('raw collection changed')
        if any(fingerprint(EXP / name) != pin for name, pin in source_support.items()):
            raise ValueError('support changed')
        packaged = {str(p.relative_to(OUT)): fingerprint(p) for directory in ['metadata', 'support'] for p in sorted((OUT / directory).rglob('*')) if p.is_file()}
        packaged['diagnostics.tar.gz'] = fingerprint(OUT / 'diagnostics.tar.gz')
        manifest = {'schema': 'logging03-lossless-package-v1', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
                    'raw_tree': raw, 'archive_members': members, 'support_sources': source_support,
                    'package_files': packaged, 'rehydration_helper': fingerprint(OUT / 'rehydrate.py'),
                    'gzip': {'mtime': 0, 'filename': '', 'compression_level': 9, 'zlib_runtime': zlib.ZLIB_RUNTIME_VERSION},
                    'scope': 'Exact raw bytes retained losslessly. No result Parquet payload or physical-value correctness claim.'}
        with (OUT / 'manifest.json').open('x') as stream:
            json.dump(manifest, stream, indent=2)
            stream.write('\n')
        receipt.update(outcome='LOSSLESS_PUBLICATION_PACKAGE_VERIFIED', manifest=fingerprint(OUT / 'manifest.json'),
                       gzip=packaged['diagnostics.tar.gz'], max_payload_file_bytes=max(p['bytes'] for p in packaged.values()),
                       gzip_decodes_to_exact_original=True, raw_inputs_unchanged=True,
                       packaging_helper=fingerprint(Path(__file__)), rehydration_helper=manifest['rehydration_helper'],
                       source_support=source_support, free_disk_after_bytes=shutil.disk_usage(OUT).free)
    except Exception as error:
        receipt.update(outcome='PACKAGING_FAILED', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        receipt['finished_utc'] = datetime.now(timezone.utc).isoformat()
        with (OUT / 'packaging-receipt.json').open('x') as stream:
            json.dump(receipt, stream, indent=2)
            stream.write('\n')
    print(receipt['outcome'], receipt['gzip'])


if __name__ == '__main__':
    main()
