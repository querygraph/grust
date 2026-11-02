from pathlib import Path
import json, re, subprocess
import xml.etree.ElementTree as ET
root=Path('/Users/alexy/src/grust-sdp-review-gate')
candidate=json.loads(Path('/tmp/sail-sdp-evidence-candidate.json').read_text())
def git(*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()
assert git('rev-parse','HEAD')==candidate['commit']
assert not git('status','--porcelain')
# Preserve raw logs exactly, including pytest's trailing spaces.
subprocess.run(['git','-C',str(root),'diff','--check',candidate['base'],candidate['commit'],'--','*.md','*.json','*.py'],check=True)
assert not re.search(r'^(<<<<<<<|=======|>>>>>>>)( |$)',(root/'codex-to-codex.md').read_text(),re.M)
docs=root/'docs/sail-declarative-pipelines'
for path in docs.rglob('*.json'):
    if path.relative_to(docs).as_posix() == 'evidence/catalog-empty-schema-read/spark-catalog-reference/inputs/json/part.json':
        # A retained source-data fixture is JSON Lines, not a JSON document.
        assert [json.loads(line) for line in path.read_text().splitlines()] == [{'id': 3}, {'id': 1}]
        continue
    data=json.loads(path.read_text())
    if path.name=='gate.json' and 'sail_commit' in data:
        subprocess.run(['git','-C','/Users/alexy/src/sail-pipelines-proposal','cat-file','-e',data['sail_commit']+'^{commit}'],check=True)
for path in docs.rglob('*.xml'):
    ET.parse(path)
for path in docs.rglob('*.md'):
    for link in re.findall(r'\]\(([^)]+)\)',path.read_text()):
        if not link.startswith(('http:','https:','#','mailto:')):
            assert (path.parent/link.split('#')[0]).exists(), (path,link)
for sha,count in [('3221b8ab68c9d248c9c9d28a04e64235db1b85a1',54),('8dccd5a6e419f2d2485bd94686bede5a219ad084',66),('fd93eb6ef44e25a8a28e0673f9906d6de506cac8',74),('0393db9226638910a9552b97aa0a8cc98e48816a',68),('12664ae7eee787e1d70bc5a9d78934869da95af0',75),('789d28ac301ce646fdb4e15d73e4954e687709ae',77),('29eeb6546c4d5353fe4b0d611f14dbd1fb9ecdf9',89),('038f28f95eebfb78edf1ae8a76d0fbd27adf4366',101),('bbda0c14d59920b650618cb8682fc68261106079',101),('a007290e7a628c0b9da373b4490431147134e94e',106),('e4d578ce0658f94884753e3bfdadb3f2208f5af6',112),('5a5e256328406b6dcbffd0db83dd39d6f9746553',112),('9031373d0dfbf5c7a876a113a0a273ec933e6ccd',121),('0a84375381236786f66f09ada7578c9c8efef0c7',121),('eb417941e86dfe18cbdc141d7a55a675ea0e26e6',122),('24533f1f0d32621b54d3f0f78f353be673dc493c',124),('6c87cd39de51f925221fbc97ed475810f655b188',129),('a587b7e6d86d734a816d6455ad922d2a1faf7258',137),('900925b7d0a01ea118fa6e3fd0d1d3bf8d5d1b2d', 143),('f064fb2709e14d3064c93a9c03b25dbcd8d40ec5', 157),('2075468608cccc0d8e3581b2f235154e557a56b8',160),('9f96b534dde38228ab7e1eba7d4a383c93a6c8cb',164),('8ef94cb7dd09b1cade4d62afa7fe19cb9272b877',170),('b145ed12d92fb98b0e484b101be17b24f8ec38fc',184),('39f070e62540eacdb260ee2c241027e53838899f',192),('e856e584652dfcc9f444ce67fd71ef440cf9af8b',195),('a2dbec30eb48a15040798049b9e81e9606ff1d5f',199),('bbf438c0661cdfa4a3fab3af70439f7f788615d8',211),('efc21f2c53b0d8c886b31928ed67131a1de7c6db',217),('35565f49d1f4666255b431c63f1e4f8cabdf3ecf',217),('cb27f1a9dbd0fd888e4d5d8babff18bb349478cc',217),('9c42934ed8e095b2e7ccaafeef2faea3f35f797a',222),('ac7bff5007545859b6c972e2d9b9a17ffc38fa97',226),('5647383189ce71dd97d62fbe97b7013b7bd6e038',236),('010469d3c079285d637752c4cde012ef9bad0b75',238),('73305d1f7b3d69fefad19944e1270b69fe9adf8f',238),('992f5bcbf60added5b44596f279ab8801f0c0045',246),('cd79b2bcc94fdf69418615fb0c0c60b5bee9f871',246),('96eb6d75fe13f1254af5fb1452d16abbd1fff446',246),('e28c27782604cc9f31ed6ec219114149d4ecdca8',246),('87a7c941d30c952e6c928e1a6d2b4aec2b45abf6',273)]:
    p=docs/'evidence'/sha
    suite=ET.parse(p/'pytest.xml').getroot().find('testsuite')
    assert (int(suite.get('tests')),suite.get('failures'),suite.get('errors'),suite.get('skipped'))==(count,'0','0','0')
    upstream=json.loads((p/'spark-python.json').read_text())
    assert upstream['tests_run']==67 and upstream['server_spark_version']=='4.2.1'
    assert upstream['failures']==upstream['errors']==upstream['skipped']==0
for sha,count in [('29eeb6546c4d5353fe4b0d611f14dbd1fb9ecdf9',8),('038f28f95eebfb78edf1ae8a76d0fbd27adf4366',9)]:
    reference=json.loads((docs/'evidence'/sha/'spark-reference.json').read_text())
    assert reference['spark_version']=='4.2.1'
    assert len(reference['cases'])==count and all(c['outcome']=='passed' for c in reference['cases'])
publication=docs/'evidence'/'038f28f95eebfb78edf1ae8a76d0fbd27adf4366'
failed=ET.parse(publication/'initial-gate.xml').getroot().find('testsuite')
assert (failed.get('tests'),failed.get('failures'),failed.get('errors'))==('85','4','0')
receipt=json.loads((publication/'gate.json').read_text())
reference=next(c for c in receipt['checks'] if 'test_blobs' in c)
for path,blob in reference['test_blobs'].items():
    actual=subprocess.check_output(['git','-C','/Users/alexy/src/sail-pipelines-proposal','rev-parse',receipt['sail_commit']+':'+path],text=True).strip()
    assert actual==blob
view=docs/'evidence'/'a007290e7a628c0b9da373b4490431147134e94e'
reference=json.loads((view/'spark-reference.json').read_text())
assert reference['spark_version']=='4.2.1' and len(reference['cases'])==5
cases={c['name']:c for c in reference['cases']}
assert cases['failed_table_write']['run']=='failed'
assert cases['failed_table_write']['output_rows']==[]
assert cases['selected_tables_via_view']['chosen_rows']==[{'value':6}]
for name in ('unselected_view','selected_tables_via_view','view_with_absent_excluded_table','view_selected_alone'):
    assert cases[name]['run']=='success' and cases[name]['exists']['output']
for name in ('view_with_absent_excluded_table','view_selected_alone'):
    assert not cases[name]['exists']['raw']
for file,tests,failures in [('initial-gate.xml','5','1'),('second-gate.xml','106','1')]:
    suite=ET.parse(view/file).getroot().find('testsuite')
    assert (suite.get('tests'),suite.get('failures'),suite.get('errors'))==(tests,failures,'0')
assert git('rev-parse','HEAD')==candidate['commit']
pkg=docs/'evidence'/'catalog-expression-design'
if pkg.exists():
    provenance=json.loads((pkg/'provenance.json').read_text())
    assert provenance['sail_source_commit']=='2d54d5a568f8dbac68d2b9ac8519380a25782fd3'
    assert provenance['cli_sha256']==json.loads((docs/'evidence'/'ac7bff5007545859b6c972e2d9b9a17ffc38fa97'/'gate.json').read_text())['cli_sha256']
    analyzer=json.loads((pkg/'analyzer-reference.json').read_text())
    assert analyzer['spark_version']=='4.2.1' and len(analyzer['cases'])==22
    for engine,passed,failed in [('spark',13,0),('sail',2,11)]:
        report=json.loads((pkg/('assertions-'+engine+'.json')).read_text())
        assert (report['passed'],report['failed'])==(passed,failed)
        registration=json.loads((pkg/('registration-'+engine+'.json')).read_text())
        assert registration['spark_version']=='4.2.1' and len(registration['cases'])==13
        cases={case['name']:case for case in registration['cases']}
        assert cases['unresolved']['sql']=="SET CATALOG CONCAT(foo, '1')"
        assert cases['multipart']['sql']=='SET CATALOG test.cat'
        assert all(case['session_catalog_after']==registration['catalog'] and case['session_database_after']==registration['database'] for case in registration['cases'])
print('PASS detached documentation gate '+candidate['commit'])

activation=docs/"evidence"/"992f5bcbf60added5b44596f279ab8801f0c0045"
r=json.loads((activation/"assertions-sail.json").read_text())
assert (r["passed"],r["failed"])==(11,2)
assert {c["name"] for c in r["checks"] if c["outcome"]=="failed"}=={"graph_default_false","session_true_file_false"}
for engine,condition,state in [("sail",None,None),("spark","CAST_INVALID_INPUT","22018")]:
 r=json.loads((activation/("cast-transport-"+engine+".json")).read_text())
 assert r["spark_version"]=="4.2.1" and r["exception_type"]=="NumberFormatException"
 assert (r["condition"],r["sql_state"])==(condition,state)
print("PASS retained activation checks including two unresolved metadata failures")

cast=docs/"evidence"/"shared-cast-error-design"
provenance=json.loads((cast/"provenance.json").read_text())
assert provenance["sail_source_commit"]=="992f5bcbf60added5b44596f279ab8801f0c0045"
assert provenance["cli_sha256"]==json.loads((activation/"gate.json").read_text())["cli_sha256"]
for engine,passed,failed in [("spark",24,0),("sail",4,20)]:
 r=json.loads((cast/("assertions-"+engine+".json")).read_text())
 assert (r["passed"],r["failed"])==(passed,failed)
 r=json.loads((cast/("observations-"+engine+".json")).read_text())
 assert r["spark_version"]=="4.2.1" and len(r["cases"])==24
print("PASS shared cast design baseline; all twenty Sail mismatches retained")

shared=docs/"evidence"/"cd79b2bcc94fdf69418615fb0c0c60b5bee9f871"
for file,passed,failed in [("catalog-design-assertions-sail.json",11,2),("cast-design-assertions-sail.json",4,20)]:
 r=json.loads((shared/file).read_text())
 assert (r["passed"],r["failed"])==(passed,failed)
print("PASS shared error extraction receipt; required failures remain visible")

transport=docs/"evidence"/"96eb6d75fe13f1254af5fb1452d16abbd1fff446"
for file,passed,failed in [("catalog-design-assertions-sail.json",11,2),("cast-design-assertions-sail.json",4,20)]:
 r=json.loads((transport/file).read_text())
 assert (r["passed"],r["failed"])==(passed,failed)
print("PASS structured transport receipt; required failures remain open")

codec=docs/"evidence"/"e28c27782604cc9f31ed6ec219114149d4ecdca8"
for file,passed,failed in [("catalog-design-assertions-sail.json",11,2),("cast-design-assertions-sail.json",4,20)]:
 r=json.loads((codec/file).read_text())
 assert (r["passed"],r["failed"])==(passed,failed)
print("PASS ANSI codec receipt with unchanged pre-activation failures")

activated=docs/"evidence"/"87a7c941d30c952e6c928e1a6d2b4aec2b45abf6"
for file,passed,failed in [("catalog-design-assertions-sail.json",13,0),("cast-design-assertions-sail.json",19,5)]:
 r=json.loads((activated/file).read_text())
 assert (r["passed"],r["failed"])==(passed,failed)
r=json.loads((activated/"reference.json").read_text())
assert r["spark_version"]=="4.2.1" and len(r["cases"])==27 and all(c["outcome"]=="passed" for c in r["cases"])
print("PASS shared ANSI activation evidence; five broader cast failures retained")
