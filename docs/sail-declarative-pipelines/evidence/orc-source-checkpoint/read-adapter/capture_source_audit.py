"""Capture exact source anchors for the read-only adapter handoff."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

ROOT=Path(__file__).resolve().parent
SAIL=Path('/Users/alexy/src/sail-pipelines-proposal')
SPARK=Path('/Users/alexy/src/spark-sdp-4.2.1')
NATIVE=Path('/Users/alexy/src/orc-rust-sdp')
SAIL_PIN='db8844172d2b6b70095796987bcff613f2ad62aa'
SPARK_PIN='617618396087429b5627a86ce933bb0f5d6645cb'
NATIVE_PIN='ec6baa46860fb3df95c23a72124e736c5334a418'
REGISTRY=Path('/Users/alexy/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f')

def git(repo,*args):
 return subprocess.check_output(['git','-C',str(repo),*args])

def sha(value):
 return hashlib.sha256(value).hexdigest()

sources=[]
def capture(label,kind,path,ranges,claim,repo=None,pin=None,package=None):
 if repo:
  data=git(repo,'show',f'{pin}:{path}')
  identity={'repository':str(repo),'commit':pin,'git_blob':git(repo,'rev-parse',f'{pin}:{path}').decode().strip()}
 else:
  data=(REGISTRY/package/path).read_bytes()
  identity={'registry_package':package,'cargo_lock_package_checksum':checksums[package]}
 lines=data.splitlines(keepends=True)
 entry={'label':label,'kind':kind,'source_path':path,'source_sha256':sha(data),'claim':claim,**identity,'excerpts':[]}
 for start,end in ranges:
  assert 1<=start<=end<=len(lines),(path,start,end,len(lines))
  selected=b''.join(lines[start-1:end])
  target=Path('sources')/f'{label}-{start}-{end}.txt'
  (ROOT/target).parent.mkdir(exist_ok=True)
  (ROOT/target).write_bytes(selected)
  entry['excerpts'].append({'first_line':start,'last_line':end,'file':str(target),'sha256':sha(selected)})
 sources.append(entry)

lock=tomllib.loads(git(SAIL,'show',f'{SAIL_PIN}:Cargo.lock').decode())
checksums={p['name']+'-'+p['version']:p.get('checksum') for p in lock['package']}
sail=[
 ('listing-contract','crates/sail-data-source/src/listing/source.rs',[(36,95),(121,134),(160,208),(351,379)],'ReadFormat/scan inputs; read case sensitivity consumed before scan and top-level reconciliation'),
 ('listing-inference','crates/sail-data-source/src/listing/utils.rs',[(60,74),(140,190),(269,306)],'Arrow schema merge; take ten nonempty objects per URL; shared full-file listing/path rules'),
 ('listing-table-config','crates/sail-data-source/src/listing/table.rs',[(1,45)],'ListingTableSourceConfig has no read-case-sensitivity field'),
 ('planner-read-case','crates/sail-plan/src/resolver/query/read.rs',[(225,255),(610,638)],'Planner supplies source read_case_sensitive'),
 ('avro-read','crates/sail-data-source/src/formats/avro/read.rs',[(1,73)],'ReadFormat implementation and preservation of FileScanConfig inputs'),
 ('json-read','crates/sail-data-source/src/formats/json/read.rs',[(105,175)],'Existing shared scan construction'),
 ('parquet-read','crates/sail-data-source/src/formats/parquet/read.rs',[(245,300)],'Existing runtime source and FileScanConfig construction'),
 ('csv-source','crates/sail-data-source/src/formats/csv/source.rs',[(162,240)],'Custom FileSource and opener patterns'),
 ('binary-source','crates/sail-data-source/src/formats/binary/source.rs',[(45,116)],'Custom FileSource pattern'),
 ('orc-controlled-factory','crates/sail-data-source/src/formats/orc/metadata.rs',[(1,122)],'Infer logical first; configured native builder and physical-schema bridge; fixed semantic-option contract'),
 ('orc-object-reader','crates/sail-data-source/src/formats/orc/reader.rs',[(1,140)],'Pinned version/ETag; exact-range reads; no memory reservation'),
 ('schema-evolution','crates/sail-common-datafusion/src/schema_evolution.rs',[(205,305),(554,603),(641,735),(1056,1101)],'Existing generic reconciliation/cast rules are not a Spark ORC LTZ/NTZ compatibility policy'),
 ('codec-context','crates/sail-execution/src/proto/codec.rs',[(360,380),(700,738)],'Worker decoder receives TaskContext; nearby local runtime attachment'),
 ('reservation-buffer','crates/sail-python-udf/src/buffer.rs',[(1,58)],'Existing local MemoryReservation ownership pattern'),
 ('reservation-delta','crates/sail-delta-lake/src/physical_plan/log_replay_exec.rs',[(880,920)],'Existing scan memory reservation usage'),
 ('option-layer','crates/sail-common-datafusion/src/datasource.rs',[(218,245)],'SourceInfo option layer order and read semantic setting'),
 ('format-registration','crates/sail-session/src/formats.rs',[(1,60)],'Normal shared listing source registration'),
 ('read-only-format','crates/sail-data-source/src/formats/binary/write.rs',[(1,22)],'Existing explicit unsupported writing boundary'),
 ('option-generation','crates/sail-data-source/build.rs',[(1,14)],'Generated format options build mechanism'),
]
for label,path,ranges,claim in sail:
 capture(label,'pinned-git',path,ranges,claim,SAIL,SAIL_PIN)
capture('spark-orc-utils','pinned-git','sql/core/src/main/scala/org/apache/spark/sql/execution/datasources/orc/OrcUtils.scala',[(70,100),(125,178),(193,310)],'First usable/merged schema; container annotations; positional timestamp check with STRUCT-only recursion; separate field mapping',SPARK,SPARK_PIN)
for label,path,ranges,claim in [
 ('native-metadata-budget','src/reader/metadata.rs',[(55,145),(285,417)],'File-tail encoded/decoded/depth limits; not a whole scan or stripe/decoded array memory cap'),
 ('native-stripe-allocation','src/stripe.rs',[(206,292)],'Async stripe footer decode and selected encoded stream retention'),
 ('native-async-poll','src/async_arrow_reader.rs',[(160,255)],'CPU array decoding occurs in stream polling'),
]:
 capture(label,'pinned-git',path,ranges,claim,NATIVE,NATIVE_PIN)
 vendored=git(SAIL,'show',f'{SAIL_PIN}:vendor/orc-rust/{path}')
 assert sha(vendored)==sources[-1]['source_sha256'],path
 sources[-1]['sail_vendor_crosscheck']={'commit':SAIL_PIN,'path':f'vendor/orc-rust/{path}','sha256':sha(vendored),'matches_native':True}
for label,package,path,ranges,claim in [
 ('df-projection','datafusion-datasource-55.2.0','src/projection.rs',[(33,101),(153,286)],'SplitProjection unique input file columns and remaining projection opener'),
 ('df-filesource','datafusion-datasource-55.2.0','src/file.rs',[(70,179)],'FileSource opener has no TaskContext and repartitioning defaults enabled'),
 ('df-scan-context','datafusion-datasource-55.2.0','src/file_scan_config/mod.rs',[(699,733)],'Scan has TaskContext but passes store/config/partition into opener'),
 ('df-objectmeta-proto','datafusion-datasource-55.2.0','src/proto.rs',[(55,115)],'Worker PartitionedFile conversion drops ETag/version and opaque extensions'),
 ('df-projection-proto','datafusion-datasource-55.2.0','src/file_scan_config/proto.rs',[(185,222)],'Decoded projection requires source pushdown support or falls back'),
 ('df-task-pool','datafusion-execution-55.2.0','src/task.rs',[(120,145)],'Worker-local pool and runtime environment getters'),
]:
 capture(label,'locked-registry-source',path,ranges,claim,package=package)
result={'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'scope':'Source-only audit, no build/runtime qualification; resource defaults and decoded-memory admission are unresolved', 'handoff_sha256':sha((ROOT/'READ-ADAPTER-HANDOFF.md').read_bytes()),'capture_script_sha256':sha(Path(__file__).read_bytes()), 'sources':sources}
(ROOT/'source-audit.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(len(sources),'source files;',sum(len(s['excerpts']) for s in sources),'exact excerpts')
