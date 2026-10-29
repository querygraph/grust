import argparse,json
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('engine',choices=['sail','spark']);args=parser.parse_args()
r=json.loads(Path('/tmp/sail-sdp-catalog-registration-'+args.engine+'.json').read_text())
cases={c['name']:c for c in r['cases']}
checks=[]
for name in ['graph_default_false','graph_default_true','concat','cast','unresolved','multipart','wrong_type','null','session_true_file_false','session_false_file_true','unset_database','explicit_database','private_view']:
 c=cases[name]
 try:
  assert c['session_catalog_after']==r['catalog']
  assert c['session_database_after']==r['database']
  if name in ('concat','cast','explicit_database','private_view'):
   assert c['outcome']=='registered', c.get('message')
  elif name=='unset_database':
   assert c['outcome']=='rejected', 'Unqualified persistent output requires an explicit database after SET CATALOG'
  elif name in ('session_true_file_false','graph_default_false'):
   assert c['outcome']=='rejected'
   assert c.get('condition')=='CAST_INVALID_INPUT', c.get('condition')
   assert c.get('exception_type')=='NumberFormatException', c.get('exception_type')
   assert c.get('sql_state')=='22018', c.get('sql_state')
  else:
   assert c['outcome']=='rejected'
   assert c.get('condition')=='PIPELINE_SQL_GRAPH_ELEMENT_REGISTRATION_ERROR', c.get('condition')
   assert c.get('exception_type')=='AnalysisException', c.get('exception_type')
   assert c.get('sql_state')=='42000', c.get('sql_state')
   parameters=c['parameters']
   assert set(parameters)=={'message','offendingQuery','codeLocation'}, parameters
   assert parameters['message'].startswith('Failed to resolve catalog expression: '), parameters
   query=c['sql'].split('\n')[-1]
   assert parameters['offendingQuery']=='\nOffending query:\n'+query+'\n', parameters
   line=2 if name=='session_false_file_true' else 1
   assert parameters['codeLocation'].endswith('/catalog.sql:'+str(line)), parameters
   if name in ('null','session_false_file_true','graph_default_true'):
    assert 'NOT_A_CONSTANT_STRING.NULL' in parameters['message'], parameters
  checks.append({'name':name,'outcome':'passed'})
 except (AssertionError,KeyError) as error:
  checks.append({'name':name,'outcome':'failed','error':str(error)})
result={'engine':args.engine,'scope':r['scope'],'passed':sum(c['outcome']=='passed' for c in checks),'failed':sum(c['outcome']=='failed' for c in checks),'checks':checks}
Path('/tmp/sail-sdp-catalog-design-assertions-'+args.engine+'.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(bool(result['failed']))
