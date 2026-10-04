#!/usr/bin/env python3
"""Read-only publication identity, JSONL and credential-pattern audit."""
import datetime,hashlib,io,json,re,subprocess,tarfile,zipfile
from pathlib import Path
root=Path('/private/tmp/grust-sail-review-interim-docs')
out=Path('/private/tmp/grust-sail-review-interim-publication')
manifest_path=root/'docs/reviews/sail-stream-experiments-2026-09-30/DOCUMENTATION-SNAPSHOT.json'
manifest=json.loads(manifest_path.read_text())
patterns={
 'aws_access_key':rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
 'github_token':rb'\b(?:gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b',
 'openai_style_token':rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}',
 'google_api_key':rb'\bAIza[0-9A-Za-z_-]{30,}',
 'slack_token':rb'\bxox[baprs]-[A-Za-z0-9-]{20,}',
 'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',
 'basic_bearer_auth':rb'(?i)authorization\s*[:=]\s*["\x27]?(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{16,}',
 'credential_url':rb'(?i)https?://[^\s:@/]{1,100}:[^\s@/]{8,100}@',
}
hits={};checked=0;archive_members=0;jsonl_lines=0

def scan(name,data):
 global checked,jsonl_lines
 checked+=1
 matched={label:len(re.findall(pattern,data)) for label,pattern in patterns.items() if re.search(pattern,data)}
 if matched:hits[name]=matched
 if name.endswith('.jsonl'):
  for line in data.splitlines():
   if line.strip():json.loads(line);jsonl_lines+=1

for row in manifest['files']:
 p=root/row['path'];data=p.read_bytes()
 assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
 scan(row['path'],data)
 if p.name.endswith(('.tar','.tar.gz','.tgz')):
  with tarfile.open(fileobj=io.BytesIO(data),mode='r:*') as archive:
   for member in archive.getmembers():
    if member.isfile():
     scan(row['path']+'::'+member.name,archive.extractfile(member).read());archive_members+=1
 elif p.name.endswith(('.zip','.whl')):
  with zipfile.ZipFile(io.BytesIO(data)) as archive:
   for name in archive.namelist():
    if not name.endswith('/'):
     scan(row['path']+'::'+name,archive.read(name));archive_members+=1
result={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'scan_units':checked,'archive_file_members':archive_members,'jsonl_rows_parsed_including_archives':jsonl_lines,'credential_pattern_matched_files':len(hits),'matches_file_and_count_only':hits,'scope':'Heuristic credential-like patterns; values never printed or recorded. Not exhaustive secret detection. Archive files inspected in memory without extraction.'}
(out/'independent-privacy-scan.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
