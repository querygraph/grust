from pathlib import Path
import json,hashlib
packet=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/fable-c2-corrected-review/lowercase')
inputs=json.loads((packet/'cases.json').read_text())
outputs=[bytes.fromhex(s).decode('utf-8') for s in (packet/'java.stdout').read_text().splitlines()]
assert len(inputs)==len(outputs)==68588
p=Path('/tmp/sail-sdp-root-lowercase-integration-corpus.json')
p.write_text(json.dumps({'cases':[{'input':i,'lower':o}for i,o in zip(inputs,outputs)]},ensure_ascii=False)+'\n')
print(json.dumps({'cases':len(inputs),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'path':str(p)}))
