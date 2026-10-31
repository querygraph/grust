from pathlib import Path
p=Path('/Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/deferred-arithmetic/schema-reference.py')
s=p.read_text();start=s.index(' for ansi in [True,False]:');end=s.index(' for name,ansi,text in cases:',start)
block=''' for ansi in [True,False]:
  for name,query in [
   ('decimal_divide','SELECT a / b AS value FROM VALUES (CAST(7.12 AS DECIMAL(10,2)), CAST(2.30 AS DECIMAL(5,2))) AS v(a,b)'),
   ('decimal_div','SELECT a DIV b AS value FROM VALUES (CAST(7.12 AS DECIMAL(10,2)), CAST(2.30 AS DECIMAL(5,2))) AS v(a,b)'),
   ('decimal_mod','SELECT a % b AS value FROM VALUES (CAST(7.12 AS DECIMAL(10,2)), CAST(2.30 AS DECIMAL(5,2))) AS v(a,b)'),
   ('decimal_zero_divide','SELECT a / b AS value FROM VALUES (CAST(7.12 AS DECIMAL(10,2)), CAST(0 AS DECIMAL(5,2))) AS v(a,b)'),
   ('decimal_zero_mod','SELECT a % b AS value FROM VALUES (CAST(7.12 AS DECIMAL(10,2)), CAST(0 AS DECIMAL(5,2))) AS v(a,b)'),
   ('decimal_null_divisor','SELECT a / b AS value FROM VALUES (CAST(7.12 AS DECIMAL(10,2)), CAST(NULL AS DECIMAL(5,2))) AS v(a,b)'),
   ('decimal_wide','SELECT a / b AS value FROM VALUES (CAST(123456789012345678901.12 AS DECIMAL(30,2)), CAST(3.00 AS DECIMAL(10,2))) AS v(a,b)'),
   ('case_input','SELECT CASE WHEN 7 / id > 0 THEN 1 ELSE 0 END AS value FROM VALUES (2) AS v(id)'),
   ('case_zero','SELECT CASE WHEN 1 / 0 > 0 THEN 1 ELSE 0 END AS value'),
   ('string_zero','SELECT \'1\' / \'0\' AS value'),
   ('string_nonzero','SELECT \'7\' / \'2\' AS value'),
  ]:
   cases.append((('ansi_' if ansi else 'legacy_')+name,ansi,query))
'''
# repr preserves the SQL single quotes in the generated Python list.
block=block.replace("('string_zero','SELECT '1' / '0' AS value'),", "('string_zero',\"SELECT '1' / '0' AS value\"),").replace("('string_nonzero','SELECT '7' / '2' AS value'),", "('string_nonzero',\"SELECT '7' / '2' AS value\"),")
s=s[:start]+block+s[end:];s=s.replace('40 ANSI/legacy arithmetic SQL probes','22 decimal/CASE/string ANSI/legacy SQL probes')
Path('/tmp/sail-sdp-numeric-divisor-additional-reference.py').write_text(s)
compile(s,'additional-reference.py','exec')
