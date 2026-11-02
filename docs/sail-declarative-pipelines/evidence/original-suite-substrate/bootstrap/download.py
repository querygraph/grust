from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
import hashlib,json
ROOT=Path(__file__).resolve().parent;DEST=ROOT/'artifacts';DEST.mkdir(exist_ok=True)
@dataclass(frozen=True)
class Artifact:
    group: str
    name: str
    version: str
    classifier: str=''
    @property
    def filename(self)->str:return f'{self.name}-{self.version}'+(f'-{self.classifier}'if self.classifier else '')+'.jar'
    @property
    def url(self)->str:return 'https://repo.maven.apache.org/maven2/'+self.group.replace('.','/')+'/'+self.name+'/'+self.version+'/'+self.filename
artifacts=[Artifact('org.apache.spark',name+'_2.13','4.2.1','tests')for name in ['spark-pipelines','spark-core','spark-sql','spark-catalyst','spark-sql-api','spark-common-utils','spark-tags','spark-connect']]+[Artifact('org.apache.spark',name+'_2.13','4.2.1','test-sources')for name in ['spark-pipelines','spark-connect']]+[Artifact('org.scalatest','scalatest-app_2.13','3.2.19')]
artifacts += [Artifact('io.grpc','grpc-api','1.76.0'),Artifact('org.scalatestplus','mockito-5-18_2.13','3.2.19.0'),Artifact('org.mockito','mockito-core','5.23.0'),Artifact('net.bytebuddy','byte-buddy','1.18.4'),Artifact('net.bytebuddy','byte-buddy-agent','1.18.4'),Artifact('org.objenesis','objenesis','3.5')]
artifacts += [Artifact('com.google.protobuf','protobuf-java','4.33.5'),Artifact('org.apache.spark','spark-hive_2.13','4.2.1','tests'),Artifact('org.apache.spark','spark-hive_2.13','4.2.1','test-sources')]
def fetch(a:Artifact)->dict:
 p=DEST/a.filename
 with urlopen(a.url,timeout=60)as response:data=response.read()
 checksum_url=a.url+'.sha1'
 with urlopen(checksum_url,timeout=30)as response:expected=response.read().decode().strip().split()[0]
 assert hashlib.sha1(data).hexdigest()==expected,a.filename
 p.write_bytes(data)
 return {'url':a.url,'path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'published_sha1':expected,'checksum_url':checksum_url}
with ThreadPoolExecutor(max_workers=6)as pool:results=list(pool.map(fetch,artifacts))
(ROOT/'artifacts.json').write_text(json.dumps({'recorded_at':datetime.now(timezone.utc).isoformat(),'artifacts':results},indent=2)+'\n')
print('Downloaded and checksum-verified',len(results),'isolated test artifacts',sum(x['bytes']for x in results),'bytes')
