#!/bin/sh
# Regenerate the ANTLR 4 Rust parsers used by this probe (not committed: ~4 MB).
# Pinned inputs, as measured on 2026-10-03:
#   tool jar: antlr4rust/antlr4 release v0.6.0, antlr4-4.13.3-SNAPSHOT-complete.jar
#             sha256 391e77311794f7c8fed2bc6d291f54b04725e37456d79e1981edfd3fc919b677
#   GQL:      opengql/grammar 16ea71bd320ad07fd2c46a3066afbaef7d226922 GQL.g4
#   Cypher:   antlr/grammars-v4 7df52be94698550d219d299d04105c6bafadd9c3 cypher/*.g4
# Build: CARGO_TARGET_DIR=~/src/reference/build/antlr-probe cargo build --release -j 4
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=${WORK:-$HOME/src/reference/build/antlr-probe-inputs}
mkdir -p "$work"
cd "$work"
[ -f antlr4rust.jar ] || curl -sL -o antlr4rust.jar \
  https://github.com/antlr4rust/antlr4/releases/download/v0.6.0/antlr4-4.13.3-SNAPSHOT-complete.jar
shasum -a 256 antlr4rust.jar
base=https://raw.githubusercontent.com
curl -sL -o GQL.g4 $base/opengql/grammar/16ea71bd320ad07fd2c46a3066afbaef7d226922/GQL.g4
curl -sL -o CypherLexer.g4 $base/antlr/grammars-v4/7df52be94698550d219d299d04105c6bafadd9c3/cypher/CypherLexer.g4
curl -sL -o CypherParser.g4 $base/antlr/grammars-v4/7df52be94698550d219d299d04105c6bafadd9c3/cypher/CypherParser.g4
java -jar antlr4rust.jar -Dlanguage=Rust -visitor -o "$here/src/gql" GQL.g4
java -jar antlr4rust.jar -Dlanguage=Rust -visitor -o "$here/src/cypher" CypherLexer.g4 CypherParser.g4
