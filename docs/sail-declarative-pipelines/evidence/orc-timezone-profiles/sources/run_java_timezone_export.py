"""Repeatable offline profile generation; no JVM is required by profile consumers."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import verify_java_timezone_profiles

ARTIFACTS = [
    'java-timezone-profiles.json', 'java-timezone-profile-verification.json',
    'java-timezone-resolver-oracle.json', 'java-timezone-profile-provenance.json',
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--java-home', required=True, type=Path)
    parser.add_argument('--classpath', required=True)
    parser.add_argument('--format-locale', required=True)
    parser.add_argument('--oldmapping', required=True, choices=['true', 'false'])
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repeat', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).with_name('ExportJavaTimezoneProfiles.java')
    verify_source = Path(__file__).with_name('verify_java_timezone_profiles.py')
    command = [
        str(args.java_home/'bin/java'), '-Xmx256m',
        '-Dsun.timezone.ids.oldmapping='+args.oldmapping,
        '--add-opens', 'java.base/java.util=ALL-UNNAMED',
        '--add-opens', 'java.base/sun.util.calendar=ALL-UNNAMED',
        '--class-path', args.classpath, str(source),
    ]

    def generate(directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(command+[str(directory), args.format_locale, args.oldmapping], capture_output=True, text=True)
        (directory/'export.stdout').write_text(result.stdout)
        (directory/'export.stderr').write_text(result.stderr)
        print(result.stdout, end='')
        if result.returncode:
            print(result.stderr)
            raise SystemExit(result.returncode)

    generate(args.output)
    repeat = args.output/'repeat'
    if args.repeat:
        generate(repeat)
        for name in ARTIFACTS:
            assert (args.output/name).read_bytes() == (repeat/name).read_bytes(), name+' is nondeterministic'
    verify_java_timezone_profiles.verify(args.output)
    manifest = {
        'settings': {'format_locale': args.format_locale, 'oldmapping': args.oldmapping},
        'repeat_generation_identical': args.repeat,
        'sources': {path.name: {'bytes': path.stat().st_size, 'sha256': sha(path)} for path in [source, verify_source, Path(__file__)]},
        'outputs': {name: {'bytes': (args.output/name).stat().st_size, 'sha256': sha(args.output/name)} for name in ARTIFACTS+['independent-verification.json', 'export.stdout', 'export.stderr']},
        'classpath_artifacts': {},
    }
    # Record the relevant installed dependencies without redistributing jars.
    for path in sorted(Path(args.classpath.rstrip('*')).glob('*.jar')):
        if path.name.startswith(('orc-core-', 'jackson-core-', 'jackson-databind-', 'jackson-annotations-')):
            manifest['classpath_artifacts'][path.name] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
    (args.output/'generation-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')


if __name__ == '__main__':
    main()
