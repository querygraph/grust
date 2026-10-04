"""Freeze and exercise only archive-link helpers; no operational snapshot gate."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

OUT=Path(__file__).resolve().parent
EXP=OUT.parent
PYTHON=Path('/Users/alexy/src/sail-extensions-poc/.venvs/extensions-datafusion/bin/python')
OLD=Path('/private/tmp/grust-sail-review-ownership-docs')
REL=Path('docs/reviews/sail-stream-experiments-2026-09-30')
ARCHIVE=str(REL/'documentation-validation-publication/preparation-attempt01/RESULTS.md')
SOURCE_MANIFEST=str(REL/'documentation-validation-publication/preparation-attempt01/DOCUMENTATION-SNAPSHOT.json')
ORIGINAL=str(REL/'RESULTS.md')
CONTEXT={ARCHIVE:dict(original_path=ORIGINAL,source_manifest=SOURCE_MANIFEST)}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    report=dict(started_utc=utc(),outcome='INCONCLUSIVE',scope=__doc__)
    private=Path(tempfile.mkdtemp(prefix='documentation-archive-context-gate-',dir='/private/tmp'))
    (private/'documentation-archive-context').mkdir()
    source_files={EXP/'verify_documentation_snapshot.py':private/'verify_documentation_snapshot.py',
                  OUT/'test_archive_context.py':private/'documentation-archive-context/test_archive_context.py'}
    before={str(p.relative_to(EXP)):sha(p) for p in source_files}
    command=[str(PYTHON),'-B',str(private/'documentation-archive-context/test_archive_context.py')]
    report.update(private_frozen_copy=str(private),source_hashes=before,command=command,
                  interpreter=str(PYTHON),interpreter_sha256=sha(PYTHON))
    try:
        for source,target in source_files.items():
            shutil.copyfile(source,target)
            assert sha(source)==sha(target)==before[str(source.relative_to(EXP))]
        with (OUT/'controls.stdout').open('xb') as stdout,(OUT/'controls.stderr').open('xb') as stderr:
            done=subprocess.run(command,stdout=stdout,stderr=stderr,check=False,timeout=60,
                                env={'PATH':str(PYTHON.parent)+':/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'})
        report['returncode']=done.returncode
        assert done.returncode==0 and 'Ran 16 tests' in (OUT/'controls.stderr').read_text()
        spec=importlib.util.spec_from_file_location('frozen_archive_verifier',private/'verify_documentation_snapshot.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        manifest_path=OLD/REL/'DOCUMENTATION-SNAPSHOT.json'
        before_manifest=sha(manifest_path)
        assert before_manifest=='5ee69bac72d6dcfbe7f84029c736ef55ccfbff21f268fe005ba04605175dec1d'
        manifest=json.loads(manifest_path.read_text())
        body=(OLD/ARCHIVE).read_bytes()
        try:
            module.check_markdown_links(OLD,OLD/ARCHIVE,body)
        except AssertionError as error:
            assert 'missing link' in str(error)
            report['unmapped_actual_archive']='EXPECTED_MISSING_LINK'
        else:
            raise AssertionError('baseline link failure did not reproduce')
        manifest['archived_markdown_link_contexts']=CONTEXT
        bases=module.markdown_link_contexts(OLD,manifest)
        count=module.check_markdown_links(OLD,OLD/ARCHIVE,body,bases[ARCHIVE])
        assert count==68
        historical=json.loads((OLD/SOURCE_MANIFEST).read_text())
        row=next(r for r in historical['files'] if r['path']==ORIGINAL)
        assert row['sha256']==sha(OLD/ARCHIVE)=='7cf7f2e3fb677f3e547db4214de2dd9d48c2db8f4a5463a3234bc002444e7d9a'
        assert row['bytes']==len(body)==33684
        assert sha(manifest_path)==before_manifest
        report['actual_archive']=dict(archived_path=ARCHIVE,archived_sha256=sha(OLD/ARCHIVE),
            original_path=ORIGINAL,source_manifest=SOURCE_MANIFEST,source_manifest_sha256=sha(OLD/SOURCE_MANIFEST),
            historical_row=row,relative_links_checked=count,all_targets_present=True,
            full_documentation_gate_executed=False,old_snapshot_manifest_unchanged=True)
        assert {str(p.relative_to(EXP)):sha(p) for p in source_files}==before
        assert all(sha(target)==before[str(source.relative_to(EXP))] for source,target in source_files.items())
        report.update(outcome='PASS_FROZEN_ARCHIVE_CONTEXT_CONTROLS',controls=16,source_unchanged=True)
    except Exception as error:
        report.update(outcome='FAIL',error=repr(error))
        raise
    finally:
        report.update(finished_utc=utc(),script_sha256=sha(Path(__file__)),logs={n:sha(OUT/n) for n in ['controls.stdout','controls.stderr'] if (OUT/n).exists()})
        with (OUT/'receipt.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    with (OUT/'context.json').open('x') as f:json.dump(CONTEXT,f,indent=2);f.write('\n')
    print(report['outcome'],sha(OUT/'receipt.json'))


if __name__=='__main__':
    main()
