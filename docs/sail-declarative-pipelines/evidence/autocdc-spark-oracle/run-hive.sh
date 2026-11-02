#!/usr/bin/env bash
# Run the pipeline materialization and DDL tests against a Sail server whose catalog is a standalone
# Hive metastore, with embedded Derby and a local file warehouse. The test modules are the default
# profile's own, unchanged: Spark's HiveMaterializeTablesSuite also reuses the default suite's bodies.
#
# usage: run-hive-metastore.sh SAIL_BINARY METASTORE_DIR [PORT]
# METASTORE_DIR is filled on first use, and each download is checked against its Maven SHA-1.
# PORT is the Sail server, and PORT + 1 is the metastore.
set -euo pipefail

binary=$1
store=$2
port=${3:-15270}
metastore_port=$((port + 1))
root=/private/tmp/claude-501/-Users-alexy-src-grust-sdp/e456d749-5632-4fc6-88b7-cd047a0a4f11/scratchpad/hive/root
maven=https://repo1.maven.org/maven2
java_home=$(/usr/libexec/java_home -v 17)

fetch() {
    local url=$1 sha1=$2 file
    file=$store/downloads/$(basename "$url")
    if [[ ! -f $file ]]; then
        curl -fsSL -o "$file.part" "$url"
        echo "$sha1  $file.part" | shasum -a 1 -c - >/dev/null
        mv "$file.part" "$file"
    fi
}

mkdir -p "$store/downloads"
fetch "$maven/org/apache/hive/hive-standalone-metastore-server/4.0.1/hive-standalone-metastore-server-4.0.1-bin.tar.gz" \
    e6fd257ef9871e9c5d2e01528b85a47e0db78322
fetch "$maven/org/apache/hadoop/hadoop-client-api/3.3.6/hadoop-client-api-3.3.6.jar" \
    12ac6f103a0ff29fce17a078c7c64d25320b6165
fetch "$maven/org/apache/hadoop/hadoop-client-runtime/3.3.6/hadoop-client-runtime-3.3.6.jar" \
    81065531e63fccbe85fb04a3274709593fb00d3c
fetch "$maven/javax/servlet/javax.servlet-api/3.1.0/javax.servlet-api-3.1.0.jar" \
    3cd63d075497751784b2fa84be59432f4905bf7c
# The tarball leaves out what a Hadoop installation would provide.
fetch "$maven/org/apache/hadoop/hadoop-hdfs/3.3.6/hadoop-hdfs-3.3.6.jar" \
    ba40aca60f39599d5b1f1d32b35295bfde1f3c8b
fetch "$maven/org/apache/hadoop/hadoop-hdfs-client/3.3.6/hadoop-hdfs-client-3.3.6.jar" \
    d635e3eed4beb74213489ff003ca39dbe47ea44e
fetch "$maven/commons-io/commons-io/2.11.0/commons-io-2.11.0.jar" \
    a2503f302b11ebde7ebc3df41daebe0e4eea3689
fetch "$maven/org/slf4j/slf4j-api/1.7.36/slf4j-api-1.7.36.jar" \
    6c62681a2f655b49963a5983b8b0950a6120ae14
fetch "$maven/commons-collections/commons-collections/3.2.2/commons-collections-3.2.2.jar" \
    8ad72fe39fa8c91eaaf12aadb21e0c3661fe26d5
fetch "$maven/org/apache/commons/commons-collections4/4.4/commons-collections4-4.4.jar" \
    62ebe7544cb7164d87e0637a2a6a2bdc981395e8
fetch "$maven/org/apache/httpcomponents/httpclient/4.5.13/httpclient-4.5.13.jar" \
    e5f6cae5ca7ecaac1ec2827a9e2d65ae2869cada
fetch "$maven/org/apache/httpcomponents/httpcore/4.4.13/httpcore-4.4.13.jar" \
    853b96d3afbb7bf8cc303fe27ee96836a10c1834
fetch "$maven/com/google/code/gson/gson/2.9.0/gson-2.9.0.jar" \
    8a1167e089096758b49f9b34066ef98b2f4b37aa
fetch "$maven/commons-lang/commons-lang/2.6/commons-lang-2.6.jar" \
    0ce1edb914c94ebc388f086c6827e8bdeec71ac2
fetch "$maven/commons-configuration/commons-configuration/1.10/commons-configuration-1.10.jar" \
    2b36e4adfb66d966c5aef2d73deb6be716389dc9
fetch "$maven/com/fasterxml/woodstox/woodstox-core/5.4.0/woodstox-core-5.4.0.jar" \
    3e05dcce371d3f672feba29f086ad78a93ae3996
fetch "$maven/org/codehaus/woodstox/stax2-api/4.2.1/stax2-api-4.2.1.jar" \
    a3f7325c52240418c2ba257b103c3c550e140c83
fetch "$maven/org/apache/commons/commons-configuration2/2.8.0/commons-configuration2-2.8.0.jar" \
    6a76acbe14d2c01d4758a57171f3f6a150dbd462
fetch "$maven/org/apache/commons/commons-text/1.10.0/commons-text-1.10.0.jar" \
    3363381aef8cef2dbc1023b3e3a9433b08b64e01

home=$store/apache-hive-metastore-4.0.1-bin
if [[ ! -d $home ]]; then
    tar -xzf "$store/downloads/hive-standalone-metastore-server-4.0.1-bin.tar.gz" -C "$store" --no-same-owner
fi

run=$(mktemp -d "$store/run.XXXXXX")
mkdir "$run/conf" "$run/warehouse" "$run/managed"
cat >"$run/conf/metastore-site.xml" <<EOF
<?xml version="1.0"?>
<configuration>
  <property><name>metastore.thrift.port</name><value>$metastore_port</value></property>
  <property><name>metastore.warehouse.dir</name><value>file://$run/managed</value></property>
  <property><name>metastore.warehouse.external.dir</name><value>file://$run/warehouse</value></property>
  <property><name>javax.jdo.option.ConnectionURL</name><value>jdbc:derby:;databaseName=$run/metastore_db;create=true</value></property>
  <property><name>javax.jdo.option.ConnectionDriverName</name><value>org.apache.derby.jdbc.EmbeddedDriver</value></property>
  <property><name>metastore.expression.proxy</name><value>org.apache.hadoop.hive.metastore.DefaultPartitionExpressionProxy</value></property>
  <property><name>metastore.disallow.incompatible.col.type.changes</name><value>false</value></property>
</configuration>
EOF
classpath="$run/conf:$home/lib/*:$store/downloads/*"

wait_for_port() {
    local target=$1 owner=$2
    for _ in $(seq 1 1200); do
        if (exec 3<>"/dev/tcp/127.0.0.1/$target") 2>/dev/null; then
            return 0
        fi
        kill -0 "$owner"
        sleep 0.1
    done
    echo "nothing listening on $target" >&2
    return 1
}

metastore=
server=
stop() {
    if [[ -n $server ]]; then
        kill -INT "$server" 2>/dev/null || true
        wait "$server" 2>/dev/null || true
    fi
    if [[ -n $metastore ]]; then
        kill "$metastore" 2>/dev/null || true
        wait "$metastore" 2>/dev/null || true
    fi
}
trap stop EXIT

cd "$run"
export METASTORE_HOME=$home
"$java_home/bin/java" -cp "$classpath" org.apache.hadoop.hive.metastore.tools.schematool.MetastoreSchemaTool \
    -dbType derby -initSchema >schema.log 2>&1
"$java_home/bin/java" --add-opens java.base/java.net=ALL-UNNAMED --add-opens java.base/java.lang=ALL-UNNAMED \
    -cp "$classpath" org.apache.hadoop.hive.metastore.HiveMetaStore -p "$metastore_port" >metastore.log 2>&1 &
metastore=$!
wait_for_port "$metastore_port" "$metastore"

export SAIL_CATALOG__LIST="[{name=\"sail\",type=\"hms\",uris=[\"127.0.0.1:$metastore_port\"]}]"
export SPARK_REMOTE="sc://localhost:$port"
export PYTHONPATH="$root/python:$root/scripts/spark-pipelines-tests${PYTHONPATH:+:$PYTHONPATH}"
"$binary" spark server --port "$port" >server.log 2>&1 &
server=$!
wait_for_port "$port" "$server"

cd "$root"
tests=python/pysail/tests/spark/pipelines
PY=/Users/alexy/src/sail-sdp-fable-gate-venv/bin/python
$PY -m pytest "$tests/test_autocdc_semantics.py" "$tests/test_autocdc_spark_suites.py" -q -p no:cacheprovider -p hive_profile_plugin --tb=short > $run/pytest.out 2>&1 || true
echo HIVE_TESTS=$?; tail -1 $run/pytest.out
kill -INT "$server" 2>/dev/null || true; wait "$server" 2>/dev/null || true; server=
unset SPARK_REMOTE
cd /private/tmp/claude-501/-Users-alexy-src-grust-sdp/e456d749-5632-4fc6-88b7-cd047a0a4f11/scratchpad/crash
for seed in 31; do $PY crash.py $run/crash$seed $seed 6 2>&1 | tail -1 | tr '\\' ' ' | cut -c1-420; done
