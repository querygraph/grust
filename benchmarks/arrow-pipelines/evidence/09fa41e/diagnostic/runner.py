import pathlib, subprocess, time, json
p=pathlib.Path('/tmp/grust-relational-sample-09fa41e');p.mkdir(exist_ok=False)
binary='/tmp/grust-relational-baseline/20260914T164956Z/grust-arrow-pipeline-profile'
with (p/'result.jsonl').open('w') as out, (p/'stderr').open('w') as err:
 proc=subprocess.Popen([binary,'20000','8','3'],stdout=out,stderr=err)
 time.sleep(2)
 with (p/'sample-command.log').open('w') as samplelog:
  sample=subprocess.run(['/usr/bin/sample',str(proc.pid),'5','-file',str(p/'sample.txt')],stdout=samplelog,stderr=subprocess.STDOUT)
 code=proc.wait()
(p/'status.json').write_text(json.dumps({'binary':binary,'command':[binary,'20000','8','3'],'exit_code':code,'sample_exit_code':sample.returncode,'boundary':'Instrumented diagnostic run; timings excluded from uninstrumented benchmark statistics. Five seconds is the sampling window, not a query deadline.'},indent=2)+'\n')
print(p,code,sample.returncode)
