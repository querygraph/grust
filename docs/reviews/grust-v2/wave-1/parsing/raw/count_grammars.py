"""Count productions and keywords in the GQL and Cypher grammars.

Usage: python3 count_grammars.py <opengql/GQL.g4> <grammars-v4/cypher dir> <openCypher.bnf>
"""
import re, sys

def antlr(path):
    t = open(path).read()
    t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
    t = re.sub(r'//[^\n]*', '', t)
    rules = re.findall(r'^\s*(fragment\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\n?\s*:', t, flags=re.M)
    parser = [r for f, r in rules if r[0].islower()]
    lexer = [r for f, r in rules if r[0].isupper() and not f]
    frag = [r for f, r in rules if f]
    return len(parser), len(lexer), len(frag)

gql, cy, bnf = sys.argv[1], sys.argv[2], sys.argv[3]
p, l, f = antlr(gql)
print(f"GQL.g4: {p} parser rules, {l} lexer rules, {f} fragments, {sum(1 for _ in open(gql))} lines")
lines = open(gql).read().split('\n')
def section(a, b):
    return sum(1 for x in lines[a:b] if re.match(r'^[A-Z_0-9]+\s*:', x))
idx = {name: i for i, x in enumerate(lines) for name in ['// Reserved words', '// Prereserved words', '// Nonreserved words', '// 21.4 GQL terminal characters'] if x.strip() == name}
print("GQL keywords: reserved", section(idx['// Reserved words'], idx['// Prereserved words']),
      "prereserved", section(idx['// Prereserved words'], idx['// Nonreserved words']),
      "nonreserved", section(idx['// Nonreserved words'], idx['// 21.4 GQL terminal characters']))
pp, _, _ = antlr(cy + '/CypherParser.g4')
_, ll, ff = antlr(cy + '/CypherLexer.g4')
kw = len(re.findall(r"^[A-Z]+\s*:\s*'[A-Z]+'", open(cy + '/CypherLexer.g4').read(), flags=re.M))
print(f"grammars-v4 Cypher: {pp} parser rules, {ll} lexer rules ({kw} keyword tokens), {ff} fragments")
t = open(bnf).read()
prods = re.findall(r'^<([^>]+)>\s*::=', t, flags=re.M)
words = set(re.findall(r'\b([A-Z][A-Z]+)\b', re.sub(r'<[^>]*>', '', re.sub(r'^#.*$', '', t, flags=re.M))))
print(f"openCypher.bnf: {len(prods)} productions, {len(words)} distinct upper-case terminal words, {t.count(chr(10))} lines")
