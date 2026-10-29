from pathlib import Path
import json,subprocess
source=Path('/tmp/sail-sdp-orc-probe/output/nullable.orc');raw=bytearray(source.read_bytes());start=len(raw)-1-raw[-1];pos=start
# The writer's PostScript field1 is footer_length (varint); parse wire tag/value.
def varint():
 global pos
 value=0;shift=0
 while True:
  b=raw[pos];pos+=1;value|=(b&127)<<shift
  if not b&128:return value
  shift+=7
assert varint()==8
length=varint();footer=start-length
assert 3<=footer<start and length>=3
raw[footer:footer+3]=b'\xff\xff\xff'
path=Path('/tmp/sail-sdp-orc-malformed-block.orc');path.write_bytes(raw)
r=subprocess.run(['/tmp/sail-sdp-orc-probe/target/debug/sail-sdp-orc-dependency-probe','read',str(path)],capture_output=True,text=True,timeout=30)
report={'scope':'Isolated malformed ORC footer-block boundary; no production Sail reader exists','source':str(source),'fixture':str(path),'mutation':'Footer first compression block claims original payload longer than remaining footer','exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
Path('/tmp/sail-sdp-orc-malformed-block.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
