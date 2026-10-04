# Complete host integration patch {#host-code}

This appendix contains every changed line, with unified context, under `crates/`
and the workspace Cargo manifests/lockfile between the fork's actual upstream
base and the reviewed prototype. It includes generic integration, domain-specific
GraphUtils helpers, tests and dependency changes; inclusion is not a proposal
that every file belongs in the minimum extension API.

Patch base: `a85d912d72ae03a6d97b6a3fd151f5752da636c6`.
Patch result: `bd8ce9ae8839477e2c08a0475ab7900b115c5366`.
Present plain-Sail comparison: `4d31e15b350c975aed95c23e6cc7e7c51c59fe52`.

This is a complete historical integration patch, not a patch against present
plain Sail. It has not been rebased or qualified against that newer revision.
The source bundle also contains the complete affected files at each of those
three revisions when the file exists. Tests in this appendix are source
evidence; this document build does not rerun their historical runtime gates.

## 01. Cargo.lock {#host-patch-01}

```diff
diff --git a/Cargo.lock b/Cargo.lock
index 60a069a1da595a0e0cea905daf9f97dc7f8a6a04..0fac74dc746d3eacb4c77d4c3b4306f4e2602fde 100644
--- a/Cargo.lock
+++ b/Cargo.lock
@@ -133,7 +133,7 @@ version = "1.1.5"
 source = "registry+https://github.com/rust-lang/crates.io-index"
 checksum = "40c48f72fd53cd289104fc64099abca73db4166ad86ea0b4341abe65af83dadc"
 dependencies = [
- "windows-sys 0.60.2",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -144,7 +144,7 @@ checksum = "291e6a250ff86cd4a820112fb8898808a366d8f9f58ce16d1f538353ad55747d"
 dependencies = [
  "anstyle",
  "once_cell_polyfill",
- "windows-sys 0.60.2",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -220,9 +220,9 @@ checksum = "d3fb67a6e08acf24fdeccbac2cb6ac4305825bd1f117462e0e6f2f193345ad56"
 
 [[package]]
 name = "arrow"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "61d285d16bce7d0be61912f7928342b673067b6b7d7ef6cc179258ba7de1fecf"
+checksum = "7c14b3d39f306bc28fd639d59f06e17a0f377d0021e1b7e9054e4d6fedc98774"
 dependencies = [
  "arrow-arith",
  "arrow-array",
@@ -241,9 +241,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-arith"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "757ef1836251e88222542a7da2623bc1c9cb9e20afefa6db2c41e79991cd91d4"
+checksum = "ce2961626677665b2195eb59242af4c7befe7b8737ca2050295389362380104e"
 dependencies = [
  "arrow-array",
  "arrow-buffer",
@@ -255,9 +255,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-array"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "bc9a4a4b2b5ecd0e04df03471661cb61f28bed3c7fd50994715129b01b2edb97"
+checksum = "1e5f6adeffdf587d7a31db5d2266189624b526730cd3627f9ff9fedae97ad584"
 dependencies = [
  "ahash",
  "arrow-buffer",
@@ -275,9 +275,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-avro"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "9fb45cd6bd2b25c0965793b83200eaca82214273a8030fbbc2d783e4c7c65a61"
+checksum = "9145b685d586482102e4fe3d40349fe00086c0b219d51cae9daaead4698849ea"
 dependencies = [
  "arrow-array",
  "arrow-buffer",
@@ -299,9 +299,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-buffer"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "c12b576ef18c1deb80925a248b25ad84f419198d791b8e293fc6aaa60441fe90"
+checksum = "097d193003ce7995d5d087089069ec2a6e0187faf5a6f8c9f38af2645d987182"
 dependencies = [
  "bytes",
  "half",
@@ -311,9 +311,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-cast"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "68338a9096a5dc9bc11927c58c43a8526d96bf6abd2012ef6c0c9f505991cc79"
+checksum = "635c9c635668ad26adf76cce8fb276c4be7cf06e63bd516de7da514f9680ee53"
 dependencies = [
  "arrow-array",
  "arrow-buffer",
@@ -333,9 +333,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-csv"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "25011b52b346407d497ef0030e12b45e4f2d0cc279efc09c4f3d09106db30e36"
+checksum = "4c2ebf8d631e79b02c16cf5ae860561272c26024ec88fce389a56aaddd558e86"
 dependencies = [
  "arrow-array",
  "arrow-cast",
@@ -348,9 +348,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-data"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "723fe4aeed7604e00b9883a465af4ff0a0e6c44c03e41a68c3d1cbc403e0e44d"
+checksum = "9ba2f832eaeca24b8f26143dba750e42ee4ab51cf7d65e701ca9607cfda9f358"
 dependencies = [
  "arrow-buffer",
  "arrow-schema",
@@ -361,9 +361,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-flight"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "2bebfacc9d71f0728f6774164e4d4254b5e504d2b46812d0512d8290ec119a64"
+checksum = "be0e6d452fff35cb4a3ef1a719d03fdfe653e590e8012b57d3057a316e295402"
 dependencies = [
  "arrow-arith",
  "arrow-array",
@@ -388,9 +388,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-ipc"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "149437b14371f5b9ec60f5ddc751483ae99d7a7072653c0075e5e469156eea7b"
+checksum = "dcc41681ea80f521df14c36725b74d4c60702c47f0793af2be469c04527e2599"
 dependencies = [
  "arrow-array",
  "arrow-buffer",
@@ -404,9 +404,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-json"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "f18b9123ccfec418a663f821c9a034af339711678c11ffe00d3ec07da5ff9f7e"
+checksum = "a2f57d7a81969f24ccf80809587b76c09897e6f829d2d65a5976bfb3218851f1"
 dependencies = [
  "arrow-array",
  "arrow-buffer",
@@ -429,9 +429,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-ord"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "e6c08dff0686cf23ca4f562803f191ccbeb726dbae6309cd4b4aaf65e0f2c979"
+checksum = "2c900759f3bd8354fd4196bc4403eee846894dc2adf66b4225472006a0bf18c5"
 dependencies = [
  "arrow-array",
  "arrow-buffer",
@@ -442,9 +442,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-pyarrow"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "c196ecc25b3a8dcbc1d842f2619cee653dcfa2fb8b56a291bc0481c3cf5c3821"
+checksum = "801aed7e607dbcc60ed6359025383b27a490327d4282ba87a9a3b78e25959c9a"
 dependencies = [
  "arrow-array",
  "arrow-data",
@@ -454,9 +454,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-row"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "bbec439386df71ad570e6758a946111322b9e9dc8db83b5527321f0b4c9119c2"
+checksum = "f4c6425032e28266e3fc4ff680805e57e670d6ea92473043f3e65b7ed6ac79f2"
 dependencies = [
  "arrow-array",
  "arrow-buffer",
@@ -467,9 +467,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-schema"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "e6fed2ca0d1eade57e811cbe73b98ad50cc08a1183e13b2d2aa43a7df593f40e"
+checksum = "10fab8d4563491417ba801fab29d205104d20d4bdf37bda6cd1cf425cff598cd"
 dependencies = [
  "bitflags 2.13.2",
  "serde",
@@ -479,9 +479,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-select"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "466b19cf75130b891dc1b23a84b343c714c62c64c9c62e365c76aa0ff90a53fb"
+checksum = "fc58569193c2525915f3cc6310edba3792f1200f65d6e9ed330aa33e691493b8"
 dependencies = [
  "ahash",
  "arrow-array",
@@ -493,9 +493,9 @@ dependencies = [
 
 [[package]]
 name = "arrow-string"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "c838a25bb3691e919e0f617616ac51a4ff8517a952e29ca133cf0c22b2ce65b1"
+checksum = "2e0813f3c35c1cfea65e14c20a953440f7783c088b7ad2d0db162ccdeefcec14"
 dependencies = [
  "arrow-array",
  "arrow-buffer",
@@ -542,6 +542,12 @@ dependencies = [
  "tokio",
 ]
 
+[[package]]
+name = "async-ffi"
+version = "0.5.1"
+source = "registry+https://github.com/rust-lang/crates.io-index"
+checksum = "39cd9de47399986d5b216c6bef9434dfff1689ab61ba8d1e2720dc5fe5c84083"
+
 [[package]]
 name = "async-lock"
 version = "3.4.2"
@@ -2372,6 +2378,39 @@ dependencies = [
  "itertools 0.15.0",
 ]
 
+[[package]]
+name = "datafusion-ffi"
+version = "55.1.0"
+source = "registry+https://github.com/rust-lang/crates.io-index"
+checksum = "77a9e527ab3fd2cea1c216efb81c40684a54490489d4ee6cd5719b17f8442f35"
+dependencies = [
+ "arrow",
+ "arrow-schema",
+ "async-ffi",
+ "async-trait",
+ "chrono",
+ "datafusion-catalog",
+ "datafusion-common",
+ "datafusion-datasource",
+ "datafusion-execution",
+ "datafusion-expr",
+ "datafusion-functions-aggregate-common",
+ "datafusion-physical-expr",
+ "datafusion-physical-expr-common",
+ "datafusion-physical-optimizer",
+ "datafusion-physical-plan",
+ "datafusion-proto",
+ "datafusion-proto-common",
+ "datafusion-session",
+ "futures",
+ "libloading 0.9.0",
+ "log",
+ "prost",
+ "semver",
+ "stabby",
+ "tokio",
+]
+
 [[package]]
 name = "datafusion-functions"
 version = "55.1.0"
@@ -2915,7 +2954,7 @@ dependencies = [
  "libc",
  "option-ext",
  "redox_users",
- "windows-sys 0.60.2",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -3081,7 +3120,7 @@ source = "registry+https://github.com/rust-lang/crates.io-index"
 checksum = "39cab71617ae0d63f51a36d69f866391735b51691dbda63cf6f96d042b63efeb"
 dependencies = [
  "libc",
- "windows-sys 0.52.0",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -4599,7 +4638,7 @@ checksum = "3640c1c38b8e4e43584d8df18be5fc6b0aa314ce6ebf51b53313d4306cca8e46"
 dependencies = [
  "hermit-abi",
  "libc",
- "windows-sys 0.52.0",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -5453,7 +5492,7 @@ version = "0.50.3"
 source = "registry+https://github.com/rust-lang/crates.io-index"
 checksum = "7957b9740744892f114936ab4a57b3f487491bbeafaf8083688b16841a4240e5"
 dependencies = [
- "windows-sys 0.60.2",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -5825,9 +5864,9 @@ dependencies = [
 
 [[package]]
 name = "parquet"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "7065842956a20c2a536924ce8e4d9955f7422451511b9eb7500d7bfe5077e59c"
+checksum = "ff322f54b1a0f9288e614ed1f2d329b380af5476420db19f46ffb865e1163d73"
 dependencies = [
  "ahash",
  "arrow-array",
@@ -5859,9 +5898,9 @@ dependencies = [
 
 [[package]]
 name = "parquet-variant"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "3f7e5fff3ed0c07514a7fb8bee3f2ea5a53f36939410ecac4a466620213539a8"
+checksum = "3950502c5d383bc98ac83424c50ad06214cfb8a8554ef6f19413e71894079288"
 dependencies = [
  "arrow",
  "arrow-schema",
@@ -5875,9 +5914,9 @@ dependencies = [
 
 [[package]]
 name = "parquet-variant-compute"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "ba4d3de89dab8d1aaaf601ae8d71bd07ea88cfca9efc1df5815b982c30f631e1"
+checksum = "28c4fc004d60a76d727fe4a383b48e8c4d629384b9d9f0cc359164ec2cbd3326"
 dependencies = [
  "arrow",
  "arrow-schema",
@@ -5892,9 +5931,9 @@ dependencies = [
 
 [[package]]
 name = "parquet-variant-json"
-version = "59.2.0"
+version = "59.3.0"
 source = "registry+https://github.com/rust-lang/crates.io-index"
-checksum = "fb19dfe1bd24c17addd761ba4f7000f615e2fa12525871c7baa835dbb3d7f147"
+checksum = "216b1aecab3ee2e8f429ade4dfef24e233d008ee91ce745fb273c39fc5936b85"
 dependencies = [
  "arrow-schema",
  "base64 0.23.1",
@@ -6728,7 +6767,7 @@ dependencies = [
  "once_cell",
  "socket2",
  "tracing",
- "windows-sys 0.52.0",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -7281,7 +7320,7 @@ dependencies = [
  "errno",
  "libc",
  "linux-raw-sys 0.12.1",
- "windows-sys 0.52.0",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -7615,6 +7654,7 @@ dependencies = [
  "pin-project-lite",
  "prost",
  "sail-common",
+ "sail-native-resource-ffi",
  "serde",
  "serde_arrow",
  "serde_json",
@@ -7935,6 +7975,10 @@ dependencies = [
  "sail-function",
 ]
 
+[[package]]
+name = "sail-native-resource-ffi"
+version = "0.1.0"
+
 [[package]]
 name = "sail-object-store"
 version = "0.7.1"
@@ -8100,18 +8144,23 @@ dependencies = [
 name = "sail-session"
 version = "0.7.1"
 dependencies = [
+ "arrow-schema",
  "async-trait",
  "chrono",
  "datafusion",
  "datafusion-common",
  "datafusion-datasource",
  "datafusion-expr",
+ "datafusion-ffi",
  "datafusion-physical-expr",
  "fastrace",
  "futures",
  "indexmap 2.14.2",
  "log",
  "object_store",
+ "prost",
+ "prost-build",
+ "pyo3",
  "readonly",
  "sail-cache",
  "sail-catalog",
@@ -8138,10 +8187,13 @@ dependencies = [
  "sail-system-store",
  "sail-telemetry",
  "secrecy",
+ "serde",
+ "serde_json",
  "tempfile",
  "thiserror 2.0.20",
  "tokio",
  "tonic",
+ "url",
  "uuid",
 ]
 
@@ -8181,6 +8233,7 @@ dependencies = [
  "sail-telemetry",
  "serde",
  "serde_json",
+ "stacker",
  "syn 2.0.119",
  "thiserror 2.0.20",
  "tokio",
@@ -8437,7 +8490,7 @@ source = "registry+https://github.com/rust-lang/crates.io-index"
 checksum = "5b55fb86dfd3a2f5f76ea78310a88f96c4ea21a3031f8d212443d56123fd0521"
 dependencies = [
  "libc",
- "windows-sys 0.52.0",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -8668,6 +8721,12 @@ dependencies = [
  "digest 0.11.3",
 ]
 
+[[package]]
+name = "sha2-const-stable"
+version = "0.1.0"
+source = "registry+https://github.com/rust-lang/crates.io-index"
+checksum = "5f179d4e11094a893b82fff208f74d448a7512f99f5a0acbd5c679b705f83ed9"
+
 [[package]]
 name = "sharded-slab"
 version = "0.1.7"
@@ -8745,7 +8804,7 @@ source = "registry+https://github.com/rust-lang/crates.io-index"
 checksum = "c3d1e2c7f27f8d4cb10542a02c49005dbd6e93095799d6f3be745fae9f8fedd4"
 dependencies = [
  "libc",
- "windows-sys 0.60.2",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -8818,6 +8877,40 @@ dependencies = [
  "syn 2.0.119",
 ]
 
+[[package]]
+name = "stabby"
+version = "72.1.16"
+source = "registry+https://github.com/rust-lang/crates.io-index"
+checksum = "3d53d2428934c46277fafd2d41e39357595aa1e47954c75db2b14ed90632f3cc"
+dependencies = [
+ "rustversion",
+ "stabby-abi",
+]
+
+[[package]]
+name = "stabby-abi"
+version = "72.1.16"
+source = "registry+https://github.com/rust-lang/crates.io-index"
+checksum = "f375eae680bb54203ee5e47d4cd2ae7b79c0a79ed90919279f38f500ad53f190"
+dependencies = [
+ "rustc_version",
+ "rustversion",
+ "sha2-const-stable",
+ "stabby-macros",
+]
+
+[[package]]
+name = "stabby-macros"
+version = "72.1.16"
+source = "registry+https://github.com/rust-lang/crates.io-index"
+checksum = "ea664671a576c5f7e32fee291ac123d82af5e92b0689beb3555347c00c76eef1"
+dependencies = [
+ "proc-macro-crate",
+ "proc-macro2",
+ "quote",
+ "syn 2.0.119",
+]
+
 [[package]]
 name = "stable_deref_trait"
 version = "1.2.1"
@@ -8834,7 +8927,7 @@ dependencies = [
  "cfg-if",
  "libc",
  "psm",
- "windows-sys 0.60.2",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -8998,10 +9091,10 @@ source = "registry+https://github.com/rust-lang/crates.io-index"
 checksum = "32497e9a4c7b38532efcdebeef879707aa9f794296a4f0244f6f69e9bc8574bd"
 dependencies = [
  "fastrand",
- "getrandom 0.3.4",
+ "getrandom 0.4.3",
  "once_cell",
  "rustix 1.1.4",
- "windows-sys 0.52.0",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
@@ -9542,7 +9635,7 @@ version = "2.1.4"
 source = "registry+https://github.com/rust-lang/crates.io-index"
 checksum = "5283634e518fe9e82c7b20520bb4bc209009fd16c82077c802f8111ecbb0117a"
 dependencies = [
- "rand 0.9.5",
+ "rand 0.10.3",
 ]
 
 [[package]]
@@ -9997,7 +10090,7 @@ version = "0.1.11"
 source = "registry+https://github.com/rust-lang/crates.io-index"
 checksum = "c2a7b1c03c876122aa43f3020e6c3c3ee5c05081c9a00739faf7503aeba10d22"
 dependencies = [
- "windows-sys 0.52.0",
+ "windows-sys 0.61.2",
 ]
 
 [[package]]
```

## 02. Cargo.toml {#host-patch-02}

```diff
diff --git a/Cargo.toml b/Cargo.toml
index b2865f9af30d792109e9b2d91bfe8c803c15ba79..bc6e5aff18d50475eaa55ae64597da8f11a69efa 100644
--- a/Cargo.toml
+++ b/Cargo.toml
@@ -23,6 +23,7 @@ dbg_macro = "deny"
 todo = "deny"
 
 [workspace.dependencies]
+stacker = "0.1.25"
 thiserror = { version = "2.0.18" }
 tokio = { version = "1.52.3", features = ["full"] }
 tokio-util = { version = "0.7.19", features = ["rt"] }
@@ -162,7 +163,7 @@ prost-types = "0.14"
 # The `axum` version must match the one used in `tonic` (replace `RELEASE` with the release we are using):
 #   https://github.com/hyperium/tonic/blob/vRELEASE/tonic/Cargo.toml
 axum = "0.8.9"
-datafusion = { version = "55.1.0", default-features = false, features = [
+datafusion = { version = "=55.1.0", default-features = false, features = [
     "nested_expressions",
     "crypto_expressions",
     "datetime_expressions",
@@ -176,32 +177,33 @@ datafusion = { version = "55.1.0", default-features = false, features = [
     "avro",
     "recursive_protection",
 ] }
-datafusion-common = { version = "55.1.0", features = ["object_store"] }
-datafusion-datasource = { version = "55.1.0" }
-datafusion-datasource-avro = { version = "55.1.0" }
-datafusion-datasource-json = { version = "55.1.0" }
-datafusion-datasource-parquet = { version = "55.1.0" }
-datafusion-expr = { version = "55.1.0", default-features = false }
-datafusion-expr-common = { version = "55.1.0" }
-datafusion-proto = { version = "55.1.0" }
-datafusion-functions = { version = "55.1.0" }
-datafusion-functions-nested = { version = "55.1.0", default-features = false }
-datafusion-physical-expr = { version = "55.1.0" }
-datafusion-session = { version = "55.1.0" }
-datafusion-spark = { version = "55.1.0", features = ["core"] }
+datafusion-common = { version = "=55.1.0", features = ["object_store"] }
+datafusion-datasource = { version = "=55.1.0" }
+datafusion-datasource-avro = { version = "=55.1.0" }
+datafusion-datasource-json = { version = "=55.1.0" }
+datafusion-datasource-parquet = { version = "=55.1.0" }
+datafusion-expr = { version = "=55.1.0", default-features = false }
+datafusion-expr-common = { version = "=55.1.0" }
+datafusion-ffi = { version = "=55.1.0" }
+datafusion-proto = { version = "=55.1.0" }
+datafusion-functions = { version = "=55.1.0" }
+datafusion-functions-nested = { version = "=55.1.0", default-features = false }
+datafusion-physical-expr = { version = "=55.1.0" }
+datafusion-session = { version = "=55.1.0" }
+datafusion-spark = { version = "=55.1.0", features = ["core"] }
 pyo3 = { version = "0.29.0", features = ["serde"] }
 jiter = { version = "0.15.0", default-features = false }
-arrow = { version = "59.2.0", features = ["chrono-tz"] }
-arrow-array = { version = "59.2.0", features = ["ffi"] }
-arrow-buffer = { version = "59.2.0" }
-arrow-data = { version = "59.2.0" }
-arrow-schema = { version = "59.2.0", features = ["serde"] }
-arrow-flight = { version = "59.2.0", features = ["flight-sql-experimental"] }
-arrow-pyarrow = { version = "59.2.0" }
-parquet = { version = "59.2.0" }
-parquet-variant = { version = "59.2.0" }
-parquet-variant-compute = { version = "59.2.0" }
-parquet-variant-json = { version = "59.2.0" }
+arrow = { version = "=59.3.0", features = ["chrono-tz"] }
+arrow-array = { version = "=59.3.0", features = ["ffi"] }
+arrow-buffer = { version = "=59.3.0" }
+arrow-data = { version = "=59.3.0" }
+arrow-schema = { version = "=59.3.0", features = ["serde"] }
+arrow-flight = { version = "=59.3.0", features = ["flight-sql-experimental"] }
+arrow-pyarrow = { version = "=59.3.0" }
+parquet = { version = "=59.3.0" }
+parquet-variant = { version = "=59.3.0" }
+parquet-variant-compute = { version = "=59.3.0" }
+parquet-variant-json = { version = "=59.3.0" }
 serde_arrow = { version = "0.14.2", features = ["arrow-59"] }
 # The `object_store` version must match the one used in DataFusion.
 object_store = { version = "0.13.2", features = ["aws", "gcp", "azure", "http"] }
```

## 03. crates/sail-common-datafusion/Cargo.toml {#host-patch-03}

```diff
diff --git a/crates/sail-common-datafusion/Cargo.toml b/crates/sail-common-datafusion/Cargo.toml
index 3e5373a5690077a161d2221d8b81fddca9618ed1..85c1fd71a06c7d21ab228c91920591f2c7349f5e 100644
--- a/crates/sail-common-datafusion/Cargo.toml
+++ b/crates/sail-common-datafusion/Cargo.toml
@@ -8,6 +8,7 @@ workspace = true
 
 [dependencies]
 sail-common = { path = "../sail-common" }
+sail-native-resource-ffi = { path = "../sail-native-resource-ffi" }
 
 chrono = { workspace = true }
 datafusion = { workspace = true }
```

## 04. crates/sail-common-datafusion/src/connect_extension.rs {#host-patch-04}

```diff
diff --git a/crates/sail-common-datafusion/src/connect_extension.rs b/crates/sail-common-datafusion/src/connect_extension.rs
new file mode 100644
index 0000000000000000000000000000000000000000..89941ca59257ee97f667f7443a1a9b8bb0f1106a
--- /dev/null
+++ b/crates/sail-common-datafusion/src/connect_extension.rs
@@ -0,0 +1,257 @@
+//! Internal host adapters for the experimental local Connect extension API.
+//!
+//! This Rust interface stays inside Sail. Native packages cross the independently
+//! version-checked DataFusion FFI boundary in the package loader, not this trait.
+
+use std::collections::BTreeMap;
+use std::fmt::{Debug, Formatter};
+use std::pin::Pin;
+use std::sync::Arc;
+use std::task::{Context, Poll};
+
+use datafusion::arrow::datatypes::SchemaRef;
+use datafusion::arrow::record_batch::RecordBatch;
+use datafusion::catalog::TableProvider;
+use datafusion::execution::{RecordBatchStream, SendableRecordBatchStream, TaskContext};
+use datafusion::physical_expr::PhysicalExpr;
+use datafusion::physical_plan::coalesce_partitions::CoalescePartitionsExec;
+use datafusion::physical_plan::{
+    DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties, ReplaceChildrenOptions,
+};
+use datafusion_common::tree_node::TreeNodeRecursion;
+use datafusion_common::{Result, exec_err, plan_err};
+use futures::Stream;
+use tokio::runtime::Handle;
+
+use crate::extension::SessionExtension;
+
+/// Planning must only describe execution: it must not consume input or mutate
+/// extension state. AnalyzePlan can invoke this method without executing a query.
+pub trait ConnectRelationHandler: Send + Sync + 'static {
+    fn plan(
+        &self,
+        payload: &[u8],
+        inputs: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn TableProvider>>;
+}
+
+struct RegisteredHandler {
+    accepts_bare: bool,
+    min_inputs: usize,
+    max_inputs: usize,
+    handler: Arc<dyn ConnectRelationHandler>,
+}
+
+/// One registry is bound to one server session. Package discovery may be shared;
+/// handlers and the graph state they own must be instantiated for this session.
+#[derive(Default)]
+pub struct ConnectExtensionRegistry {
+    handlers: BTreeMap<String, RegisteredHandler>,
+}
+
+impl ConnectExtensionRegistry {
+    pub fn new() -> Self {
+        Self::default()
+    }
+
+    pub fn register(
+        &mut self,
+        type_url: String,
+        accepts_bare: bool,
+        min_inputs: usize,
+        max_inputs: usize,
+        handler: Arc<dyn ConnectRelationHandler>,
+    ) -> Result<()> {
+        if type_url.is_empty() || type_url.len() > 512 {
+            return plan_err!("extension type URL must contain between 1 and 512 bytes");
+        }
+        if min_inputs > max_inputs || (accepts_bare && min_inputs != 0) {
+            return plan_err!("invalid input arity registration for extension {type_url}");
+        }
+        if self.handlers.contains_key(&type_url) {
+            return plan_err!("duplicate Connect extension type URL: {type_url}");
+        }
+        self.handlers.insert(
+            type_url,
+            RegisteredHandler {
+                accepts_bare,
+                min_inputs,
+                max_inputs,
+                handler,
+            },
+        );
+        Ok(())
+    }
+
+    /// Validate before planning children, so invalid requests cannot trigger
+    /// planning callbacks in their nested extensions.
+    pub fn resolve(
+        &self,
+        type_url: &str,
+        is_envelope: bool,
+        input_count: usize,
+    ) -> Result<Arc<dyn ConnectRelationHandler>> {
+        let Some(entry) = self.handlers.get(type_url) else {
+            let registered = self.handlers.keys().cloned().collect::<Vec<_>>().join(", ");
+            return plan_err!(
+                "unregistered Connect extension type URL: {type_url}; registered: [{registered}]"
+            );
+        };
+        if !is_envelope && !entry.accepts_bare {
+            return plan_err!(
+                "Connect extension {type_url} requires a SailExtensionRequest envelope"
+            );
+        }
+        if !is_envelope && input_count != 0 {
+            return plan_err!("bare Connect extension {type_url} cannot have inputs");
+        }
+        if !(entry.min_inputs..=entry.max_inputs).contains(&input_count) {
+            return plan_err!(
+                "Connect extension {type_url} expects {}..={} inputs, received {input_count}",
+                entry.min_inputs,
+                entry.max_inputs
+            );
+        }
+        Ok(Arc::clone(&entry.handler))
+    }
+}
+
+impl SessionExtension for ConnectExtensionRegistry {
+    fn name() -> &'static str {
+        "ConnectExtensionRegistry"
+    }
+}
+
+/// Executes a previously planned Sail input under its original host context.
+///
+/// DataFusion 55's foreign TaskContext reconstruction does not preserve Sail's
+/// RuntimeEnv. A foreign consumer therefore receives this wrapper, whose execute
+/// ignores the reconstructed context. Coalescing happens on the host and consumes
+/// every partition. The host runtime is retained and entered for execution and
+/// stream polls: FFI child replacement can discard the FFI wrapper's runtime.
+/// This is a local-mode bridge, not a serializable remote node.
+pub struct HostInputExec {
+    input: Arc<dyn ExecutionPlan>,
+    context: Arc<TaskContext>,
+    runtime: Handle,
+}
+
+impl HostInputExec {
+    pub fn gathered_input(&self) -> Arc<dyn ExecutionPlan> {
+        self.input.clone()
+    }
+
+    pub fn new(input: Arc<dyn ExecutionPlan>, context: Arc<TaskContext>, runtime: Handle) -> Self {
+        Self {
+            input: Arc::new(CoalescePartitionsExec::new(input)),
+            context,
+            runtime,
+        }
+    }
+}
+
+impl Debug for HostInputExec {
+    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
+        f.debug_struct("HostInputExec")
+            .field("input", &self.input)
+            .finish_non_exhaustive()
+    }
+}
+
+impl DisplayAs for HostInputExec {
+    fn fmt_as(&self, _t: DisplayFormatType, f: &mut Formatter<'_>) -> std::fmt::Result {
+        write!(
+            f,
+            "HostInputExec: local, host_context=true, host_runtime=true, partitions=1"
+        )
+    }
+}
+
+impl ExecutionPlan for HostInputExec {
+    fn name(&self) -> &'static str {
+        "HostInputExec"
+    }
+
+    fn properties(&self) -> &Arc<PlanProperties> {
+        self.input.properties()
+    }
+
+    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
+        vec![&self.input]
+    }
+
+    fn apply_expressions(
+        &self,
+        _f: &mut dyn FnMut(&Arc<dyn PhysicalExpr>) -> Result<TreeNodeRecursion>,
+    ) -> Result<TreeNodeRecursion> {
+        Ok(TreeNodeRecursion::Continue)
+    }
+
+    #[expect(deprecated)]
+    fn replace_children(
+        self: Arc<Self>,
+        children: Vec<Arc<dyn ExecutionPlan>>,
+        _options: ReplaceChildrenOptions,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        self.with_new_children(children)
+    }
+
+    fn with_new_children(
+        self: Arc<Self>,
+        mut children: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        if children.len() != 1 {
+            return plan_err!("HostInputExec requires exactly one child");
+        }
+        if children[0].schema() != self.input.schema() {
+            return plan_err!("HostInputExec replacement child has a different schema");
+        }
+        // Re-establish the single-partition contract even after foreign child
+        // replacement, which cannot carry required_input_distribution over FFI.
+        Ok(Arc::new(Self::new(
+            children.remove(0),
+            Arc::clone(&self.context),
+            self.runtime.clone(),
+        )))
+    }
+
+    fn execute(
+        &self,
+        partition: usize,
+        _foreign_context: Arc<TaskContext>,
+    ) -> Result<SendableRecordBatchStream> {
+        if partition != 0 {
+            return exec_err!("HostInputExec only supports partition 0, received {partition}");
+        }
+        let _guard = self.runtime.enter();
+        let inner = self.input.execute(0, Arc::clone(&self.context))?;
+        Ok(Box::pin(HostInputStream {
+            inner,
+            runtime: self.runtime.clone(),
+        }))
+    }
+}
+
+struct HostInputStream {
+    inner: SendableRecordBatchStream,
+    runtime: Handle,
+}
+
+impl Stream for HostInputStream {
+    type Item = Result<RecordBatch>;
+
+    fn poll_next(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Option<Self::Item>> {
+        let this = self.get_mut();
+        let _guard = this.runtime.enter();
+        this.inner.as_mut().poll_next(cx)
+    }
+}
+
+impl RecordBatchStream for HostInputStream {
+    fn schema(&self) -> SchemaRef {
+        self.inner.schema()
+    }
+}
+
+#[cfg(test)]
+mod tests;
```

## 05. crates/sail-common-datafusion/src/connect_extension/tests.rs {#host-patch-05}

```diff
diff --git a/crates/sail-common-datafusion/src/connect_extension/tests.rs b/crates/sail-common-datafusion/src/connect_extension/tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..6998511ae8d125cd3b58c4b4b4d0ad1159445214
--- /dev/null
+++ b/crates/sail-common-datafusion/src/connect_extension/tests.rs
@@ -0,0 +1,226 @@
+use std::sync::atomic::{AtomicUsize, Ordering};
+
+use datafusion::arrow::array::Int64Array;
+use datafusion::arrow::datatypes::{DataType, Field, Schema};
+use datafusion::arrow::record_batch::RecordBatch;
+use datafusion::datasource::empty::EmptyTable;
+use datafusion::physical_expr::{EquivalenceProperties, Partitioning};
+use datafusion::physical_plan::common::collect;
+use datafusion::physical_plan::execution_plan::{Boundedness, EmissionType};
+use datafusion::physical_plan::stream::RecordBatchStreamAdapter;
+use datafusion::prelude::SessionContext;
+
+use super::*;
+
+struct EmptyHandler;
+
+impl ConnectRelationHandler for EmptyHandler {
+    fn plan(
+        &self,
+        _payload: &[u8],
+        _inputs: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn TableProvider>> {
+        Ok(Arc::new(EmptyTable::new(Arc::new(Schema::empty()))))
+    }
+}
+
+#[test]
+fn registry_refuses_collisions_unknown_urls_and_invalid_shapes() -> Result<()> {
+    let mut registry = ConnectExtensionRegistry::new();
+    registry.register(
+        "type.test/Stage".into(),
+        false,
+        2,
+        2,
+        Arc::new(EmptyHandler),
+    )?;
+    registry.register("type.test/Read".into(), true, 0, 0, Arc::new(EmptyHandler))?;
+    assert!(registry.resolve("type.test/Stage", true, 2).is_ok());
+    assert!(registry.resolve("type.test/Read", false, 0).is_ok());
+    assert!(matches!(
+        registry.resolve("type.test/Stage", false, 0),
+        Err(e) if e.to_string().contains("Stage requires a SailExtensionRequest envelope")
+    ));
+    assert!(matches!(
+        registry.resolve("type.test/Stage", true, 1),
+        Err(e) if e.to_string().contains("expects 2..=2 inputs, received 1")
+    ));
+    assert!(matches!(
+        registry.resolve("type.test/Missing", true, 0),
+        Err(e) if e.to_string().contains("type.test/Missing")
+            && e.to_string().contains("[type.test/Read, type.test/Stage]")
+    ));
+    assert!(matches!(
+        registry.register("type.test/Stage".into(), true, 0, 0, Arc::new(EmptyHandler)),
+        Err(e) if e.to_string().contains("duplicate")
+    ));
+    // A failed duplicate registration leaves the original contract intact.
+    assert!(registry.resolve("type.test/Stage", true, 2).is_ok());
+    assert!(registry.resolve("type.test/Stage", true, 0).is_err());
+    assert!(
+        registry
+            .register("type.test/Bad".into(), true, 1, 1, Arc::new(EmptyHandler))
+            .is_err()
+    );
+    Ok(())
+}
+
+struct ContextProbeExec {
+    expected: Arc<TaskContext>,
+    properties: Arc<PlanProperties>,
+    executions: Arc<AtomicUsize>,
+    runtime: tokio::runtime::Id,
+}
+
+impl Debug for ContextProbeExec {
+    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
+        write!(f, "ContextProbeExec")
+    }
+}
+
+impl DisplayAs for ContextProbeExec {
+    fn fmt_as(&self, _t: DisplayFormatType, f: &mut Formatter<'_>) -> std::fmt::Result {
+        write!(f, "ContextProbeExec")
+    }
+}
+
+impl ExecutionPlan for ContextProbeExec {
+    fn name(&self) -> &'static str {
+        "ContextProbeExec"
+    }
+
+    fn properties(&self) -> &Arc<PlanProperties> {
+        &self.properties
+    }
+
+    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
+        vec![]
+    }
+
+    fn apply_expressions(
+        &self,
+        _f: &mut dyn FnMut(&Arc<dyn PhysicalExpr>) -> Result<TreeNodeRecursion>,
+    ) -> Result<TreeNodeRecursion> {
+        Ok(TreeNodeRecursion::Continue)
+    }
+
+    fn with_new_children(
+        self: Arc<Self>,
+        children: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        if !children.is_empty() {
+            return plan_err!("ContextProbeExec has no children");
+        }
+        Ok(self)
+    }
+
+    fn execute(
+        &self,
+        partition: usize,
+        context: Arc<TaskContext>,
+    ) -> Result<SendableRecordBatchStream> {
+        if !Arc::ptr_eq(&context, &self.expected) {
+            return exec_err!("Sail input received a foreign task context");
+        }
+        assert_eq!(Handle::current().id(), self.runtime);
+        self.executions.fetch_add(1, Ordering::SeqCst);
+        let values = match partition {
+            0 => vec![10, 20],
+            1 => vec![],
+            2 => vec![30],
+            _ => return exec_err!("unexpected partition {partition}"),
+        };
+        let batch = RecordBatch::try_new(self.schema(), vec![Arc::new(Int64Array::from(values))])?;
+        let runtime = self.runtime;
+        Ok(Box::pin(RecordBatchStreamAdapter::new(
+            self.schema(),
+            futures::stream::once(async move {
+                assert_eq!(Handle::current().id(), runtime);
+                // Constructing a timer needs the correct reactor at poll time,
+                // even when the caller is an ordinary foreign worker thread.
+                tokio::time::sleep(std::time::Duration::from_millis(1)).await;
+                Ok(batch)
+            }),
+        )))
+    }
+}
+
+#[tokio::test]
+async fn host_input_is_lazy_consumes_every_partition_and_preserves_context_after_replacement()
+-> Result<()> {
+    let host = SessionContext::new().task_ctx();
+    let foreign = SessionContext::new().task_ctx();
+    let executions = Arc::new(AtomicUsize::new(0));
+    let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)]));
+    let probe = Arc::new(ContextProbeExec {
+        expected: Arc::clone(&host),
+        properties: Arc::new(PlanProperties::new(
+            EquivalenceProperties::new(schema),
+            Partitioning::UnknownPartitioning(3),
+            EmissionType::Incremental,
+            Boundedness::Bounded,
+        )),
+        executions: Arc::clone(&executions),
+        runtime: Handle::current().id(),
+    });
+    let input = Arc::new(HostInputExec::new(probe.clone(), host, Handle::current()));
+    assert_eq!(executions.load(Ordering::SeqCst), 0);
+    assert!(input.execute(1, Arc::clone(&foreign)).is_err());
+    let batches = collect(input.execute(0, Arc::clone(&foreign))?).await?;
+    assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 3);
+    assert_eq!(executions.load(Ordering::SeqCst), 3);
+
+    #[expect(deprecated)]
+    let replaced = input.with_new_children(vec![probe])?;
+    let batches = collect(replaced.execute(0, foreign)?).await?;
+    assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 3);
+    assert_eq!(executions.load(Ordering::SeqCst), 6);
+    Ok(())
+}
+
+#[test]
+fn host_input_preserves_runtime_when_replaced_and_polled_on_a_foreign_thread() -> Result<()> {
+    let runtime = tokio::runtime::Builder::new_multi_thread()
+        .worker_threads(2)
+        .enable_all()
+        .build()?;
+    let host = SessionContext::new().task_ctx();
+    let foreign = SessionContext::new().task_ctx();
+    let executions = Arc::new(AtomicUsize::new(0));
+    let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)]));
+    let probe = Arc::new(ContextProbeExec {
+        expected: Arc::clone(&host),
+        properties: Arc::new(PlanProperties::new(
+            EquivalenceProperties::new(schema),
+            Partitioning::UnknownPartitioning(1),
+            EmissionType::Incremental,
+            Boundedness::Bounded,
+        )),
+        executions: Arc::clone(&executions),
+        runtime: runtime.handle().id(),
+    });
+    let input = Arc::new(HostInputExec::new(
+        probe.clone(),
+        host,
+        runtime.handle().clone(),
+    ));
+    // The single-partition coalescer delegates its stream directly. Thus this
+    // tests the wrapper's poll guard itself, without a Tokio task hiding it.
+    std::thread::spawn(move || -> Result<()> {
+        assert!(Handle::try_current().is_err());
+        let batches =
+            futures::executor::block_on(collect(input.execute(0, Arc::clone(&foreign))?))?;
+        assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 2);
+        assert!(Handle::try_current().is_err());
+        #[expect(deprecated)]
+        let replaced = input.with_new_children(vec![probe])?;
+        let batches = futures::executor::block_on(collect(replaced.execute(0, foreign)?))?;
+        assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 2);
+        assert!(Handle::try_current().is_err());
+        Ok(())
+    })
+    .join()
+    .map_err(|_| datafusion_common::internal_datafusion_err!("foreign thread panicked"))??;
+    assert_eq!(executions.load(Ordering::SeqCst), 2);
+    Ok(())
+}
```

## 06. crates/sail-common-datafusion/src/driver_extension.rs {#host-patch-06}

```diff
diff --git a/crates/sail-common-datafusion/src/driver_extension.rs b/crates/sail-common-datafusion/src/driver_extension.rs
new file mode 100644
index 0000000000000000000000000000000000000000..15fa21a959416f1a6b9d96473ad52ddffacf00cf
--- /dev/null
+++ b/crates/sail-common-datafusion/src/driver_extension.rs
@@ -0,0 +1,210 @@
+//! Session-owned native regions placed on the driver in a distributed job.
+use std::collections::HashMap;
+use std::fmt::{Debug, Formatter};
+use std::sync::{Arc, Mutex, Weak};
+
+use datafusion::execution::{SendableRecordBatchStream, TaskContext};
+use datafusion::physical_plan::{DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties};
+use datafusion_common::{Result, plan_datafusion_err, plan_err};
+use serde::{Deserialize, Serialize};
+
+use crate::extension::{SessionExtension, SessionExtensionAccessor};
+
+pub const DRIVER_CODEC_PREFIX: &[u8] = b"SAIL_DRIVER_EXTENSION_V1\0";
+
+/// A frozen native plan, including its graph revision or mutation attempt state.
+/// Only its declared host inputs are substituted during task preparation.
+pub trait DriverExtensionBinding: Debug + Send + Sync {
+    /// Release native snapshots after query completion/cancellation. Streams
+    /// already executing own their materialized plans until they are dropped.
+    fn close(&self) {}
+    fn materialize(
+        &self,
+        inputs: &[Arc<dyn ExecutionPlan>],
+        context: Arc<TaskContext>,
+    ) -> Result<Arc<dyn ExecutionPlan>>;
+}
+
+#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
+#[serde(deny_unknown_fields)]
+pub struct DriverDescriptor {
+    pub owner: String,
+    pub plan_id: String,
+}
+
+#[derive(Debug)]
+pub struct BoundDriverPlan {
+    pub descriptor: DriverDescriptor,
+    pub properties: Arc<PlanProperties>,
+    pub input_schemas: Vec<arrow_schema::SchemaRef>,
+    pub binding: Arc<dyn DriverExtensionBinding>,
+}
+
+/// Weak entries do not extend graph snapshots beyond the lifetime of a query.
+/// The job graph owns each live bound plan while its tasks can be decoded.
+#[derive(Debug, Default)]
+pub struct DriverExtensionRegistry(Mutex<HashMap<String, Weak<BoundDriverPlan>>>);
+
+impl SessionExtension for DriverExtensionRegistry {
+    fn name() -> &'static str {
+        "DriverExtensionRegistry"
+    }
+}
+
+impl DriverExtensionRegistry {
+    pub fn register(&self, plan: &Arc<BoundDriverPlan>) -> Result<()> {
+        let mut entries = self
+            .0
+            .lock()
+            .map_err(|_| plan_datafusion_err!("driver extension registry poisoned"))?;
+        entries.retain(|_, value| value.strong_count() > 0);
+        if entries.contains_key(&plan.descriptor.plan_id) {
+            return plan_err!("duplicate driver extension plan identity");
+        }
+        entries.insert(plan.descriptor.plan_id.clone(), Arc::downgrade(plan));
+        Ok(())
+    }
+
+    fn lookup(&self, descriptor: &DriverDescriptor) -> Result<Arc<BoundDriverPlan>> {
+        let entries = self
+            .0
+            .lock()
+            .map_err(|_| plan_datafusion_err!("driver extension registry poisoned"))?;
+        let plan = entries
+            .get(&descriptor.plan_id)
+            .and_then(Weak::upgrade)
+            .ok_or_else(|| {
+                plan_datafusion_err!(
+                    "driver extension plan is unavailable in this session or has expired"
+                )
+            })?;
+        if plan.descriptor != *descriptor {
+            return plan_err!("driver extension owner mismatch");
+        }
+        Ok(plan)
+    }
+}
+
+#[derive(Debug)]
+pub struct DriverExtensionExec {
+    pub bound: Arc<BoundDriverPlan>,
+    inputs: Vec<Arc<dyn ExecutionPlan>>,
+}
+
+impl DriverExtensionExec {
+    pub fn new(bound: Arc<BoundDriverPlan>, inputs: Vec<Arc<dyn ExecutionPlan>>) -> Result<Self> {
+        if inputs.len() != bound.input_schemas.len()
+            || inputs
+                .iter()
+                .zip(&bound.input_schemas)
+                .any(|(input, schema)| input.schema() != *schema)
+        {
+            return plan_err!("driver extension input arity/schema mismatch");
+        }
+        Ok(Self { bound, inputs })
+    }
+
+    pub fn encode(&self, buffer: &mut Vec<u8>) -> Result<()> {
+        buffer.extend_from_slice(DRIVER_CODEC_PREFIX);
+        serde_json::to_writer(buffer, &self.bound.descriptor)
+            .map_err(|e| plan_datafusion_err!("driver extension descriptor: {e}"))
+    }
+
+    pub fn decode(
+        buffer: &[u8],
+        inputs: &[Arc<dyn ExecutionPlan>],
+        context: &TaskContext,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        if buffer.len() > 8192 {
+            return plan_err!("driver extension descriptor exceeds 8192 bytes");
+        }
+        let payload = buffer
+            .strip_prefix(DRIVER_CODEC_PREFIX)
+            .ok_or_else(|| plan_datafusion_err!("unknown driver extension codec owner/version"))?;
+        let descriptor: DriverDescriptor = serde_json::from_slice(payload)
+            .map_err(|e| plan_datafusion_err!("driver extension descriptor: {e}"))?;
+        let registry = context
+            .extension::<DriverExtensionRegistry>()
+            .map_err(|_| {
+                plan_datafusion_err!("driver-only extension cannot be decoded on a worker")
+            })?;
+        Ok(Arc::new(Self::new(
+            registry.lookup(&descriptor)?,
+            inputs.to_vec(),
+        )?))
+    }
+}
+
+impl DisplayAs for DriverExtensionExec {
+    fn fmt_as(&self, _: DisplayFormatType, f: &mut Formatter<'_>) -> std::fmt::Result {
+        write!(
+            f,
+            "DriverExtensionExec: owner={}, plan={}, placement=driver, retry=disabled",
+            self.bound.descriptor.owner, self.bound.descriptor.plan_id
+        )
+    }
+}
+
+impl ExecutionPlan for DriverExtensionExec {
+    fn apply_expressions(
+        &self,
+        _f: &mut dyn FnMut(
+            &Arc<dyn datafusion::physical_expr::PhysicalExpr>,
+        ) -> Result<datafusion_common::tree_node::TreeNodeRecursion>,
+    ) -> Result<datafusion_common::tree_node::TreeNodeRecursion> {
+        Ok(datafusion_common::tree_node::TreeNodeRecursion::Continue)
+    }
+    fn name(&self) -> &str {
+        "DriverExtensionExec"
+    }
+    fn properties(&self) -> &Arc<PlanProperties> {
+        &self.bound.properties
+    }
+    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
+        self.inputs.iter().collect()
+    }
+    fn required_input_distribution(&self) -> Vec<datafusion::physical_expr::Distribution> {
+        vec![datafusion::physical_expr::Distribution::SinglePartition; self.inputs.len()]
+    }
+    fn with_new_children(
+        self: Arc<Self>,
+        children: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        Ok(Arc::new(Self::new(self.bound.clone(), children)?))
+    }
+    fn execute(
+        &self,
+        partition: usize,
+        context: Arc<TaskContext>,
+    ) -> Result<SendableRecordBatchStream> {
+        if partition != 0
+            || self
+                .inputs
+                .iter()
+                .any(|input| input.properties().partitioning.partition_count() != 1)
+        {
+            return plan_err!("driver extension requires one output partition and gathered inputs");
+        }
+        let plan = self
+            .bound
+            .binding
+            .materialize(&self.inputs, context.clone())?;
+        plan.execute(0, context)
+    }
+}
+
+pub fn contains_driver_extension(plan: &Arc<dyn ExecutionPlan>) -> bool {
+    plan.is::<DriverExtensionExec>() || plan.children().into_iter().any(contains_driver_extension)
+}
+
+pub fn release_driver_extensions(plan: &Arc<dyn ExecutionPlan>) {
+    if let Some(native) = plan.downcast_ref::<DriverExtensionExec>() {
+        native.bound.binding.close();
+    }
+    for child in plan.children() {
+        release_driver_extensions(child);
+    }
+}
+
+#[cfg(test)]
+mod tests;
```

## 07. crates/sail-common-datafusion/src/driver_extension/tests.rs {#host-patch-07}

```diff
diff --git a/crates/sail-common-datafusion/src/driver_extension/tests.rs b/crates/sail-common-datafusion/src/driver_extension/tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..c5e7a7c0d9e02f84e394241a003818245a6d6c0f
--- /dev/null
+++ b/crates/sail-common-datafusion/src/driver_extension/tests.rs
@@ -0,0 +1,64 @@
+use datafusion::physical_plan::empty::EmptyExec;
+use datafusion::prelude::{SessionConfig, SessionContext};
+
+use super::*;
+
+#[derive(Debug)]
+struct Binding(Arc<dyn ExecutionPlan>);
+impl DriverExtensionBinding for Binding {
+    fn materialize(
+        &self,
+        _: &[Arc<dyn ExecutionPlan>],
+        _: Arc<TaskContext>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        Ok(self.0.clone())
+    }
+}
+
+#[test]
+fn driver_extension_codec_binds_only_live_plans_in_the_original_session() -> Result<()> {
+    let registry = Arc::new(DriverExtensionRegistry::default());
+    let context =
+        SessionContext::new_with_config(SessionConfig::new().with_extension(registry.clone()))
+            .task_ctx();
+    let empty: Arc<dyn ExecutionPlan> =
+        Arc::new(EmptyExec::new(Arc::new(arrow_schema::Schema::empty())));
+    let bound = Arc::new(BoundDriverPlan {
+        descriptor: DriverDescriptor {
+            owner: "fixture@1:digest".into(),
+            plan_id: "incarnation:operation".into(),
+        },
+        properties: empty.properties().clone(),
+        input_schemas: vec![],
+        binding: Arc::new(Binding(empty.clone())),
+    });
+    registry.register(&bound)?;
+    let exec = DriverExtensionExec::new(bound.clone(), vec![])?;
+    let mut bytes = vec![];
+    exec.encode(&mut bytes)?;
+    let decoded = DriverExtensionExec::decode(&bytes, &[], &context)?;
+    assert_eq!(decoded.name(), "DriverExtensionExec");
+    assert!(DriverExtensionExec::decode(&bytes, &[empty], &context).is_err());
+    assert!(DriverExtensionExec::decode(&bytes, &[], &TaskContext::default()).is_err());
+    let other = SessionContext::new_with_config(
+        SessionConfig::new().with_extension(Arc::new(DriverExtensionRegistry::default())),
+    )
+    .task_ctx();
+    assert!(DriverExtensionExec::decode(&bytes, &[], &other).is_err());
+    let mut forged = DRIVER_CODEC_PREFIX.to_vec();
+    serde_json::to_writer(
+        &mut forged,
+        &DriverDescriptor {
+            owner: "other".into(),
+            plan_id: bound.descriptor.plan_id.clone(),
+        },
+    )
+    .map_err(|e| plan_datafusion_err!("{e}"))?;
+    assert!(DriverExtensionExec::decode(&forged, &[], &context).is_err());
+    drop(decoded);
+    drop(exec);
+    drop(bound);
+    assert!(DriverExtensionExec::decode(&bytes, &[], &context).is_err());
+    assert!(DriverExtensionExec::decode(&vec![0; 8193], &[], &context).is_err());
+    Ok(())
+}
```

## 08. crates/sail-common-datafusion/src/geometry.rs {#host-patch-08}

```diff
diff --git a/crates/sail-common-datafusion/src/geometry.rs b/crates/sail-common-datafusion/src/geometry.rs
new file mode 100644
index 0000000000000000000000000000000000000000..86b06c1b723b2d53cc8c1da667499964ace75fe2
--- /dev/null
+++ b/crates/sail-common-datafusion/src/geometry.rs
@@ -0,0 +1,65 @@
+//! Conservative propagation of GeoArrow logical types through value selectors.
+use std::collections::HashMap;
+
+use arrow_schema::{DataType, FieldRef};
+
+/// Preserve a geometry type only when every non-NULL alternative has the same
+/// storage type and GeoArrow extension metadata. Plain binary is not geometry;
+/// neither mixed CRS nor geometry/geography alternatives may be relabelled.
+pub fn common_geometry_metadata(fields: &[FieldRef]) -> Option<HashMap<String, String>> {
+    const NAME: &str = "ARROW:extension:name";
+    const METADATA: &str = "ARROW:extension:metadata";
+    let mut fields = fields.iter().filter(|field| !field.data_type().is_null());
+    let first = fields.next()?;
+    if !matches!(
+        first.data_type(),
+        DataType::Binary | DataType::LargeBinary | DataType::BinaryView
+    ) || first.metadata().get(NAME).map(String::as_str) != Some("geoarrow.wkb")
+    {
+        return None;
+    }
+    if fields.any(|field| {
+        field.data_type() != first.data_type()
+            || field.metadata().get(NAME) != first.metadata().get(NAME)
+            || field.metadata().get(METADATA) != first.metadata().get(METADATA)
+    }) {
+        return None;
+    }
+    Some(
+        first
+            .metadata()
+            .iter()
+            .filter(|(key, _)| matches!(key.as_str(), NAME | METADATA))
+            .map(|(key, value)| (key.clone(), value.clone()))
+            .collect(),
+    )
+}
+
+#[cfg(test)]
+mod tests {
+    use std::sync::Arc;
+
+    use arrow_schema::Field;
+
+    use super::*;
+
+    #[test]
+    fn geometry_alternatives_require_compatible_types_and_crs() {
+        let geometry = Arc::new(Field::new("g", DataType::Binary, true).with_metadata(
+            HashMap::from([
+                ("ARROW:extension:name".into(), "geoarrow.wkb".into()),
+                ("ARROW:extension:metadata".into(), "{}".into()),
+            ]),
+        ));
+        let null = Arc::new(Field::new("null", DataType::Null, true));
+        assert!(common_geometry_metadata(&[geometry.clone(), null]).is_some());
+        let plain = Arc::new(Field::new("binary", DataType::Binary, true));
+        assert!(common_geometry_metadata(&[geometry.clone(), plain]).is_none());
+        let mut other = geometry.as_ref().clone();
+        other.metadata_mut().insert(
+            "ARROW:extension:metadata".into(),
+            r#"{"edges":"spherical"}"#.into(),
+        );
+        assert!(common_geometry_metadata(&[geometry, Arc::new(other)]).is_none());
+    }
+}
```

## 09. crates/sail-common-datafusion/src/lib.rs {#host-patch-09}

```diff
diff --git a/crates/sail-common-datafusion/src/lib.rs b/crates/sail-common-datafusion/src/lib.rs
index e8b8fbf2c8bf7f5becbc6e2f04cdb6f84405982e..eb962e018634ee9bca36950d1300f65b0fbeb4aa 100644
--- a/crates/sail-common-datafusion/src/lib.rs
+++ b/crates/sail-common-datafusion/src/lib.rs
@@ -1,11 +1,13 @@
 pub mod array;
 pub mod catalog;
 pub mod column_features;
+pub mod connect_extension;
 pub mod datasource;
 pub mod display;
 pub mod error;
 pub mod extension;
 pub mod formatter;
+pub mod geometry;
 mod java_float;
 pub mod lakesource;
 pub mod literal;
@@ -20,3 +22,7 @@ pub mod streaming;
 pub mod udf;
 pub mod utils;
 pub mod variant;
+
+pub mod driver_extension;
+pub mod native_resource;
+pub mod native_scalar;
```

## 10. crates/sail-common-datafusion/src/native_resource.rs {#host-patch-10}

```diff
diff --git a/crates/sail-common-datafusion/src/native_resource.rs b/crates/sail-common-datafusion/src/native_resource.rs
new file mode 100644
index 0000000000000000000000000000000000000000..3f4ffe9458d62a35f06ff29bd7fdf0520c19045e
--- /dev/null
+++ b/crates/sail-common-datafusion/src/native_resource.rs
@@ -0,0 +1,209 @@
+//! Coarse native quotas admitted from the exact pool used by Sail operators.
+use std::fs::OpenOptions;
+use std::io::Write;
+use std::path::PathBuf;
+use std::sync::Arc;
+use std::sync::atomic::{AtomicU64, Ordering};
+
+use datafusion::execution::memory_pool::{MemoryConsumer, MemoryPool, MemoryReservation};
+use datafusion_common::{DataFusionError, Result, plan_err};
+pub use sail_native_resource_ffi::{MEMORY_LEASE_CAPSULE, MemoryLease};
+use tokio::sync::watch;
+
+use crate::extension::SessionExtension;
+
+struct NativeQuota {
+    reservation: Option<MemoryReservation>,
+    audit: Option<QuotaAudit>,
+    tracker: Option<watch::Sender<usize>>,
+}
+
+/// A session-local shutdown barrier for native producer and Arrow owners.
+/// The tracker never owns a lease; its counter reaches zero only on final drop.
+pub struct NativeResourceTracker(watch::Sender<usize>);
+
+impl Default for NativeResourceTracker {
+    fn default() -> Self {
+        Self(watch::channel(0).0)
+    }
+}
+
+impl SessionExtension for NativeResourceTracker {
+    fn name() -> &'static str {
+        "NativeResourceTracker"
+    }
+}
+
+impl NativeResourceTracker {
+    pub fn reserve(
+        &self,
+        pool: &Arc<dyn MemoryPool>,
+        extension: &str,
+        bytes: usize,
+    ) -> Result<MemoryLease> {
+        reserve_native_quota_inner(pool, extension, bytes, Some(self.0.clone()))
+    }
+
+    pub async fn wait_for_release(&self) {
+        let mut receiver = self.0.subscribe();
+        // The sender in self remains alive throughout this wait.
+        let _ = receiver.wait_for(|count| *count == 0).await;
+    }
+}
+
+/// Opt-in lifecycle evidence for integration tests. Normal execution does no
+/// filesystem logging. A release event is written by the last lease owner after
+/// its reservation is returned, rather than by a cancellation request handler.
+struct QuotaAudit {
+    path: PathBuf,
+    id: u64,
+    extension: String,
+    bytes: usize,
+    pool: Arc<dyn MemoryPool>,
+}
+
+impl QuotaAudit {
+    fn write(&self, event: &str) -> Result<()> {
+        static WRITER: std::sync::Mutex<()> = std::sync::Mutex::new(());
+        let _lock = WRITER.lock().map_err(|_| {
+            DataFusionError::Execution("native resource audit writer poisoned".into())
+        })?;
+        let record = serde_json::json!({
+            "timestamp_utc": chrono::Utc::now().to_rfc3339(),
+            "pid": std::process::id(), "id": self.id, "event": event,
+            "extension": self.extension, "bytes": self.bytes,
+            "pool_reserved": self.pool.reserved(),
+        });
+        let mut bytes = serde_json::to_vec(&record)
+            .map_err(|error| DataFusionError::Execution(error.to_string()))?;
+        bytes.push(b'\n');
+        OpenOptions::new()
+            .create(true)
+            .append(true)
+            .open(&self.path)?
+            .write_all(&bytes)?;
+        Ok(())
+    }
+}
+
+impl Drop for NativeQuota {
+    fn drop(&mut self) {
+        // Release first: the audit is evidence about completed accounting.
+        self.reservation.take();
+        if let Some(audit) = &self.audit
+            && let Err(error) = audit.write("released")
+        {
+            eprintln!("native resource release audit failed: {error}");
+        }
+        if let Some(tracker) = &self.tracker {
+            tracker.send_modify(|count| *count -= 1);
+        }
+    }
+}
+
+/// Admit the entire native session cap before any extension state is allocated.
+/// The lease is non-spillable; the native subpool must stay within this prepaid
+/// cap. This accounts participating native allocations, not total process RSS.
+pub fn reserve_native_quota(
+    pool: &Arc<dyn MemoryPool>,
+    extension: &str,
+    bytes: usize,
+) -> Result<MemoryLease> {
+    reserve_native_quota_inner(pool, extension, bytes, None)
+}
+
+fn reserve_native_quota_inner(
+    pool: &Arc<dyn MemoryPool>,
+    extension: &str,
+    bytes: usize,
+    tracker: Option<watch::Sender<usize>>,
+) -> Result<MemoryLease> {
+    if bytes == 0 {
+        return plan_err!("native extension {extension} requires a positive memory quota");
+    }
+    let reservation = MemoryConsumer::new(format!("native extension {extension} session quota"))
+        .with_can_spill(false)
+        .register(pool);
+    reservation.try_grow(bytes).map_err(|error| {
+        // Spark's error transport unwraps Context variants. Keep the admission
+        // boundary in the actual resource error so the client sees it too.
+        DataFusionError::ResourcesExhausted(format!(
+            "native extension {extension} host memory admission of {bytes} bytes refused: {error}"
+        ))
+    })?;
+    let audit = std::env::var_os("SAIL_NATIVE_RESOURCE_AUDIT").map(|path| {
+        static IDS: AtomicU64 = AtomicU64::new(1);
+        QuotaAudit {
+            path: path.into(),
+            id: IDS.fetch_add(1, Ordering::Relaxed),
+            extension: extension.to_owned(),
+            bytes,
+            pool: pool.clone(),
+        }
+    });
+    if let Some(audit) = &audit {
+        audit.write("admitted")?;
+    }
+    if let Some(tracker) = &tracker {
+        tracker.send_modify(|count| *count += 1);
+    }
+    Ok(MemoryLease::new(
+        Arc::new(NativeQuota {
+            reservation: Some(reservation),
+            audit,
+            tracker,
+        }),
+        bytes as u64,
+    ))
+}
+
+#[cfg(test)]
+mod tests {
+    use datafusion::execution::memory_pool::GreedyMemoryPool;
+
+    use super::*;
+
+    #[tokio::test]
+    async fn shutdown_barrier_waits_for_the_last_detached_output_owner() -> Result<()> {
+        let tracker = NativeResourceTracker::default();
+        let pool: Arc<dyn MemoryPool> = Arc::new(GreedyMemoryPool::new(64));
+        let lease = tracker.reserve(&pool, "native-output", 64)?;
+        let output = lease.clone();
+        drop(lease);
+        let mut waiting = Box::pin(tracker.wait_for_release());
+        assert!(futures::poll!(waiting.as_mut()).is_pending());
+        std::thread::spawn(move || drop(output))
+            .join()
+            .map_err(|_| DataFusionError::Execution("output owner thread panicked".into()))?;
+        waiting.await;
+        assert_eq!(pool.reserved(), 0);
+        Ok(())
+    }
+
+    #[test]
+    fn native_quota_and_datafusion_operators_contend_until_the_last_owner_drops() -> Result<()> {
+        let pool: Arc<dyn MemoryPool> = Arc::new(GreedyMemoryPool::new(96));
+        let lease = reserve_native_quota(&pool, "session-a", 64)?;
+        assert_eq!(pool.reserved(), 64);
+        assert!(reserve_native_quota(&pool, "session-b", 33).is_err());
+        let input = MemoryConsumer::new("host foreign input").register(&pool);
+        assert!(input.try_grow(33).is_err());
+        input.try_grow(32)?;
+        assert_eq!(pool.reserved(), 96);
+        let output = lease.clone();
+        drop(lease);
+        drop(input);
+        assert_eq!(
+            pool.reserved(),
+            64,
+            "retained output still owns the native quota"
+        );
+        drop(output);
+        assert_eq!(pool.reserved(), 0);
+        let next = reserve_native_quota(&pool, "session-b", 96)?;
+        assert_eq!(next.bytes(), 96);
+        drop(next);
+        assert_eq!(pool.reserved(), 0);
+        Ok(())
+    }
+}
```

## 11. crates/sail-common-datafusion/src/native_scalar.rs {#host-patch-11}

```diff
diff --git a/crates/sail-common-datafusion/src/native_scalar.rs b/crates/sail-common-datafusion/src/native_scalar.rs
new file mode 100644
index 0000000000000000000000000000000000000000..d77599e87905d2b40fce8fba18b1050376555f35
--- /dev/null
+++ b/crates/sail-common-datafusion/src/native_scalar.rs
@@ -0,0 +1,155 @@
+use std::any::Any;
+use std::collections::HashMap;
+use std::hash::{Hash, Hasher};
+use std::sync::{Arc, Mutex, OnceLock};
+
+use arrow_schema::{DataType, FieldRef};
+use datafusion_common::{Result, plan_datafusion_err};
+use datafusion_expr::{
+    ColumnarValue, ReturnFieldArgs, ScalarFunctionArgs, ScalarUDF, ScalarUDFImpl, Signature,
+};
+
+/// Retains the Python owner and gives each catalog alias its own name. The
+/// underlying kernel still receives the original argument/return field metadata.
+pub struct OwnedScalar {
+    pub name: String,
+    pub identity: String,
+    pub udf: ScalarUDF,
+    pub owner: Arc<dyn Any + Send + Sync>,
+}
+
+impl PartialEq for OwnedScalar {
+    fn eq(&self, other: &Self) -> bool {
+        self.name == other.name && self.identity == other.identity && self.udf == other.udf
+    }
+}
+impl Eq for OwnedScalar {}
+impl Hash for OwnedScalar {
+    fn hash<H: Hasher>(&self, state: &mut H) {
+        self.name.hash(state);
+        self.identity.hash(state);
+        self.udf.hash(state);
+    }
+}
+
+impl ScalarUDFImpl for OwnedScalar {
+    fn name(&self) -> &str {
+        &self.name
+    }
+    fn signature(&self) -> &Signature {
+        self.udf.signature()
+    }
+    fn return_type(&self, types: &[DataType]) -> Result<DataType> {
+        self.udf.return_type(types)
+    }
+    fn return_field_from_args(&self, args: ReturnFieldArgs) -> Result<FieldRef> {
+        self.udf.return_field_from_args(args)
+    }
+    fn invoke_with_args(&self, args: ScalarFunctionArgs) -> Result<ColumnarValue> {
+        // The owner is held for every call and for as long as this UDF is planned.
+        let _owner = &self.owner;
+        self.udf.invoke_with_args(args)
+    }
+    fn coerce_types(&self, types: &[DataType]) -> Result<Vec<DataType>> {
+        self.udf.coerce_types(types)
+    }
+    fn short_circuits(&self) -> bool {
+        self.udf.short_circuits()
+    }
+}
+
+impl std::fmt::Debug for OwnedScalar {
+    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
+        f.debug_struct("OwnedScalar")
+            .field("name", &self.name)
+            .field("identity", &self.identity)
+            .finish()
+    }
+}
+
+pub const SCALAR_CODEC_PREFIX: &[u8] = b"SAIL_NATIVE_SCALAR_V1\0";
+type Functions = HashMap<(String, String), Arc<ScalarUDF>>;
+fn functions() -> &'static Mutex<Functions> {
+    static FUNCTIONS: OnceLock<Mutex<Functions>> = OnceLock::new();
+    FUNCTIONS.get_or_init(Mutex::default)
+}
+
+/// Only immutable, placement=any scalar implementations enter this process registry.
+/// Keys include a content digest of package code and canonical configuration.
+pub fn retain_scalar(udf: ScalarUDF) -> Result<()> {
+    let native = udf
+        .inner()
+        .downcast_ref::<OwnedScalar>()
+        .ok_or_else(|| plan_datafusion_err!("expected native scalar"))?;
+    let key = (native.identity.clone(), native.name.clone());
+    functions()
+        .lock()
+        .map_err(|_| plan_datafusion_err!("native scalar registry poisoned"))?
+        .entry(key)
+        .or_insert_with(|| Arc::new(udf));
+    Ok(())
+}
+
+pub fn encode_scalar(udf: &ScalarUDF, output: &mut Vec<u8>) -> Result<bool> {
+    let Some(native) = udf.inner().downcast_ref::<OwnedScalar>() else {
+        return Ok(false);
+    };
+    output.extend_from_slice(SCALAR_CODEC_PREFIX);
+    let descriptor = serde_json::to_vec(&(&native.identity, &native.name))
+        .map_err(|e| plan_datafusion_err!("native scalar descriptor: {e}"))?;
+    output.extend_from_slice(&descriptor);
+    Ok(true)
+}
+
+pub fn decode_scalar(name: &str, bytes: &[u8]) -> Result<Arc<ScalarUDF>> {
+    if bytes.len() > 8192 {
+        return Err(plan_datafusion_err!("native scalar descriptor too large"));
+    }
+    let payload = bytes
+        .strip_prefix(SCALAR_CODEC_PREFIX)
+        .ok_or_else(|| plan_datafusion_err!("invalid native scalar codec owner/version"))?;
+    let (identity, encoded_name): (String, String) = serde_json::from_slice(payload)
+        .map_err(|e| plan_datafusion_err!("native scalar descriptor: {e}"))?;
+    if name != encoded_name {
+        return Err(plan_datafusion_err!("native scalar name mismatch"));
+    }
+    functions().lock().map_err(|_| plan_datafusion_err!("native scalar registry poisoned"))?
+        .get(&(identity.clone(), encoded_name)).cloned()
+        .ok_or_else(|| plan_datafusion_err!("native extension unavailable or package/configuration mismatch on worker: {identity}, function {name}"))
+}
+
+#[cfg(test)]
+mod tests {
+    use super::*;
+
+    #[test]
+    fn native_scalar_extension_codec_requires_the_exact_loaded_identity() -> Result<()> {
+        let native = |identity: &str| {
+            ScalarUDF::new_from_impl(OwnedScalar {
+                name: "fixture_native_abs".into(),
+                identity: identity.into(),
+                udf: (*datafusion::functions::math::abs()).clone(),
+                owner: Arc::new(()),
+            })
+        };
+        let original = native("fixture@1:code-and-configuration-A");
+        retain_scalar(original.clone())?;
+        let mut bytes = vec![];
+        assert!(encode_scalar(&original, &mut bytes)?);
+        assert_eq!(
+            decode_scalar("fixture_native_abs", &bytes)?.name(),
+            original.name()
+        );
+        assert!(decode_scalar("renamed", &bytes).is_err());
+        let mut incompatible = vec![];
+        assert!(encode_scalar(
+            &native("fixture@1:code-and-configuration-B"),
+            &mut incompatible
+        )?);
+        assert!(decode_scalar("fixture_native_abs", &incompatible).is_err());
+        assert!(decode_scalar("fixture_native_abs", &vec![0; 8193]).is_err());
+        assert!(decode_scalar("fixture_native_abs", b"SAIL_NATIVE_SCALAR_V2\0[]").is_err());
+        assert!(decode_scalar("fixture_native_abs", SCALAR_CODEC_PREFIX).is_err());
+        Ok(())
+    }
+}
```

## 12. crates/sail-common-datafusion/src/session/lifecycle.rs {#host-patch-12}

```diff
diff --git a/crates/sail-common-datafusion/src/session/lifecycle.rs b/crates/sail-common-datafusion/src/session/lifecycle.rs
new file mode 100644
index 0000000000000000000000000000000000000000..afc4ed4fe1bbc3b0ca4e016ef292d8b2f26fec76
--- /dev/null
+++ b/crates/sail-common-datafusion/src/session/lifecycle.rs
@@ -0,0 +1,32 @@
+use std::sync::Arc;
+
+use datafusion::common::Result;
+
+use crate::extension::SessionExtension;
+
+/// Protocol-owned operations can retain task contexts containing their session.
+/// Explicit teardown breaks those ownership cycles before a session is removed.
+#[tonic::async_trait]
+pub trait SessionResource: Send + Sync + 'static {
+    async fn stop(&self) -> Result<()>;
+}
+
+pub struct SessionLifecycle {
+    resource: Arc<dyn SessionResource>,
+}
+
+impl SessionLifecycle {
+    pub fn new(resource: Arc<dyn SessionResource>) -> Self {
+        Self { resource }
+    }
+
+    pub async fn stop(&self) -> Result<()> {
+        self.resource.stop().await
+    }
+}
+
+impl SessionExtension for SessionLifecycle {
+    fn name() -> &'static str {
+        "SessionLifecycle"
+    }
+}
```

## 13. crates/sail-common-datafusion/src/session/mod.rs {#host-patch-13}

```diff
diff --git a/crates/sail-common-datafusion/src/session/mod.rs b/crates/sail-common-datafusion/src/session/mod.rs
index 2bde515e56dcdca5ef2ed4af8e0464c8799e8a39..23e61281b8659a968e1632901e8a044c1450e81c 100644
--- a/crates/sail-common-datafusion/src/session/mod.rs
+++ b/crates/sail-common-datafusion/src/session/mod.rs
@@ -1,4 +1,5 @@
 pub mod activity;
 pub mod job;
+pub mod lifecycle;
 pub mod plan;
 pub mod repartition;
```

## 14. crates/sail-common/src/spec/plan.rs {#host-patch-14}

```diff
diff --git a/crates/sail-common/src/spec/plan.rs b/crates/sail-common/src/spec/plan.rs
index 33c14d0d485a6a12d6fecbeaa5ffca3898db741b..33f736ebda67536a01bacaa2bb5939bd72e97182 100644
--- a/crates/sail-common/src/spec/plan.rs
+++ b/crates/sail-common/src/spec/plan.rs
@@ -73,6 +73,13 @@ impl CommandPlan {
 #[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
 #[serde(rename_all = "camelCase", rename_all_fields = "camelCase")]
 pub enum QueryNode {
+    /// Experimental, local-mode Spark Connect relation extension.
+    Extension {
+        payload_type_url: String,
+        payload: Vec<u8>,
+        inputs: Vec<QueryPlan>,
+        is_envelope: bool,
+    },
     Read {
         #[serde(flatten)]
         read_type: ReadType,
```

## 15. crates/sail-execution/src/driver/job_scheduler/core.rs {#host-patch-15}

```diff
diff --git a/crates/sail-execution/src/driver/job_scheduler/core.rs b/crates/sail-execution/src/driver/job_scheduler/core.rs
index 7161812f21a1062c0e4c34ee4eb9978f8bb5b205..c6b3ab1ec98832cc2dd925776df5211a2f82afb8 100644
--- a/crates/sail-execution/src/driver/job_scheduler/core.rs
+++ b/crates/sail-execution/src/driver/job_scheduler/core.rs
@@ -10,6 +10,9 @@ use datafusion_proto::physical_plan::PhysicalExtensionCodec;
 use indexmap::{IndexMap, IndexSet};
 use log::{debug, warn};
 use sail_common::actor::ActorContext;
+use sail_common_datafusion::driver_extension::{
+    contains_driver_extension, release_driver_extensions,
+};
 use sail_common_datafusion::error::CommonErrorCause;
 use sail_python_udf::error::PyErrExtractor;
 use sail_system_store::SystemEvent;
@@ -203,6 +206,18 @@ impl JobScheduler {
             .any(|x| matches!(x.state, TaskRegionState::Failed))
         {
             let cause = Self::infer_job_failure_cause(job);
+            let cause = if job
+                .graph
+                .stages()
+                .iter()
+                .any(|stage| contains_driver_extension(&stage.plan))
+            {
+                CommonErrorCause::Execution(format!(
+                    "driver extension task failed; automatic retry disabled; an unacknowledged mutation outcome is indeterminate: {cause}"
+                ))
+            } else {
+                cause
+            };
             if let JobState::Running { output, .. } = &job.state {
                 actions.push(JobAction::FailJobOutput {
                     handle: output.handle(),
@@ -248,11 +263,23 @@ impl JobScheduler {
 
     fn update_task_regions(job: &mut JobDescriptor, options: &JobSchedulerOptions) {
         for (r, region) in job.topology.regions.iter().enumerate() {
+            // A lost acknowledgement cannot distinguish a committed native
+            // mutation from one canceled before publication. Never re-execute
+            // a region containing a driver-resident native operation.
+            let max_attempts = if region
+                .tasks
+                .iter()
+                .any(|task| contains_driver_extension(&job.graph.stages()[task.stage].plan))
+            {
+                1
+            } else {
+                options.task_max_attempts
+            };
             let failed = region.tasks.iter().any(|t| {
                 let attempts = &job.stages[t.stage].tasks[t.partition].attempts;
                 if let Some(attempt) = attempts.last()
                     && matches!(attempt.state, TaskState::Failed | TaskState::Canceled)
-                    && attempts.len() >= options.task_max_attempts
+                    && attempts.len() >= max_attempts
                 {
                     return true;
                 }
@@ -625,6 +652,9 @@ impl JobScheduler {
             context: job.context.clone(),
         });
         job.state.finish_output(outcome);
+        for stage in job.graph.stages() {
+            release_driver_extensions(&stage.plan);
+        }
         event_reporter.report(SystemEvent::JobUpdated {
             session_id,
             job_id: u64::from(job_id),
@@ -1107,6 +1137,10 @@ impl StageGroup {
     }
 }
 
+#[cfg(test)]
+#[path = "native_retry_tests.rs"]
+mod native_retry_tests;
+
 #[cfg(test)]
 mod tests {
     use std::collections::HashSet;
```

## 16. crates/sail-execution/src/driver/job_scheduler/native_retry_tests.rs {#host-patch-16}

```diff
diff --git a/crates/sail-execution/src/driver/job_scheduler/native_retry_tests.rs b/crates/sail-execution/src/driver/job_scheduler/native_retry_tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..f11eb3c3f3bc04f1026c8db0f8963a6d1dd1da07
--- /dev/null
+++ b/crates/sail-execution/src/driver/job_scheduler/native_retry_tests.rs
@@ -0,0 +1,92 @@
+use std::sync::atomic::{AtomicUsize, Ordering};
+
+use datafusion::arrow::datatypes::Schema;
+use datafusion::physical_plan::empty::EmptyExec;
+use sail_common_datafusion::driver_extension::{
+    BoundDriverPlan, DriverDescriptor, DriverExtensionBinding, DriverExtensionExec,
+};
+
+use super::*;
+use crate::job_graph::JobGraphOptions;
+use crate::shuffle::ShuffleCompression;
+
+#[derive(Debug)]
+struct CommitThenLoseAcknowledgement(Arc<AtomicUsize>);
+impl DriverExtensionBinding for CommitThenLoseAcknowledgement {
+    fn materialize(
+        &self,
+        _: &[Arc<dyn ExecutionPlan>],
+        _: Arc<TaskContext>,
+    ) -> datafusion::common::Result<Arc<dyn ExecutionPlan>> {
+        self.0.fetch_add(1, Ordering::SeqCst);
+        datafusion::common::exec_err!("injected acknowledgement loss after commit")
+    }
+}
+
+#[test]
+fn driver_mutation_acknowledgement_loss_exhausts_the_region_after_one_attempt()
+-> ExecutionResult<()> {
+    let commits = Arc::new(AtomicUsize::new(0));
+    let empty: Arc<dyn ExecutionPlan> = Arc::new(EmptyExec::new(Arc::new(Schema::empty())));
+    let native: Arc<dyn ExecutionPlan> = Arc::new(DriverExtensionExec::new(
+        Arc::new(BoundDriverPlan {
+            descriptor: DriverDescriptor {
+                owner: "fault-fixture@1:code".into(),
+                plan_id: "committed-write".into(),
+            },
+            properties: empty.properties().clone(),
+            input_schemas: vec![],
+            binding: Arc::new(CommitThenLoseAcknowledgement(commits.clone())),
+        }),
+        vec![],
+    )?);
+    let backend = ShuffleBackendKind::Flight {
+        compression: ShuffleCompression::None,
+    };
+    let options = JobSchedulerOptions::for_retry_test(3, backend.clone());
+    // Control: an ordinary failed task remains retryable with this configuration.
+    for (plan, is_native) in [(empty, false), (native.clone(), true)] {
+        let graph = JobGraph::try_new(
+            plan,
+            JobGraphOptions {
+                shuffle_backend: backend.clone(),
+            },
+        )?;
+        let mut job =
+            JobDescriptor::try_new(graph, JobState::Draining, Arc::new(TaskContext::default()))?;
+        for stage in &mut job.stages {
+            for task in &mut stage.tasks {
+                task.attempts.push(TaskAttemptDescriptor {
+                    state: TaskState::Failed,
+                    messages: vec![],
+                    cause: None,
+                    job_output_fetched: false,
+                });
+            }
+        }
+        if is_native {
+            assert!(native.execute(0, Arc::new(TaskContext::default())).is_err());
+            assert_eq!(commits.load(Ordering::SeqCst), 1);
+            assert!(
+                job.graph
+                    .stages()
+                    .iter()
+                    .any(|stage| matches!(stage.placement, TaskPlacement::Driver))
+            );
+        }
+        JobScheduler::update_task_regions(&mut job, &options);
+        assert_eq!(
+            job.regions
+                .iter()
+                .any(|region| matches!(region.state, TaskRegionState::Failed)),
+            is_native
+        );
+        assert!(
+            job.stages
+                .iter()
+                .all(|stage| stage.tasks.iter().all(|task| task.attempts.len() == 1))
+        );
+    }
+    assert_eq!(commits.load(Ordering::SeqCst), 1);
+    Ok(())
+}
```

## 17. crates/sail-execution/src/driver/job_scheduler/options.rs {#host-patch-17}

```diff
diff --git a/crates/sail-execution/src/driver/job_scheduler/options.rs b/crates/sail-execution/src/driver/job_scheduler/options.rs
index c341718cf6d7d073bace6be5889df06fa57377ac..4a67906436ad1f9ad416ba99b59951732418ffde 100644
--- a/crates/sail-execution/src/driver/job_scheduler/options.rs
+++ b/crates/sail-execution/src/driver/job_scheduler/options.rs
@@ -23,3 +23,18 @@ impl From<&DriverOptions> for JobSchedulerOptions {
         }
     }
 }
+
+#[cfg(test)]
+impl JobSchedulerOptions {
+    pub(super) fn for_retry_test(
+        task_max_attempts: usize,
+        shuffle_backend: ShuffleBackendKind,
+    ) -> Self {
+        Self {
+            session_id: "fault-fixture".into(),
+            task_launch_timeout: Duration::from_secs(30),
+            task_max_attempts,
+            shuffle_backend,
+        }
+    }
+}
```

## 18. crates/sail-execution/src/job_graph/planner.rs {#host-patch-18}

```diff
diff --git a/crates/sail-execution/src/job_graph/planner.rs b/crates/sail-execution/src/job_graph/planner.rs
index 0540ef15deaa10ff5f11c743ca559bf4e09b1510..284da4c5fdb16f1eb63283eee2fe543ff125c587 100644
--- a/crates/sail-execution/src/job_graph/planner.rs
+++ b/crates/sail-execution/src/job_graph/planner.rs
@@ -490,13 +490,7 @@ fn plan_job_graph_stages(
         let plan =
             create_rescale_input(child, coalesce.output_partitions(), graph, scalar_context)?;
         PlannedSubtree::without_pending_scalar_subquery_expr(plan)
-    } else if subtree.plan.is::<SystemTableExec>()
-        || subtree.plan.is::<CatalogCommandExec>()
-        || subtree.plan.is::<FileDeleteExec>()
-        || subtree.plan.is::<DeltaCommitExec>()
-        || subtree.plan.is::<IcebergCommitExec>()
-        || subtree.plan.is::<RemoteCheckpointCommitExec>()
-    {
+    } else if is_driver_stage_plan(&subtree.plan) {
         if matches!(driver_stage_handling, DriverStageHandling::PreserveRoot) {
             subtree.into_planned_subtree()
         } else {
@@ -642,6 +636,7 @@ fn is_driver_stage_plan(plan: &Arc<dyn ExecutionPlan>) -> bool {
     }
 
     plan.is::<SystemTableExec>()
+        || plan.is::<sail_common_datafusion::driver_extension::DriverExtensionExec>()
         || plan.is::<CatalogCommandExec>()
         || plan.is::<FileDeleteExec>()
         || plan.is::<DeltaCommitExec>()
```

## 19. crates/sail-execution/src/proto/codec.rs {#host-patch-19}

```diff
diff --git a/crates/sail-execution/src/proto/codec.rs b/crates/sail-execution/src/proto/codec.rs
index 86a93571332dbf305f1c64160815f9e7e56c4e93..1763c695e23cd7283a9cbbc1f02ef8490b84630c 100644
--- a/crates/sail-execution/src/proto/codec.rs
+++ b/crates/sail-execution/src/proto/codec.rs
@@ -95,6 +95,8 @@ use sail_common_datafusion::catalog::{
     CatalogPartitionField, LakehouseExecutionContext, PartitionTransform,
 };
 use sail_common_datafusion::datasource::PhysicalSinkMode;
+use sail_common_datafusion::driver_extension::{DRIVER_CODEC_PREFIX, DriverExtensionExec};
+use sail_common_datafusion::native_scalar::{decode_scalar, encode_scalar};
 use sail_common_datafusion::schema_evolution::{
     SchemaEvolutionCastColumnExpr, SchemaEvolutionDefaultExpr,
     SchemaEvolutionPhysicalExprAdapterFactoryWithMatching, SchemaEvolutionTimezoneMode,
@@ -352,6 +354,9 @@ impl PhysicalExtensionCodec for RemoteExecutionCodec {
         ctx: &TaskContext,
         proto_converter: &dyn PhysicalProtoConverterExtension,
     ) -> Result<Arc<dyn ExecutionPlan>> {
+        if buf.starts_with(DRIVER_CODEC_PREFIX) {
+            return DriverExtensionExec::decode(buf, inputs, ctx);
+        }
         let node = ExtendedPhysicalPlanNode::decode(buf)
             .map_err(|e| plan_datafusion_err!("failed to decode plan: {e}"))?;
         let ExtendedPhysicalPlanNode { node_kind } = node;
@@ -1904,6 +1909,9 @@ impl PhysicalExtensionCodec for RemoteExecutionCodec {
         buf: &mut Vec<u8>,
         proto_converter: &dyn PhysicalProtoConverterExtension,
     ) -> Result<()> {
+        if let Some(native) = node.downcast_ref::<DriverExtensionExec>() {
+            return native.encode(buf);
+        }
         let node_kind = if let Some(range) = node.downcast_ref::<RangeExec>() {
             let schema = try_encode_schema(range.original_schema().as_ref())?;
             let projection = self.try_encode_projection(range.projection())?;
@@ -3000,6 +3008,9 @@ impl PhysicalExtensionCodec for RemoteExecutionCodec {
     }
 
     fn try_decode_udf(&self, name: &str, buf: &[u8]) -> Result<Arc<ScalarUDF>> {
+        if buf.starts_with(sail_common_datafusion::native_scalar::SCALAR_CODEC_PREFIX) {
+            return decode_scalar(name, buf);
+        }
         // TODO: Implement custom registry to avoid codec for built-in functions.
         // The `match name` below has no session-registry fallback, so every
         // scalar UDF needs an explicit arm or distributed decode fails with
@@ -3472,6 +3483,9 @@ impl PhysicalExtensionCodec for RemoteExecutionCodec {
     }
 
     fn try_encode_udf(&self, node: &ScalarUDF, buf: &mut Vec<u8>) -> Result<()> {
+        if encode_scalar(node, buf)? {
+            return Ok(());
+        }
         // TODO: Implement custom registry to avoid codec for built-in functions
         let node_inner = node.inner();
         let udf_kind: UdfKind = if node_inner.is::<ArrayElement>()
```

## 20. crates/sail-execution/src/proto/converter.rs {#host-patch-20}

```diff
diff --git a/crates/sail-execution/src/proto/converter.rs b/crates/sail-execution/src/proto/converter.rs
index 5dbc2e4edd8a7249ddfa20181f88126b9748ddc2..8682125789aeb55710e4776df1f69f48aa6d68b5 100644
--- a/crates/sail-execution/src/proto/converter.rs
+++ b/crates/sail-execution/src/proto/converter.rs
@@ -69,29 +69,38 @@ impl PhysicalProtoConverterExtension for RemotePhysicalProtoConverter {
         input_schema: &Schema,
         ctx: &PhysicalPlanDecodeContext<'_>,
     ) -> Result<Arc<dyn PhysicalExpr>> {
-        let decoded = match decode_remote_expr_kind(proto)? {
-            Some((ExprKind::HigherOrderUdf(node), inputs)) => {
-                self.higher_order_proto_to_expr(node, inputs, input_schema, ctx)
-            }
-            Some((ExprKind::LambdaVariable(node), _)) => {
-                let field = try_decode_field_ref(&node.field)?;
-                let index = usize::try_from(node.index).map_err(|_| {
-                    plan_datafusion_err!(
-                        "LambdaVariable index {} does not fit in usize",
-                        node.index
-                    )
-                })?;
-                Ok(Arc::new(LambdaVariable::new(index, field)) as Arc<dyn PhysicalExpr>)
-            }
-            Some((ExprKind::Lambda(node), inputs)) => {
-                let [body] = inputs else {
-                    return plan_err!("LambdaExpr expects exactly one input, got {}", inputs.len());
-                };
-                let body = self.proto_to_physical_expr(body, input_schema, ctx)?;
-                Ok(Arc::new(LambdaExpr::try_new(node.params, body)?) as Arc<dyn PhysicalExpr>)
-            }
-            _ => self.default_proto_to_physical_expr(proto, input_schema, ctx),
-        }?;
+        let decoded = if let Some(expr) =
+            super::native_expr::decode(proto, input_schema, ctx, self)?
+        {
+            expr
+        } else {
+            match decode_remote_expr_kind(proto)? {
+                Some((ExprKind::HigherOrderUdf(node), inputs)) => {
+                    self.higher_order_proto_to_expr(node, inputs, input_schema, ctx)
+                }
+                Some((ExprKind::LambdaVariable(node), _)) => {
+                    let field = try_decode_field_ref(&node.field)?;
+                    let index = usize::try_from(node.index).map_err(|_| {
+                        plan_datafusion_err!(
+                            "LambdaVariable index {} does not fit in usize",
+                            node.index
+                        )
+                    })?;
+                    Ok(Arc::new(LambdaVariable::new(index, field)) as Arc<dyn PhysicalExpr>)
+                }
+                Some((ExprKind::Lambda(node), inputs)) => {
+                    let [body] = inputs else {
+                        return plan_err!(
+                            "LambdaExpr expects exactly one input, got {}",
+                            inputs.len()
+                        );
+                    };
+                    let body = self.proto_to_physical_expr(body, input_schema, ctx)?;
+                    Ok(Arc::new(LambdaExpr::try_new(node.params, body)?) as Arc<dyn PhysicalExpr>)
+                }
+                _ => self.default_proto_to_physical_expr(proto, input_schema, ctx),
+            }?
+        };
 
         let Some(expression_id) = proto.expr_id else {
             return Ok(decoded);
@@ -118,6 +127,9 @@ impl PhysicalProtoConverterExtension for RemotePhysicalProtoConverter {
         expr: &Arc<dyn PhysicalExpr>,
         codec: &dyn PhysicalExtensionCodec,
     ) -> Result<PhysicalExprNode> {
+        if let Some(proto) = super::native_expr::encode(expr, codec, self)? {
+            return Ok(proto);
+        }
         if let Some(hof) = expr.downcast_ref::<HigherOrderFunctionExpr>() {
             return self.higher_order_expr_to_proto(expr, hof, codec);
         }
```

## 21. crates/sail-execution/src/proto/mod.rs {#host-patch-21}

```diff
diff --git a/crates/sail-execution/src/proto/mod.rs b/crates/sail-execution/src/proto/mod.rs
index 49599ef748d665216da9efc52a964c861bbadb14..e1448edc33157b2c4872d445881fafaa7fe23075 100644
--- a/crates/sail-execution/src/proto/mod.rs
+++ b/crates/sail-execution/src/proto/mod.rs
@@ -2,6 +2,7 @@ mod codec;
 mod converter;
 mod decode;
 mod encode;
+mod native_expr;
 
 pub use codec::RemoteExecutionCodec;
 #[cfg(test)]
```

## 22. crates/sail-execution/src/proto/native_expr.rs {#host-patch-22}

```diff
diff --git a/crates/sail-execution/src/proto/native_expr.rs b/crates/sail-execution/src/proto/native_expr.rs
new file mode 100644
index 0000000000000000000000000000000000000000..562865e02aba05fb1c560e3fde7142bbc34807a8
--- /dev/null
+++ b/crates/sail-execution/src/proto/native_expr.rs
@@ -0,0 +1,358 @@
+//! Native scalar return fields carry extension metadata that DataFusion's
+//! standard scalar-expression protobuf currently omits.
+use std::sync::Arc;
+
+use datafusion::arrow::datatypes::Schema;
+use datafusion::common::metadata::FieldMetadata;
+use datafusion::common::{Result, plan_datafusion_err};
+use datafusion::execution::FunctionRegistry;
+use datafusion::physical_expr::expressions::{CastExpr, Literal};
+use datafusion::physical_expr::{PhysicalExpr, ScalarFunctionExpr};
+use datafusion_proto::physical_plan::to_proto::serialize_physical_expr_with_converter;
+use datafusion_proto::physical_plan::{
+    PhysicalExtensionCodec, PhysicalPlanDecodeContext, PhysicalProtoConverterExtension,
+};
+use datafusion_proto::protobuf::{PhysicalExprNode, PhysicalExtensionExprNode, physical_expr_node};
+use sail_common_datafusion::native_scalar::OwnedScalar;
+use serde::{Deserialize, Serialize};
+
+use super::decode::try_decode_field_ref;
+use super::encode::try_encode_field_ref;
+
+const PREFIX: &[u8] = b"SAIL_NATIVE_SCALAR_EXPR_V1\0";
+const LITERAL_PREFIX: &[u8] = b"SAIL_METADATA_LITERAL_V1\0";
+const CAST_PREFIX: &[u8] = b"SAIL_METADATA_CAST_V1\0";
+const MAX_DESCRIPTOR: usize = 1024 * 1024;
+
+#[derive(Serialize, Deserialize)]
+#[serde(deny_unknown_fields)]
+struct Descriptor {
+    name: String,
+    udf: Vec<u8>,
+    field: Vec<u8>,
+    nullable: bool,
+}
+
+pub(super) fn encode(
+    expr: &Arc<dyn PhysicalExpr>,
+    codec: &dyn PhysicalExtensionCodec,
+    converter: &dyn PhysicalProtoConverterExtension,
+) -> Result<Option<PhysicalExprNode>> {
+    if let Some(cast) = expr.downcast_ref::<CastExpr>()
+        && cast.has_explicit_metadata()
+        && !cast.target_field().metadata().is_empty()
+    {
+        let bytes = try_encode_field_ref(cast.target_field())?;
+        if bytes.len() > MAX_DESCRIPTOR {
+            return Err(plan_datafusion_err!("cast field descriptor too large"));
+        }
+        return Ok(Some(PhysicalExprNode {
+            expr_type: Some(physical_expr_node::ExprType::Extension(
+                PhysicalExtensionExprNode {
+                    expr: [CAST_PREFIX, bytes.as_slice()].concat(),
+                    inputs: vec![serialize_physical_expr_with_converter(
+                        expr, codec, converter,
+                    )?],
+                },
+            )),
+            expr_id: expr.expression_id(),
+        }));
+    }
+    if expr.downcast_ref::<Literal>().is_some() {
+        let field = expr.return_field(&Schema::empty())?;
+        if !field.metadata().is_empty() {
+            let bytes = try_encode_field_ref(&field)?;
+            if bytes.len() > MAX_DESCRIPTOR {
+                return Err(plan_datafusion_err!("literal field descriptor too large"));
+            }
+            return Ok(Some(PhysicalExprNode {
+                expr_type: Some(physical_expr_node::ExprType::Extension(
+                    PhysicalExtensionExprNode {
+                        expr: [LITERAL_PREFIX, bytes.as_slice()].concat(),
+                        inputs: vec![serialize_physical_expr_with_converter(
+                            expr, codec, converter,
+                        )?],
+                    },
+                )),
+                expr_id: expr.expression_id(),
+            }));
+        }
+    }
+    let Some(scalar) = expr.downcast_ref::<ScalarFunctionExpr>() else {
+        return Ok(None);
+    };
+    let field = expr.return_field(&Schema::empty())?;
+    if !scalar.fun().inner().is::<OwnedScalar>() && field.metadata().is_empty() {
+        return Ok(None);
+    }
+    let mut udf = vec![];
+    codec.try_encode_udf(scalar.fun(), &mut udf)?;
+    let descriptor = Descriptor {
+        name: scalar.fun().name().to_owned(),
+        udf,
+        field: try_encode_field_ref(&field)?,
+        nullable: scalar.nullable(),
+    };
+    let bytes = serde_json::to_vec(&descriptor)
+        .map_err(|e| plan_datafusion_err!("native scalar descriptor: {e}"))?;
+    if bytes.len() > MAX_DESCRIPTOR {
+        return Err(plan_datafusion_err!("native scalar descriptor too large"));
+    }
+    let inputs = scalar
+        .args()
+        .iter()
+        .map(|arg| converter.physical_expr_to_proto(arg, codec))
+        .collect::<Result<_>>()?;
+    Ok(Some(PhysicalExprNode {
+        expr_type: Some(physical_expr_node::ExprType::Extension(
+            PhysicalExtensionExprNode {
+                expr: [PREFIX, bytes.as_slice()].concat(),
+                inputs,
+            },
+        )),
+        expr_id: expr.expression_id(),
+    }))
+}
+
+pub(super) fn decode(
+    proto: &PhysicalExprNode,
+    schema: &Schema,
+    ctx: &PhysicalPlanDecodeContext<'_>,
+    converter: &dyn PhysicalProtoConverterExtension,
+) -> Result<Option<Arc<dyn PhysicalExpr>>> {
+    let Some(physical_expr_node::ExprType::Extension(node)) = &proto.expr_type else {
+        return Ok(None);
+    };
+    if let Some(bytes) = node.expr.strip_prefix(CAST_PREFIX) {
+        if bytes.len() > MAX_DESCRIPTOR {
+            return Err(plan_datafusion_err!("cast field descriptor too large"));
+        }
+        let [input] = node.inputs.as_slice() else {
+            return Err(plan_datafusion_err!(
+                "metadata cast requires one cast input"
+            ));
+        };
+        if !matches!(input.expr_type, Some(physical_expr_node::ExprType::Cast(_))) {
+            return Err(plan_datafusion_err!("metadata cast input is not a cast"));
+        }
+        let decoded = converter.proto_to_physical_expr(input, schema, ctx)?;
+        let cast = decoded
+            .downcast_ref::<CastExpr>()
+            .ok_or_else(|| plan_datafusion_err!("metadata cast input is not a cast"))?;
+        let field = try_decode_field_ref(bytes)?;
+        if field.data_type() != cast.cast_type() {
+            return Err(plan_datafusion_err!("metadata cast type mismatch"));
+        }
+        return Ok(Some(Arc::new(CastExpr::new_with_target_field(
+            Arc::clone(cast.expr()),
+            field,
+            Some(cast.cast_options().clone()),
+        ))));
+    }
+    if let Some(bytes) = node.expr.strip_prefix(LITERAL_PREFIX) {
+        if bytes.len() > MAX_DESCRIPTOR {
+            return Err(plan_datafusion_err!("literal field descriptor too large"));
+        }
+        let [input] = node.inputs.as_slice() else {
+            return Err(plan_datafusion_err!(
+                "metadata literal requires one literal input"
+            ));
+        };
+        if !matches!(
+            input.expr_type,
+            Some(physical_expr_node::ExprType::Literal(_))
+        ) {
+            return Err(plan_datafusion_err!(
+                "metadata literal input is not a literal"
+            ));
+        }
+        let value = converter.proto_to_physical_expr(input, schema, ctx)?;
+        let literal = value
+            .downcast_ref::<Literal>()
+            .ok_or_else(|| plan_datafusion_err!("metadata literal input is not a literal"))?;
+        let field = try_decode_field_ref(bytes)?;
+        if field.data_type() != &literal.value().data_type() {
+            return Err(plan_datafusion_err!("metadata literal type mismatch"));
+        }
+        let restored = Literal::new_with_metadata(
+            literal.value().clone(),
+            Some(FieldMetadata::new_from_field(&field)),
+        );
+        return Ok(Some(Arc::new(restored)));
+    }
+    let Some(bytes) = node.expr.strip_prefix(PREFIX) else {
+        return Ok(None);
+    };
+    if bytes.len() > MAX_DESCRIPTOR {
+        return Err(plan_datafusion_err!("native scalar descriptor too large"));
+    }
+    let descriptor: Descriptor = serde_json::from_slice(bytes)
+        .map_err(|e| plan_datafusion_err!("native scalar descriptor: {e}"))?;
+    // Match DataFusion's standard ScalarUdf decoder: an empty definition means
+    // a function from the task registry (e.g. get_field), not an empty Sail UDF
+    // descriptor. Native functions always carry their exact identity bytes.
+    let udf = if descriptor.udf.is_empty() {
+        ctx.task_ctx()
+            .udf(&descriptor.name)
+            .or_else(|_| ctx.codec().try_decode_udf(&descriptor.name, &[]))?
+    } else {
+        ctx.codec()
+            .try_decode_udf(&descriptor.name, &descriptor.udf)?
+    };
+    let field = try_decode_field_ref(&descriptor.field)?;
+    let args = node
+        .inputs
+        .iter()
+        .map(|arg| converter.proto_to_physical_expr(arg, schema, ctx))
+        .collect::<Result<_>>()?;
+    Ok(Some(Arc::new(
+        ScalarFunctionExpr::new(
+            &descriptor.name,
+            udf,
+            args,
+            field,
+            Arc::clone(ctx.task_ctx().session_config().options()),
+        )
+        .with_nullable(descriptor.nullable),
+    )))
+}
+
+#[cfg(test)]
+mod tests {
+    use datafusion::arrow::datatypes::{DataType, Field};
+    use datafusion::execution::TaskContext;
+    use datafusion::logical_expr::ScalarUDF;
+    use datafusion::physical_expr::expressions::Column;
+    use sail_common_datafusion::native_scalar::retain_scalar;
+
+    use super::*;
+    use crate::proto::{
+        RemoteExecutionCodec, decode_remote_physical_expr, encode_remote_physical_expr,
+    };
+
+    #[test]
+    fn native_scalar_expression_round_trip_preserves_full_return_field() -> Result<()> {
+        let task = TaskContext::default();
+        let udf = ScalarUDF::new_from_impl(OwnedScalar {
+            name: "metadata_fixture".into(),
+            identity: "fixture@1:metadata".into(),
+            udf: (*datafusion::functions::math::abs()).clone(),
+            owner: Arc::new(()),
+        });
+        retain_scalar(udf.clone())?;
+        let field = Arc::new(
+            Field::new("geometry", DataType::Float64, false).with_metadata(
+                [
+                    ("ARROW:extension:name".into(), "fixture.geometry".into()),
+                    (
+                        "ARROW:extension:metadata".into(),
+                        "{\"crs\":\"EPSG:4326\"}".into(),
+                    ),
+                ]
+                .into(),
+            ),
+        );
+        let schema = Schema::new(vec![Field::new("x", DataType::Float64, false)]);
+        let expr: Arc<dyn PhysicalExpr> = Arc::new(
+            ScalarFunctionExpr::new(
+                "metadata_fixture",
+                Arc::new(udf),
+                vec![Arc::new(Column::new("x", 0))],
+                field.clone(),
+                Arc::clone(task.session_config().options()),
+            )
+            .with_nullable(false),
+        );
+        let bytes = encode_remote_physical_expr(&RemoteExecutionCodec, &expr)?;
+        let decoded = decode_remote_physical_expr(&task, &RemoteExecutionCodec, &bytes, &schema)?;
+        assert_eq!(decoded.return_field(&schema)?, field);
+        assert!(!decoded.nullable(&schema)?);
+        assert_eq!(decoded.children().len(), 1);
+        let literal: Arc<dyn PhysicalExpr> = Arc::new(Literal::new_with_metadata(
+            datafusion::common::ScalarValue::Float64(Some(2.0)),
+            Some(FieldMetadata::new_from_field(&field)),
+        ));
+        let bytes = encode_remote_physical_expr(&RemoteExecutionCodec, &literal)?;
+        let decoded = decode_remote_physical_expr(&task, &RemoteExecutionCodec, &bytes, &schema)?;
+        assert_eq!(
+            decoded.return_field(&schema)?,
+            literal.return_field(&schema)?
+        );
+        assert_eq!(
+            decoded
+                .downcast_ref::<Literal>()
+                .ok_or_else(|| plan_datafusion_err!("expected restored literal"))?
+                .value(),
+            &datafusion::common::ScalarValue::Float64(Some(2.0))
+        );
+        Ok(())
+    }
+
+    #[test]
+    fn builtin_geometry_and_explicit_cast_preserve_metadata_on_workers() -> Result<()> {
+        use datafusion::logical_expr::ReturnFieldArgs;
+        use sail_function::scalar::geo::st_geomfromwkb::StGeomFromWKB;
+
+        let task = TaskContext::default();
+        let schema = Schema::new(vec![Field::new("wkb", DataType::Binary, true)]);
+        let udf = Arc::new(ScalarUDF::from(StGeomFromWKB::new()));
+        let field = udf.return_field_from_args(ReturnFieldArgs {
+            arg_fields: schema.fields(),
+            scalar_arguments: &[None],
+        })?;
+        let scalar: Arc<dyn PhysicalExpr> = Arc::new(ScalarFunctionExpr::new(
+            "st_geomfromwkb",
+            udf,
+            vec![Arc::new(Column::new("wkb", 0))],
+            field.clone(),
+            Arc::clone(task.session_config().options()),
+        ));
+        let cast: Arc<dyn PhysicalExpr> = Arc::new(CastExpr::new_with_target_field(
+            Arc::new(Column::new("wkb", 0)),
+            field.clone(),
+            None,
+        ));
+        for original in [scalar, cast] {
+            let bytes = encode_remote_physical_expr(&RemoteExecutionCodec, &original)?;
+            let restored =
+                decode_remote_physical_expr(&task, &RemoteExecutionCodec, &bytes, &schema)?;
+            assert_eq!(
+                restored.return_field(&schema)?,
+                original.return_field(&schema)?
+            );
+            assert_eq!(restored.return_field(&schema)?.metadata(), field.metadata());
+        }
+        Ok(())
+    }
+
+    #[test]
+    fn metadata_bearing_struct_access_uses_the_task_function_registry() -> Result<()> {
+        let context = datafusion::prelude::SessionContext::new();
+        let task = context.task_ctx();
+        let field =
+            Arc::new(Field::new("value", DataType::Utf8, true).with_metadata(
+                [("description".into(), "ordinary property metadata".into())].into(),
+            ));
+        let schema = Schema::new(vec![Field::new(
+            "node",
+            DataType::Struct(vec![field.clone()].into()),
+            true,
+        )]);
+        let expr: Arc<dyn PhysicalExpr> = Arc::new(ScalarFunctionExpr::new(
+            "get_field",
+            datafusion::functions::core::get_field(),
+            vec![
+                Arc::new(Column::new("node", 0)),
+                Arc::new(Literal::new(datafusion::common::ScalarValue::Utf8(Some(
+                    "value".into(),
+                )))),
+            ],
+            field.clone(),
+            Arc::clone(task.session_config().options()),
+        ));
+        let bytes = encode_remote_physical_expr(&RemoteExecutionCodec, &expr)?;
+        let decoded = decode_remote_physical_expr(&task, &RemoteExecutionCodec, &bytes, &schema)?;
+        assert_eq!(decoded.return_field(&schema)?, field);
+        Ok(())
+    }
+}
```

## 23. crates/sail-execution/src/task_runner/actor/handler.rs {#host-patch-23}

```diff
diff --git a/crates/sail-execution/src/task_runner/actor/handler.rs b/crates/sail-execution/src/task_runner/actor/handler.rs
index 20a37c4fceca2eca7ef9e91c78b7c286167bec83..7a4d552117e7d853967f922951332bd8fc05cd96 100644
--- a/crates/sail-execution/src/task_runner/actor/handler.rs
+++ b/crates/sail-execution/src/task_runner/actor/handler.rs
@@ -4,7 +4,7 @@ use datafusion::arrow::datatypes::Schema;
 use datafusion::common::DataFusionError;
 use datafusion::execution::TaskContext;
 use datafusion_proto::protobuf::PhysicalPlanNode;
-use log::{error, warn};
+use log::{debug, error, warn};
 use prost::Message;
 use sail_common::actor::{ActorAction, ActorContext};
 use sail_common_datafusion::error::CommonErrorCause;
@@ -125,12 +125,17 @@ impl TaskRunnerActor {
                 });
             }
             TaskRunnerPlacement::Worker {
+                worker_id,
                 sequence,
                 driver,
                 worker,
                 retry_strategy,
                 ..
             } => {
+                debug!(
+                    "worker_task_status worker_id={worker_id} job_id={} stage={} partition={} attempt={} status={status}",
+                    key.job_id, key.stage, key.partition, key.attempt
+                );
                 let seq = *sequence;
                 *sequence = match seq.checked_add(1) {
                     Some(s) => s,
```

## 24. crates/sail-execution/src/worker_manager/kubernetes.rs {#host-patch-24}

```diff
diff --git a/crates/sail-execution/src/worker_manager/kubernetes.rs b/crates/sail-execution/src/worker_manager/kubernetes.rs
index c5a43e026df341f0730c3fe9b0ad4693a02b1cc4..fad04a8993b1c050dae1fbae95c28f48481f61e5 100644
--- a/crates/sail-execution/src/worker_manager/kubernetes.rs
+++ b/crates/sail-execution/src/worker_manager/kubernetes.rs
@@ -169,6 +169,11 @@ impl KubernetesWorkerService {
             }
         };
         let mut env = vec![
+            EnvVar {
+                name: "SAIL_EXPERIMENTAL_EXTENSIONS".to_string(),
+                value: Some(env::var("SAIL_EXPERIMENTAL_EXTENSIONS").unwrap_or_default()),
+                value_from: None,
+            },
             EnvVar {
                 name: "RUST_LOG".to_string(),
                 value: Some(env::var("RUST_LOG").unwrap_or("info".to_string())),
```

## 25. crates/sail-execution/src/worker_manager/mod.rs {#host-patch-25}

```diff
diff --git a/crates/sail-execution/src/worker_manager/mod.rs b/crates/sail-execution/src/worker_manager/mod.rs
index 044c53edc4586c2d3bde741f26e4239573895dee..e946f1329d2dd3a0b81574ed0ac0237f422878c9 100644
--- a/crates/sail-execution/src/worker_manager/mod.rs
+++ b/crates/sail-execution/src/worker_manager/mod.rs
@@ -1,6 +1,8 @@
 mod kubernetes;
 mod local;
 mod options;
+mod process;
+mod process_command;
 
 use futures::future::BoxFuture;
 pub(crate) use options::WorkerLaunchOptions;
@@ -35,3 +37,4 @@ pub trait WorkerManager: Send + Sync + 'static {
 
 pub use kubernetes::{KubernetesWorkerManager, KubernetesWorkerManagerOptions};
 pub use local::LocalWorkerManager;
+pub use process::ProcessWorkerManager;
```

## 26. crates/sail-execution/src/worker_manager/process.rs {#host-patch-26}

```diff
diff --git a/crates/sail-execution/src/worker_manager/process.rs b/crates/sail-execution/src/worker_manager/process.rs
new file mode 100644
index 0000000000000000000000000000000000000000..4bf0035880b1652fd69ebf16d3970ac6698bc42a
--- /dev/null
+++ b/crates/sail-execution/src/worker_manager/process.rs
@@ -0,0 +1,104 @@
+//! Experimental local-cluster workers launched as separate Sail executables.
+use std::sync::Arc;
+use std::time::Duration;
+
+use futures::future::BoxFuture;
+use sail_common::actor::ActorSystem;
+use sail_common::config::{CliConfigEnv, ClusterConfigEnv, ExecutionConfigEnv};
+use tokio::process::Child;
+use tokio::sync::Mutex;
+
+use super::process_command::{WORKER_COMMAND_ENV, worker_command};
+use crate::error::{ExecutionError, ExecutionResult};
+use crate::id::WorkerId;
+use crate::worker_manager::{WorkerLaunchOptions, WorkerManager};
+
+#[derive(Default)]
+pub struct ProcessWorkerManager {
+    children: Arc<Mutex<Vec<Child>>>,
+}
+
+#[tonic::async_trait]
+impl WorkerManager for ProcessWorkerManager {
+    fn launch_worker(
+        &self,
+        _system: &mut ActorSystem,
+        id: WorkerId,
+        options: WorkerLaunchOptions,
+    ) -> BoxFuture<'static, ExecutionResult<()>> {
+        let children = self.children.clone();
+        Box::pin(async move {
+            let configured = std::env::var(WORKER_COMMAND_ENV).ok();
+            let mut command = worker_command(configured.as_deref())?;
+            command
+                .kill_on_drop(true)
+                .env_remove(CliConfigEnv::RUN_PYTHON)
+                .env(ClusterConfigEnv::ENABLE_TLS, options.enable_tls.to_string())
+                .env(ClusterConfigEnv::SESSION_ID, &options.session_id)
+                .env(
+                    ClusterConfigEnv::DRIVER_ID,
+                    u64::from(options.driver_id).to_string(),
+                )
+                .env(ClusterConfigEnv::WORKER_ID, u64::from(id).to_string())
+                .env(
+                    ClusterConfigEnv::DRIVER_EXTERNAL_HOST,
+                    &options.driver_external_host,
+                )
+                .env(
+                    ClusterConfigEnv::DRIVER_EXTERNAL_PORT,
+                    options.driver_external_port.to_string(),
+                )
+                .env(ClusterConfigEnv::WORKER_LISTEN_HOST, "127.0.0.1")
+                .env("SAIL_CLUSTER__WORKER_LISTEN_PORT", "0")
+                .env(ClusterConfigEnv::WORKER_EXTERNAL_HOST, "127.0.0.1")
+                .env("SAIL_CLUSTER__WORKER_EXTERNAL_PORT", "0")
+                .env(
+                    ClusterConfigEnv::WORKER_HEARTBEAT_INTERVAL_SECS,
+                    options.worker_heartbeat_interval.as_secs().to_string(),
+                )
+                .env(
+                    ClusterConfigEnv::TASK_STREAM_BUFFER,
+                    options.task_stream_buffer.to_string(),
+                )
+                .env(
+                    ClusterConfigEnv::TASK_STREAM_CREATION_TIMEOUT_SECS,
+                    options.task_stream_creation_timeout.as_secs().to_string(),
+                )
+                .env(
+                    ExecutionConfigEnv::BATCH_SIZE,
+                    options.batch_size.to_string(),
+                );
+            if let Some(path) = std::env::var_os("SAIL_EXPERIMENTAL_WORKER_PYTHONPATH") {
+                command.env("PYTHONPATH", path);
+            }
+            let child = command
+                .spawn()
+                .map_err(|e| ExecutionError::InternalError(format!("launch worker {id}: {e}")))?;
+            log::info!(
+                "extension process worker {id}: pid={:?}, driver_pid={}, session={}",
+                child.id(),
+                std::process::id(),
+                options.session_id
+            );
+            children.lock().await.push(child);
+            Ok(())
+        })
+    }
+
+    async fn stop(&self) -> ExecutionResult<()> {
+        for mut child in self.children.lock().await.drain(..) {
+            match tokio::time::timeout(Duration::from_secs(3), child.wait()).await {
+                Ok(result) => {
+                    result.map_err(|e| ExecutionError::InternalError(e.to_string()))?;
+                }
+                Err(_) => {
+                    child
+                        .kill()
+                        .await
+                        .map_err(|e| ExecutionError::InternalError(e.to_string()))?;
+                }
+            }
+        }
+        Ok(())
+    }
+}
```

## 27. crates/sail-execution/src/worker_manager/process_command.rs {#host-patch-27}

```diff
diff --git a/crates/sail-execution/src/worker_manager/process_command.rs b/crates/sail-execution/src/worker_manager/process_command.rs
new file mode 100644
index 0000000000000000000000000000000000000000..e0d60b3229585804e20b2edd47ed2c22f13966e3
--- /dev/null
+++ b/crates/sail-execution/src/worker_manager/process_command.rs
@@ -0,0 +1,63 @@
+//! Trusted startup configuration for an external worker launcher.
+use tokio::process::Command;
+
+use crate::error::{ExecutionError, ExecutionResult};
+
+pub(super) const WORKER_COMMAND_ENV: &str = "SAIL_EXPERIMENTAL_WORKER_COMMAND";
+
+/// A configured launcher receives the assigned worker/session settings through
+/// its environment. Its argv is used exactly, without a shell or appended args.
+/// The launcher must remain alive while its worker runs and stop that worker
+/// when the launcher closes. This is administrator configuration, never RPC data.
+pub(super) fn worker_command(configured: Option<&str>) -> ExecutionResult<Command> {
+    if let Some(configured) = configured {
+        let argv: Vec<String> = serde_json::from_str(configured).map_err(|error| {
+            ExecutionError::InvalidArgument(format!("{WORKER_COMMAND_ENV}: {error}"))
+        })?;
+        let Some(program) = argv.first().filter(|program| !program.is_empty()) else {
+            return Err(ExecutionError::InvalidArgument(format!(
+                "{WORKER_COMMAND_ENV} requires a nonempty executable argv"
+            )));
+        };
+        if argv.iter().any(|argument| argument.contains('\0')) {
+            return Err(ExecutionError::InvalidArgument(format!(
+                "{WORKER_COMMAND_ENV} arguments cannot contain NUL"
+            )));
+        }
+        let mut command = Command::new(program);
+        command.args(&argv[1..]);
+        Ok(command)
+    } else {
+        let executable = std::env::current_exe()
+            .map_err(|error| ExecutionError::InternalError(error.to_string()))?;
+        let mut command = Command::new(executable);
+        command.arg("worker");
+        Ok(command)
+    }
+}
+
+#[cfg(test)]
+mod tests {
+    use super::*;
+
+    #[test]
+    fn custom_worker_argv_is_literal_and_validated() -> ExecutionResult<()> {
+        let command = worker_command(Some(r#"["launcher", "$(not-a-shell)", "two words"]"#))?;
+        assert_eq!(command.as_std().get_program(), "launcher");
+        assert_eq!(
+            command.as_std().get_args().collect::<Vec<_>>(),
+            ["$(not-a-shell)", "two words"]
+        );
+        for invalid in ["[]", "{}", "[1]", r#"[""]"#, r#"["bad\u0000arg"]"#] {
+            assert!(worker_command(Some(invalid)).is_err(), "{invalid}");
+        }
+        Ok(())
+    }
+
+    #[tokio::test]
+    async fn missing_worker_launcher_is_a_launch_error() -> ExecutionResult<()> {
+        let mut command = worker_command(Some(r#"["/nonexistent-sail-worker-launcher"]"#))?;
+        assert!(command.spawn().is_err());
+        Ok(())
+    }
+}
```

## 28. crates/sail-function/src/scalar/array/spark_array.rs {#host-patch-28}

```diff
diff --git a/crates/sail-function/src/scalar/array/spark_array.rs b/crates/sail-function/src/scalar/array/spark_array.rs
index 6f7d06d735bd82cbbae33c79cddeb34d2882d03e..7b48d34316e471fa868a0b6c224201576b77b88f 100644
--- a/crates/sail-function/src/scalar/array/spark_array.rs
+++ b/crates/sail-function/src/scalar/array/spark_array.rs
@@ -9,12 +9,13 @@ use datafusion::arrow::array::{
 use datafusion::arrow::buffer::OffsetBuffer;
 use datafusion::arrow::datatypes::{DataType, Field, FieldRef};
 use datafusion_common::utils::SingleRowListArrayBuilder;
-use datafusion_common::{Result, plan_datafusion_err, plan_err};
+use datafusion_common::{Result, ScalarValue, plan_datafusion_err, plan_err};
 use datafusion_expr::type_coercion::binary::comparison_coercion;
 use datafusion_expr::{
     ColumnarValue, ReturnFieldArgs, ScalarFunctionArgs, ScalarUDFImpl, Signature, TypeSignature,
     Volatility,
 };
+use sail_common_datafusion::geometry::common_geometry_metadata;
 
 use crate::functions_nested_utils::make_scalar_function;
 
@@ -76,9 +77,29 @@ impl ScalarUDFImpl for SparkArray {
             .cloned()
             .collect::<Vec<_>>();
         let contains_null = args.arg_fields.iter().any(|f| f.is_nullable());
+        // Coercion can already have changed a NULL literal's storage type to
+        // Binary. It remains neutral when choosing the list's geometry type.
+        let alternatives = args
+            .arg_fields
+            .iter()
+            .enumerate()
+            .map(|(index, field)| {
+                if matches!(args.scalar_arguments.get(index), Some(Some(value)) if value.is_null())
+                {
+                    Arc::new(Field::new("null", DataType::Null, true))
+                } else {
+                    Arc::clone(field)
+                }
+            })
+            .collect::<Vec<_>>();
+        let metadata = common_geometry_metadata(&alternatives).unwrap_or_default();
         let return_type = match self.return_type(&data_types)? {
             DataType::List(field) => DataType::List(Arc::new(
-                field.as_ref().clone().with_nullable(contains_null),
+                field
+                    .as_ref()
+                    .clone()
+                    .with_nullable(contains_null)
+                    .with_metadata(metadata),
             )),
             data_type => data_type,
         };
@@ -93,10 +114,36 @@ impl ScalarUDFImpl for SparkArray {
             DataType::List(field) | DataType::LargeList(field) => field.is_nullable(),
             _ => true,
         };
+        let return_type = return_field.data_type().clone();
         let func = make_scalar_function(move |arrays| {
             make_array_inner_with_nullable(arrays, value_nullable)
         });
-        func(args.as_slice())
+        let result = func(args.as_slice())?;
+        if !matches!(&return_type, DataType::List(field) if !field.metadata().is_empty()) {
+            return Ok(result);
+        }
+        // Restore the descriptor after scalar conversion: DataFusion 55's
+        // SingleRowListArrayBuilder::with_field copies name/nullability but
+        // omits metadata. Both result variants must retain the planned item
+        // field, including a scalar list later broadcast to multiple rows.
+        let restore = |array: &dyn Array| {
+            array
+                .to_data()
+                .into_builder()
+                .data_type(return_type.clone())
+                .build()
+        };
+        match result {
+            ColumnarValue::Array(array) => {
+                Ok(ColumnarValue::Array(make_array(restore(array.as_ref())?)))
+            }
+            ColumnarValue::Scalar(ScalarValue::List(array)) => {
+                Ok(ColumnarValue::Scalar(ScalarValue::List(Arc::new(
+                    GenericListArray::<i32>::from(restore(array.as_ref())?),
+                ))))
+            }
+            _ => plan_err!("geometry array result must be a list"),
+        }
     }
 
     fn aliases(&self) -> &[String] {
@@ -297,3 +344,76 @@ fn array_array<O: OffsetSizeTrait>(
         None,
     )?))
 }
+
+#[cfg(test)]
+mod tests {
+    use datafusion::arrow::array::BinaryArray;
+
+    use super::*;
+
+    #[test]
+    fn geometry_array_retains_item_metadata_in_the_actual_arrow_array() -> Result<()> {
+        let geometry = Arc::new(
+            Field::new("g", DataType::Binary, true).with_metadata(
+                [
+                    ("ARROW:extension:name".into(), "geoarrow.wkb".into()),
+                    ("ARROW:extension:metadata".into(), "{}".into()),
+                ]
+                .into(),
+            ),
+        );
+        let null = ScalarValue::Binary(None);
+        let fields = vec![
+            Arc::new(Field::new("null", DataType::Binary, true)),
+            geometry.clone(),
+        ];
+        let function = SparkArray::new();
+        let returned = function.return_field_from_args(ReturnFieldArgs {
+            arg_fields: &fields,
+            scalar_arguments: &[Some(&null), None],
+        })?;
+        let DataType::List(item) = returned.data_type() else {
+            return plan_err!("expected list result");
+        };
+        assert_eq!(item.metadata(), geometry.metadata());
+        for value in [
+            ColumnarValue::Scalar(ScalarValue::Binary(Some(vec![1, 2, 3]))),
+            ColumnarValue::Array(Arc::new(BinaryArray::from(vec![Some(&[1, 2, 3][..]); 3]))),
+            ColumnarValue::Array(Arc::new(BinaryArray::from(Vec::<Option<&[u8]>>::new()))),
+        ] {
+            let is_scalar = matches!(value, ColumnarValue::Scalar(_));
+            let number_rows = match &value {
+                ColumnarValue::Scalar(_) => 3,
+                ColumnarValue::Array(array) => array.len(),
+            };
+            let result = function.invoke_with_args(ScalarFunctionArgs {
+                args: vec![ColumnarValue::Scalar(null.clone()), value],
+                arg_fields: fields.clone(),
+                number_rows,
+                return_field: returned.clone(),
+                config_options: Arc::new(Default::default()),
+            })?;
+            assert_eq!(matches!(result, ColumnarValue::Scalar(_)), is_scalar);
+            let lengths = if is_scalar {
+                vec![0, 1, 3]
+            } else {
+                vec![number_rows]
+            };
+            for length in lengths {
+                let array = result.to_array(length)?;
+                assert_eq!(array.data_type(), returned.data_type());
+                assert_eq!(array.len(), length);
+            }
+        }
+        let plain = Arc::new(Field::new("raw", DataType::Binary, true));
+        let mixed = function.return_field_from_args(ReturnFieldArgs {
+            arg_fields: &[geometry, plain],
+            scalar_arguments: &[None, None],
+        })?;
+        let DataType::List(item) = mixed.data_type() else {
+            return plan_err!("expected list result");
+        };
+        assert!(item.metadata().is_empty());
+        Ok(())
+    }
+}
```

## 29. crates/sail-native-resource-ffi/Cargo.toml {#host-patch-29}

```diff
diff --git a/crates/sail-native-resource-ffi/Cargo.toml b/crates/sail-native-resource-ffi/Cargo.toml
new file mode 100644
index 0000000000000000000000000000000000000000..b09f272ab275bd1cbd8b00a90303a4ad9517a39d
--- /dev/null
+++ b/crates/sail-native-resource-ffi/Cargo.toml
@@ -0,0 +1,9 @@
+[package]
+name = "sail-native-resource-ffi"
+version = "0.1.0"
+edition = "2024"
+license = "Apache-2.0"
+publish = false
+
+[lints]
+workspace = true
```

## 30. crates/sail-native-resource-ffi/src/lib.rs {#host-patch-30}

```diff
diff --git a/crates/sail-native-resource-ffi/src/lib.rs b/crates/sail-native-resource-ffi/src/lib.rs
new file mode 100644
index 0000000000000000000000000000000000000000..d15f735d1506f1e8775682829157f781b46266db
--- /dev/null
+++ b/crates/sail-native-resource-ffi/src/lib.rs
@@ -0,0 +1,160 @@
+//! The small C ABI shared by independently compiled native extensions and Sail.
+//! An opaque, prepaid memory lease crosses the boundary; Rust ownership and
+//! allocator layouts stay entirely inside the library that issued the lease.
+use std::ffi::{CStr, c_void};
+use std::fmt::{Debug, Formatter};
+use std::ptr::NonNull;
+use std::sync::Arc;
+
+pub const MEMORY_LEASE_CAPSULE: &CStr = c"sail_native_memory_lease_v1";
+
+#[repr(C)]
+struct Header {
+    version: u32,
+    size: u32,
+}
+
+/// A non-spillable host admission retained until the final clone is released.
+///
+/// Callbacks must be thread-safe and must never unwind. Every instance owns one
+/// reference. A consumer may inspect the header before touching versioned fields.
+#[repr(C)]
+pub struct MemoryLease {
+    header: Header,
+    bytes: u64,
+    opaque: *const c_void,
+    retain: unsafe extern "C" fn(*const c_void),
+    release: unsafe extern "C" fn(*const c_void),
+}
+
+// SAFETY: constructors require a Send + Sync owner; imports promise the same
+// thread-safe callback contract. The opaque object is never accessed here.
+unsafe impl Send for MemoryLease {}
+unsafe impl Sync for MemoryLease {}
+
+impl MemoryLease {
+    /// Export ownership through callbacks compiled in the issuing library.
+    pub fn new<T: Send + Sync + 'static>(owner: Arc<T>, bytes: u64) -> Self {
+        unsafe extern "C" fn retain<T>(opaque: *const c_void) {
+            // SAFETY: only new() constructs this token, from Arc<T>::into_raw.
+            unsafe { Arc::<T>::increment_strong_count(opaque.cast::<T>()) };
+        }
+        unsafe extern "C" fn release<T>(opaque: *const c_void) {
+            // SAFETY: each token owns one reference created by new()/retain().
+            unsafe { drop(Arc::<T>::from_raw(opaque.cast::<T>())) };
+        }
+        Self {
+            header: Header {
+                version: 1,
+                size: std::mem::size_of::<Self>() as u32,
+            },
+            bytes,
+            opaque: Arc::into_raw(owner).cast::<c_void>(),
+            retain: retain::<T>,
+            release: release::<T>,
+        }
+    }
+
+    /// Validate the ABI and quota, then take an independently releasable reference.
+    ///
+    /// # Safety
+    /// `pointer` must address a readable, aligned header. A matching header must
+    /// address a live MemoryLease with valid thread-safe, non-unwinding callbacks.
+    /// Its issuing library must remain loaded until every imported clone is gone.
+    pub unsafe fn import(
+        pointer: NonNull<c_void>,
+        expected_bytes: u64,
+    ) -> Result<Self, &'static str> {
+        // SAFETY: the caller guarantees at least the fixed header is readable.
+        let header = unsafe { pointer.cast::<Header>().as_ref() };
+        if header.version != 1 || header.size as usize != std::mem::size_of::<Self>() {
+            return Err("native memory lease ABI mismatch");
+        }
+        // SAFETY: the validated header and caller's capsule contract cover Self.
+        let lease = unsafe { pointer.cast::<Self>().as_ref() };
+        if lease.bytes != expected_bytes || lease.opaque.is_null() {
+            return Err("native memory lease quota mismatch");
+        }
+        Ok(lease.clone())
+    }
+
+    pub fn bytes(&self) -> u64 {
+        self.bytes
+    }
+}
+
+impl Clone for MemoryLease {
+    fn clone(&self) -> Self {
+        // SAFETY: self owns a live reference and callbacks obey the ABI contract.
+        unsafe { (self.retain)(self.opaque) };
+        Self {
+            header: Header {
+                version: self.header.version,
+                size: self.header.size,
+            },
+            bytes: self.bytes,
+            opaque: self.opaque,
+            retain: self.retain,
+            release: self.release,
+        }
+    }
+}
+
+impl Drop for MemoryLease {
+    fn drop(&mut self) {
+        // SAFETY: this instance owns exactly one reference, relinquished once.
+        unsafe { (self.release)(self.opaque) };
+    }
+}
+
+impl Debug for MemoryLease {
+    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
+        f.debug_struct("MemoryLease")
+            .field("version", &self.header.version)
+            .field("bytes", &self.bytes)
+            .finish_non_exhaustive()
+    }
+}
+
+#[cfg(test)]
+mod tests {
+    use std::sync::atomic::{AtomicUsize, Ordering};
+
+    use super::*;
+
+    struct Owner(Arc<AtomicUsize>);
+    impl Drop for Owner {
+        fn drop(&mut self) {
+            self.0.fetch_add(1, Ordering::SeqCst);
+        }
+    }
+
+    #[test]
+    fn imports_validate_before_clone_and_release_only_the_final_owner() -> Result<(), &'static str>
+    {
+        let drops = Arc::new(AtomicUsize::new(0));
+        let exported = MemoryLease::new(Arc::new(Owner(drops.clone())), 64);
+        let pointer = NonNull::from(&exported).cast::<c_void>();
+        // SAFETY: the exported lease remains alive during both imports.
+        assert!(unsafe { MemoryLease::import(pointer, 65) }.is_err());
+        let imported = unsafe { MemoryLease::import(pointer, 64) }?;
+        drop(exported);
+        assert_eq!(drops.load(Ordering::SeqCst), 0);
+        let output_owner = imported.clone();
+        drop(imported);
+        assert_eq!(drops.load(Ordering::SeqCst), 0);
+        std::thread::spawn(move || drop(output_owner))
+            .join()
+            .map_err(|_| "release thread failed")?;
+        assert_eq!(drops.load(Ordering::SeqCst), 1);
+        let wrong = Header {
+            version: 2,
+            size: 8,
+        };
+        // SAFETY: a rejected version only reads the fixed header.
+        assert!(
+            unsafe { MemoryLease::import(NonNull::from(&wrong).cast::<c_void>(), 64) }.is_err()
+        );
+        Ok(())
+    }
+}
```

## 31. crates/sail-plan/src/function/mod.rs {#host-patch-31}

```diff
diff --git a/crates/sail-plan/src/function/mod.rs b/crates/sail-plan/src/function/mod.rs
index ba4406d5ae15923ac5d0970023d776e6386b0346..1e2726f9ba054bf4ca36588bcbe255871ad5a79e 100644
--- a/crates/sail-plan/src/function/mod.rs
+++ b/crates/sail-plan/src/function/mod.rs
@@ -54,6 +54,11 @@ pub fn is_built_in_generator_function(name: &str) -> bool {
     BUILT_IN_GENERATOR_FUNCTIONS.contains_key(name)
 }
 
+/// Includes every built-in function kind for extension collision validation.
+pub fn is_built_in_function_name(name: &str) -> bool {
+    list_built_in_function_names().contains(&name)
+}
+
 fn list_built_in_function_names() -> Vec<&'static str> {
     let mut names = BUILT_IN_SCALAR_FUNCTIONS
         .keys()
```

## 32. crates/sail-plan/src/resolver/expression/geometry.rs {#host-patch-32}

```diff
diff --git a/crates/sail-plan/src/resolver/expression/geometry.rs b/crates/sail-plan/src/resolver/expression/geometry.rs
new file mode 100644
index 0000000000000000000000000000000000000000..ef86e807096673038bab8f13e57e242819d71a8d
--- /dev/null
+++ b/crates/sail-plan/src/resolver/expression/geometry.rs
@@ -0,0 +1,155 @@
+//! Keep logical geometry types through value-preserving SQL expressions.
+use std::sync::Arc;
+
+use arrow::datatypes::{DataType, Field};
+use datafusion_common::tree_node::{Transformed, TreeNode};
+use datafusion_common::{DFSchema, Result};
+use datafusion_expr::expr::Cast;
+use datafusion_expr::{Expr, ExprSchemable};
+use sail_common_datafusion::geometry::common_geometry_metadata;
+
+/// DataFusion 55's CASE, coalesce and array_element infer only storage types.
+/// An explicit-field identity cast preserves the selected logical type through
+/// both logical simplification (coalesce becomes CASE) and physical planning.
+pub(super) fn preserve_geometry(expr: Expr, schema: &DFSchema) -> Result<Expr> {
+    // Expressions already repaired while resolving an argument need no second
+    // traversal. User type-only casts still strip geometry metadata normally.
+    if matches!(&expr, Expr::Cast(cast) if !cast.field.metadata().is_empty()) {
+        return Ok(expr);
+    }
+    let mut expr = expr
+        .map_children(|child| preserve_geometry(child, schema).map(Transformed::yes))?
+        .data;
+    let alternatives: Vec<&Expr> = match &expr {
+        Expr::Case(case) => case
+            .when_then_expr
+            .iter()
+            .map(|(_, value)| value.as_ref())
+            .chain(case.else_expr.iter().map(|value| value.as_ref()))
+            .collect(),
+        Expr::ScalarFunction(function) if function.func.name() == "coalesce" => {
+            function.args.iter().collect()
+        }
+        Expr::ScalarFunction(function) if function.func.name() == "array_element" => {
+            let Some(input) = function.args.first() else {
+                return Ok(expr);
+            };
+            let Ok(data_type) = input.get_type(schema) else {
+                return Ok(expr); // An enclosing higher-order lambda may be unresolved.
+            };
+            let field = match data_type {
+                DataType::List(field)
+                | DataType::LargeList(field)
+                | DataType::FixedSizeList(field, _)
+                | DataType::ListView(field)
+                | DataType::LargeListView(field) => field,
+                _ => return Ok(expr),
+            };
+            if let Some(metadata) = common_geometry_metadata(std::slice::from_ref(&field)) {
+                let field = Arc::new(
+                    field
+                        .as_ref()
+                        .clone()
+                        .with_nullable(true)
+                        .with_metadata(metadata),
+                );
+                return Ok(Expr::Cast(Cast::new_from_field(Box::new(expr), field)));
+            }
+            return Ok(expr);
+        }
+        _ => return Ok(expr),
+    };
+    let fields = alternatives
+        .iter()
+        .map(|value| {
+            // A typed NULL cannot change the geometry/CRS selected by other arms.
+            if is_null_literal(value) {
+                Ok(Arc::new(Field::new("null", DataType::Null, true)))
+            } else {
+                value.to_field(schema).map(|(_, field)| field)
+            }
+        })
+        .collect::<Result<Vec<_>>>();
+    let Ok(fields) = fields else {
+        return Ok(expr); // Defer free lambda variables to their enclosing resolver.
+    };
+    let Some(metadata) = common_geometry_metadata(&fields) else {
+        return Ok(expr);
+    };
+    // DataFusion 55's coalesce coercion accepts equal Binary storage types,
+    // but excludes Binary when resolving the union of Binary and Null. Type
+    // only untyped NULL operands after establishing a common geometry type;
+    // this neither relabels ordinary binary values nor changes null semantics.
+    if let Expr::ScalarFunction(function) = &mut expr
+        && function.func.name() == "coalesce"
+        && let Some(field) = fields.iter().find(|field| !field.data_type().is_null())
+    {
+        for argument in &mut function.args {
+            if argument.get_type(schema)?.is_null() {
+                *argument = Expr::Cast(Cast::new(
+                    Box::new(argument.clone()),
+                    field.data_type().clone(),
+                ));
+            }
+        }
+    }
+    let field = Arc::new(
+        Field::new("", expr.get_type(schema)?, expr.nullable(schema)?).with_metadata(metadata),
+    );
+    Ok(Expr::Cast(Cast::new_from_field(Box::new(expr), field)))
+}
+
+fn is_null_literal(expr: &Expr) -> bool {
+    match expr {
+        Expr::Literal(value, _) => value.is_null(),
+        Expr::Cast(cast) => is_null_literal(&cast.expr),
+        Expr::TryCast(cast) => is_null_literal(&cast.expr),
+        Expr::Alias(alias) => is_null_literal(&alias.expr),
+        // ANSI extraction inserts a typed raise_error arm. It produces no
+        // value and therefore cannot change the type of a successful result.
+        Expr::ScalarFunction(function) => function
+            .func
+            .inner()
+            .is::<sail_function::scalar::misc::raise_error::RaiseError>(
+        ),
+        _ => false,
+    }
+}
+
+#[cfg(test)]
+mod tests {
+    use arrow::datatypes::Schema;
+    use datafusion_expr::{col, lit, when};
+
+    use super::*;
+
+    #[test]
+    fn selectors_preserve_geometry_but_do_not_type_plain_binary() -> Result<()> {
+        let field = Field::new("g", DataType::Binary, true).with_metadata(
+            [
+                ("ARROW:extension:name".into(), "geoarrow.wkb".into()),
+                ("ARROW:extension:metadata".into(), "{}".into()),
+            ]
+            .into(),
+        );
+        let schema = DFSchema::try_from(Schema::new(vec![
+            field.clone(),
+            Field::new("raw", DataType::Binary, true),
+        ]))?;
+        let case = when(col("g").is_not_null(), col("g")).end()?;
+        let fixed = preserve_geometry(case, &schema)?;
+        assert_eq!(fixed.to_field(&schema)?.1.metadata(), field.metadata());
+        for alternatives in [
+            vec![col("g"), lit(datafusion_common::ScalarValue::Null)],
+            vec![lit(datafusion_common::ScalarValue::Null), col("g")],
+        ] {
+            let coalesce = datafusion::functions::expr_fn::coalesce(alternatives);
+            let fixed = preserve_geometry(coalesce, &schema)?;
+            assert_eq!(fixed.to_field(&schema)?.1.metadata(), field.metadata());
+        }
+        let mixed = when(col("g").is_not_null(), col("g")).otherwise(col("raw"))?;
+        let fixed = preserve_geometry(mixed, &schema)?;
+        assert!(fixed.to_field(&schema)?.1.metadata().is_empty());
+        Ok(())
+    }
+}
```

## 33. crates/sail-plan/src/resolver/expression/mod.rs {#host-patch-33}

```diff
diff --git a/crates/sail-plan/src/resolver/expression/mod.rs b/crates/sail-plan/src/resolver/expression/mod.rs
index ebc311789d228ed576facafaaa10d1b012d8bda1..b7af74d60c9c7905745052f8f48acd33bbba4946 100644
--- a/crates/sail-plan/src/resolver/expression/mod.rs
+++ b/crates/sail-plan/src/resolver/expression/mod.rs
@@ -13,6 +13,7 @@ use crate::resolver::state::PlanResolverState;
 mod attribute;
 mod cast;
 mod function;
+mod geometry;
 mod grouping;
 mod lambda;
 mod literal;
@@ -106,7 +107,7 @@ impl PlanResolver<'_> {
     ) -> PlanResult<NamedExpr> {
         use spec::Expr;
 
-        match expr {
+        let mut result = match expr {
             Expr::Literal(literal) => self.resolve_expression_literal(literal, state),
             Expr::UnresolvedAttribute {
                 name,
@@ -340,7 +341,9 @@ impl PlanResolver<'_> {
             Expr::NamedArgument { .. } => Err(PlanError::invalid(
                 "named argument expression can only be used in UDF arguments",
             )),
-        }
+        }?;
+        result.expr = geometry::preserve_geometry(result.expr, schema)?;
+        Ok(result)
     }
 
     pub(super) async fn resolve_named_expressions(
```

## 34. crates/sail-plan/src/resolver/query/extension.rs {#host-patch-34}

```diff
diff --git a/crates/sail-plan/src/resolver/query/extension.rs b/crates/sail-plan/src/resolver/query/extension.rs
new file mode 100644
index 0000000000000000000000000000000000000000..c79c5ae407bb0a0a2d8a20e3bd633b7c3ac729c0
--- /dev/null
+++ b/crates/sail-plan/src/resolver/query/extension.rs
@@ -0,0 +1,59 @@
+use std::collections::HashSet;
+use std::sync::Arc;
+
+use datafusion_expr::{LogicalPlan, UNNAMED_TABLE};
+use sail_common::spec;
+use sail_common_datafusion::connect_extension::{ConnectExtensionRegistry, HostInputExec};
+use sail_common_datafusion::extension::SessionExtensionAccessor;
+use sail_common_datafusion::rename::logical_plan::rename_logical_plan;
+
+use crate::error::{PlanError, PlanResult};
+use crate::resolver::PlanResolver;
+use crate::resolver::state::PlanResolverState;
+
+impl PlanResolver<'_> {
+    pub(super) async fn resolve_query_extension(
+        &self,
+        payload_type_url: String,
+        payload: Vec<u8>,
+        inputs: Vec<spec::QueryPlan>,
+        is_envelope: bool,
+        state: &mut PlanResolverState,
+    ) -> PlanResult<LogicalPlan> {
+        let registry = self.ctx.extension::<ConnectExtensionRegistry>()?;
+        let handler = registry.resolve(&payload_type_url, is_envelope, inputs.len())?;
+        let session = self.ctx.state();
+        let context = self.ctx.task_ctx();
+        let runtime = tokio::runtime::Handle::try_current().map_err(|error| {
+            PlanError::internal(format!(
+                "Connect extension planning requires the host runtime: {error}"
+            ))
+        })?;
+        let mut physical_inputs = Vec::with_capacity(inputs.len());
+        for input in inputs {
+            let plan = self.resolve_query_plan(input, state).await?;
+            let names = Self::get_field_names(plan.schema(), state)?;
+            let mut seen = HashSet::new();
+            if names.iter().any(|name| !seen.insert(name)) {
+                return Err(PlanError::unsupported(format!(
+                    "duplicate input column names for Connect extension {payload_type_url}; alias the input columns"
+                )));
+            }
+            // Extensions receive public DataFrame names, never Sail's internal
+            // field IDs. Restoring names before planning also preserves expression
+            // binding through the normal physical planner.
+            let plan = rename_logical_plan(plan, &names)?;
+            let physical = session.create_physical_plan(&plan).await?;
+            physical_inputs.push(Arc::new(HostInputExec::new(
+                physical,
+                Arc::clone(&context),
+                runtime.clone(),
+            ))
+                as Arc<dyn datafusion::physical_plan::ExecutionPlan>);
+        }
+        // No input is executed here. A provider's scan must return a lazy plan;
+        // this path is also used by Spark Connect AnalyzePlan.
+        let provider = handler.plan(&payload, physical_inputs)?;
+        self.resolve_table_provider_with_rename(provider, UNNAMED_TABLE, None, vec![], None, state)
+    }
+}
```

## 35. crates/sail-plan/src/resolver/query/mod.rs {#host-patch-35}

```diff
diff --git a/crates/sail-plan/src/resolver/query/mod.rs b/crates/sail-plan/src/resolver/query/mod.rs
index fb117e5bcd292ab02a4ac548a9894901426c8558..35507d68c24fc3685fab3c70eaea0143c99da237 100644
--- a/crates/sail-plan/src/resolver/query/mod.rs
+++ b/crates/sail-plan/src/resolver/query/mod.rs
@@ -17,6 +17,7 @@ mod alias;
 mod column_op;
 mod cte;
 mod dedup;
+mod extension;
 mod filter;
 mod join;
 mod lateral;
@@ -69,6 +70,15 @@ impl PlanResolver<'_> {
 
         let plan_id = plan.plan_id;
         let plan = match plan.node {
+            QueryNode::Extension {
+                payload_type_url,
+                payload,
+                inputs,
+                is_envelope,
+            } => {
+                self.resolve_query_extension(payload_type_url, payload, inputs, is_envelope, state)
+                    .await?
+            }
             QueryNode::Read {
                 read_type,
                 is_streaming: _,
```

## 36. crates/sail-session/Cargo.toml {#host-patch-36}

```diff
diff --git a/crates/sail-session/Cargo.toml b/crates/sail-session/Cargo.toml
index c959dda31102b60919cddee8ac9b7b58021e8d66..581934556b4aa70bfa0a3e121d8b1cc50214a279 100644
--- a/crates/sail-session/Cargo.toml
+++ b/crates/sail-session/Cargo.toml
@@ -41,6 +41,11 @@ datafusion = { workspace = true }
 datafusion-common = { workspace = true }
 datafusion-datasource = { workspace = true }
 datafusion-expr = { workspace = true }
+datafusion-ffi = { workspace = true }
+arrow-schema = { workspace = true }
+pyo3 = { workspace = true }
+serde = { workspace = true }
+serde_json = { workspace = true }
 datafusion-physical-expr = { workspace = true }
 object_store = { workspace = true }
 secrecy = { workspace = true }
@@ -50,6 +55,11 @@ chrono = { workspace = true }
 indexmap = { workspace = true }
 futures = { workspace = true }
 uuid = { workspace = true }
+prost = { workspace = true }
+url = { workspace = true }
+
+[build-dependencies]
+prost-build = { workspace = true }
 
 [dev-dependencies]
 tempfile = { workspace = true }
```

## 37. crates/sail-session/build.rs {#host-patch-37}

```diff
diff --git a/crates/sail-session/build.rs b/crates/sail-session/build.rs
new file mode 100644
index 0000000000000000000000000000000000000000..8d7a2311dbfd0143509a6bb8c0e0b6f80ef3e99f
--- /dev/null
+++ b/crates/sail-session/build.rs
@@ -0,0 +1,6 @@
+fn main() -> Result<(), Box<dyn std::error::Error>> {
+    let proto = "proto";
+    println!("cargo:rerun-if-changed={proto}/gf/utils/v1/utils.proto");
+    prost_build::compile_protos(&[format!("{proto}/gf/utils/v1/utils.proto")], &[proto])?;
+    Ok(())
+}
```

## 38. crates/sail-session/proto/gf/utils/v1/utils.proto {#host-patch-38}

```diff
diff --git a/crates/sail-session/proto/gf/utils/v1/utils.proto b/crates/sail-session/proto/gf/utils/v1/utils.proto
new file mode 100644
index 0000000000000000000000000000000000000000..d3829bc7aa524f1639b1f5f0e8d5c1b8fd15a273
--- /dev/null
+++ b/crates/sail-session/proto/gf/utils/v1/utils.proto
@@ -0,0 +1,39 @@
+syntax = "proto3";
+package gf.utils.v1;
+
+// Zero-input Relation.extension, collected eagerly. This is an experimental
+// contract; protocol_version in every receipt is 1. No effects during analysis.
+message Request {
+  oneof verb {
+    Ping ping = 1;
+    Exists exists = 2;
+    Ls ls = 3;
+    Rm rm = 4;
+    Mkdir mkdir = 5;
+  }
+}
+message Ping { string client_version = 1; }
+message Exists { string path = 1; string token = 2; }
+message Ls { string path = 1; uint32 limit = 2; string token = 3; }
+message Rm { string path = 1; string token = 2; }
+// Empty root uses the configured root. A retry with the same UUID returns the
+// same run within this server session; an already released run cannot reopen.
+message Mkdir { string root = 1; string request_id = 2; }
+
+// Response is Arrow, not a protobuf Receipt. All verbs return the same schema:
+// kind: utf8 non-null, path: utf8 nullable, size: int64 nullable,
+// value: bool nullable, count: int64 nullable, capabilities: utf8 nullable,
+// token: utf8 nullable, truncated: bool non-null, engine: utf8 non-null,
+// protocol_version: int32 non-null, lease_seconds: int64 non-null.
+// Ping: kind=pong, path=root, capabilities=JSON string array.
+// Mkdir: kind=mkdir, path=run URI, token=opaque capability.
+// Exists: kind=exists, path=request path, value=prefix exists.
+// Rm: kind=rm, path=request path, count=objects removed; repeated remove is safe.
+// Ls: kind=entry rows (path,size), followed by exactly one kind=ls row with count
+// and truncated. limit is 1..1000, default 100; internal ownership markers hidden.
+// lease_seconds=0: ownership lasts for this server session. Explicit Rm(run)
+// releases it; session expiration/close requests job shutdown, then attempts
+// best-effort cleanup with bounded storage-error retries. Detached writers are
+// not fully joined; interrupted writes may require operator cleanup of late files.
+// A URI under the configured root alone is NOT authority: all FS verbs require
+// the matching run token in the same session. Root deletion is always rejected.
```

## 39. crates/sail-session/src/extensions/driver.rs {#host-patch-39}

```diff
diff --git a/crates/sail-session/src/extensions/driver.rs b/crates/sail-session/src/extensions/driver.rs
new file mode 100644
index 0000000000000000000000000000000000000000..5fb28b6769b689e1d9e3562494040bab48fcd8af
--- /dev/null
+++ b/crates/sail-session/src/extensions/driver.rs
@@ -0,0 +1,240 @@
+//! Keep a frozen native region on the driver while exposing its host inputs to
+//! Sail's stage planner. Task decoding reuses the original read snapshot/write
+//! attempt, and task execution substitutes prepared shuffle inputs across FFI.
+use std::fmt::{Debug, Formatter};
+use std::sync::{Arc, Mutex};
+
+use arrow_schema::SchemaRef;
+use async_trait::async_trait;
+use datafusion::catalog::{Session, TableProvider};
+use datafusion::execution::{SendableRecordBatchStream, TaskContext};
+use datafusion::physical_plan::{DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties};
+use datafusion_common::{Result, plan_err};
+use datafusion_expr::{Expr, TableType};
+use sail_common_datafusion::connect_extension::HostInputExec;
+use sail_common_datafusion::driver_extension::{
+    BoundDriverPlan, DriverDescriptor, DriverExtensionBinding, DriverExtensionExec,
+    DriverExtensionRegistry,
+};
+
+#[derive(Debug)]
+pub(super) struct InputPlaceholder {
+    pub name: String,
+    pub properties: Arc<PlanProperties>,
+}
+
+impl DisplayAs for InputPlaceholder {
+    fn fmt_as(&self, _: DisplayFormatType, f: &mut Formatter<'_>) -> std::fmt::Result {
+        write!(f, "{}", self.name)
+    }
+}
+
+impl ExecutionPlan for InputPlaceholder {
+    fn apply_expressions(
+        &self,
+        _f: &mut dyn FnMut(
+            &Arc<dyn datafusion::physical_expr::PhysicalExpr>,
+        ) -> Result<datafusion_common::tree_node::TreeNodeRecursion>,
+    ) -> Result<datafusion_common::tree_node::TreeNodeRecursion> {
+        Ok(datafusion_common::tree_node::TreeNodeRecursion::Continue)
+    }
+    fn name(&self) -> &str {
+        &self.name
+    }
+    fn properties(&self) -> &Arc<PlanProperties> {
+        &self.properties
+    }
+    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
+        vec![]
+    }
+    fn with_new_children(
+        self: Arc<Self>,
+        children: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        if !children.is_empty() {
+            return plan_err!("native input placeholder has no children");
+        }
+        Ok(self)
+    }
+    fn execute(&self, _: usize, _: Arc<TaskContext>) -> Result<SendableRecordBatchStream> {
+        plan_err!("native input placeholder must be bound before execution")
+    }
+}
+
+#[derive(Debug)]
+pub(super) struct DriverTableProvider {
+    pub inner: Arc<dyn TableProvider>,
+    pub inputs: Vec<Arc<dyn ExecutionPlan>>,
+    pub names: Vec<String>,
+    pub owner: String,
+    pub registry: Arc<DriverExtensionRegistry>,
+}
+
+#[async_trait]
+impl TableProvider for DriverTableProvider {
+    fn schema(&self) -> SchemaRef {
+        self.inner.schema()
+    }
+    fn table_type(&self) -> TableType {
+        self.inner.table_type()
+    }
+    async fn scan(
+        &self,
+        session: &dyn Session,
+        projection: Option<&Vec<usize>>,
+        filters: &[Expr],
+        limit: Option<usize>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        let native = self.inner.scan(session, projection, filters, limit).await?;
+        if native.properties().partitioning.partition_count() != 1 {
+            return plan_err!("driver-only native relation must produce exactly one partition");
+        }
+        let bound = Arc::new(BoundDriverPlan {
+            descriptor: DriverDescriptor {
+                owner: self.owner.clone(),
+                plan_id: uuid::Uuid::new_v4().to_string(),
+            },
+            properties: native.properties().clone(),
+            input_schemas: self.inputs.iter().map(|input| input.schema()).collect(),
+            binding: Arc::new(NativeBinding {
+                resources: Mutex::new(Some(NativeResources {
+                    native,
+                    _provider: self.inner.clone(),
+                })),
+                names: self.names.clone(),
+            }),
+        });
+        self.registry.register(&bound)?;
+        Ok(Arc::new(DriverExtensionExec::new(
+            bound,
+            self.inputs.clone(),
+        )?))
+    }
+}
+
+#[derive(Debug)]
+struct NativeBinding {
+    resources: Mutex<Option<NativeResources>>,
+    names: Vec<String>,
+}
+
+#[derive(Debug)]
+struct NativeResources {
+    native: Arc<dyn ExecutionPlan>,
+    _provider: Arc<dyn TableProvider>,
+}
+
+impl DriverExtensionBinding for NativeBinding {
+    fn close(&self) {
+        if let Ok(mut resources) = self.resources.lock() {
+            resources.take();
+        }
+    }
+    fn materialize(
+        &self,
+        inputs: &[Arc<dyn ExecutionPlan>],
+        context: Arc<TaskContext>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        let native = self
+            .resources
+            .lock()
+            .map_err(|_| {
+                datafusion_common::plan_datafusion_err!("native plan lifetime lock poisoned")
+            })?
+            .as_ref()
+            .ok_or_else(|| {
+                datafusion_common::plan_datafusion_err!("native driver query has already finished")
+            })?
+            .native
+            .clone();
+        let runtime = tokio::runtime::Handle::try_current().map_err(|e| {
+            datafusion_common::plan_datafusion_err!("driver native runtime missing: {e}")
+        })?;
+        let replacements: Vec<Arc<dyn ExecutionPlan>> = inputs
+            .iter()
+            .map(|input| {
+                Arc::new(HostInputExec::new(
+                    input.clone(),
+                    context.clone(),
+                    runtime.clone(),
+                )) as Arc<dyn ExecutionPlan>
+            })
+            .collect();
+        fn substitute(
+            plan: Arc<dyn ExecutionPlan>,
+            names: &[String],
+            replacements: &[Arc<dyn ExecutionPlan>],
+            seen: &mut [bool],
+        ) -> Result<Arc<dyn ExecutionPlan>> {
+            if let Some(index) = names.iter().position(|name| name == plan.name()) {
+                if plan.schema() != replacements[index].schema() {
+                    return plan_err!("native input placeholder schema changed");
+                }
+                seen[index] = true;
+                return Ok(replacements[index].clone());
+            }
+            let children = plan.children();
+            if children.is_empty() {
+                return Ok(plan);
+            }
+            let replaced = children
+                .iter()
+                .map(|child| substitute((*child).clone(), names, replacements, seen))
+                .collect::<Result<Vec<_>>>()?;
+            if children
+                .iter()
+                .zip(&replaced)
+                .all(|(before, after)| Arc::ptr_eq(before, after))
+            {
+                return Ok(plan);
+            }
+            plan.replace_children(
+                replaced,
+                datafusion::physical_plan::ReplaceChildrenOptions::new(
+                    datafusion::physical_plan::execution_plan::ChildrenPropertiesMode::Recompute,
+                ),
+            )
+        }
+        let mut seen = vec![false; self.names.len()];
+        let plan = substitute(native, &self.names, &replacements, &mut seen)?;
+        if seen.iter().any(|value| !value) {
+            return plan_err!("native relation lost a declared host input");
+        }
+        Ok(plan)
+    }
+}
+
+#[cfg(test)]
+mod tests {
+    use datafusion::datasource::empty::EmptyTable;
+    use datafusion::physical_plan::empty::EmptyExec;
+
+    use super::*;
+
+    #[tokio::test]
+    async fn driver_binding_releases_archived_snapshot_but_keeps_inflight_plan_alive() -> Result<()>
+    {
+        let schema = Arc::new(arrow_schema::Schema::empty());
+        let native: Arc<dyn ExecutionPlan> = Arc::new(EmptyExec::new(schema.clone()));
+        let weak = Arc::downgrade(&native);
+        let binding = NativeBinding {
+            resources: Mutex::new(Some(NativeResources {
+                native,
+                _provider: Arc::new(EmptyTable::new(schema)),
+            })),
+            names: vec![],
+        };
+        let inflight = binding.materialize(&[], Arc::new(TaskContext::default()))?;
+        binding.close();
+        assert!(weak.upgrade().is_some());
+        assert!(
+            binding
+                .materialize(&[], Arc::new(TaskContext::default()))
+                .is_err()
+        );
+        drop(inflight);
+        assert!(weak.upgrade().is_none());
+        binding.close();
+        Ok(())
+    }
+}
```

## 40. crates/sail-session/src/extensions/graph_utils/cleanup_tests.rs {#host-patch-40}

```diff
diff --git a/crates/sail-session/src/extensions/graph_utils/cleanup_tests.rs b/crates/sail-session/src/extensions/graph_utils/cleanup_tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..f9c0afdf7e5917c63b0595cfa2577a60f3f646c0
--- /dev/null
+++ b/crates/sail-session/src/extensions/graph_utils/cleanup_tests.rs
@@ -0,0 +1,144 @@
+use std::sync::Arc;
+use std::sync::atomic::{AtomicUsize, Ordering};
+
+use async_trait::async_trait;
+use datafusion::execution::runtime_env::RuntimeEnv;
+use datafusion_common::{Result, plan_datafusion_err};
+use futures::TryStreamExt;
+use futures::stream::BoxStream;
+use object_store::memory::InMemory;
+use object_store::path::Path;
+use object_store::{
+    CopyOptions, GetOptions, GetResult, ListResult, MultipartUpload, ObjectMeta, ObjectStore,
+    PutMultipartOptions, PutOptions, PutPayload, PutResult,
+};
+
+use super::proto::request::Verb;
+use super::proto::{Mkdir, Request};
+use super::storage::GraphRuns;
+
+#[derive(Debug)]
+struct FailLists {
+    inner: InMemory,
+    failures_remaining: AtomicUsize,
+    list_calls: AtomicUsize,
+}
+impl std::fmt::Display for FailLists {
+    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
+        f.write_str("FailLists")
+    }
+}
+#[async_trait]
+impl ObjectStore for FailLists {
+    async fn put_opts(
+        &self,
+        path: &Path,
+        payload: PutPayload,
+        opts: PutOptions,
+    ) -> object_store::Result<PutResult> {
+        self.inner.put_opts(path, payload, opts).await
+    }
+    async fn put_multipart_opts(
+        &self,
+        path: &Path,
+        opts: PutMultipartOptions,
+    ) -> object_store::Result<Box<dyn MultipartUpload>> {
+        self.inner.put_multipart_opts(path, opts).await
+    }
+    async fn get_opts(&self, path: &Path, opts: GetOptions) -> object_store::Result<GetResult> {
+        self.inner.get_opts(path, opts).await
+    }
+    fn delete_stream(
+        &self,
+        locations: BoxStream<'static, object_store::Result<Path>>,
+    ) -> BoxStream<'static, object_store::Result<Path>> {
+        self.inner.delete_stream(locations)
+    }
+    fn list(&self, prefix: Option<&Path>) -> BoxStream<'static, object_store::Result<ObjectMeta>> {
+        self.list_calls.fetch_add(1, Ordering::SeqCst);
+        if self
+            .failures_remaining
+            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |remaining| {
+                remaining.checked_sub(1)
+            })
+            .is_ok()
+        {
+            Box::pin(futures::stream::once(async {
+                Err(object_store::Error::Generic {
+                    store: "FailLists",
+                    source: std::io::Error::other("injected list failure").into(),
+                })
+            }))
+        } else {
+            self.inner.list(prefix)
+        }
+    }
+    async fn list_with_delimiter(&self, prefix: Option<&Path>) -> object_store::Result<ListResult> {
+        self.inner.list_with_delimiter(prefix).await
+    }
+    async fn copy_opts(
+        &self,
+        from: &Path,
+        to: &Path,
+        opts: CopyOptions,
+    ) -> object_store::Result<()> {
+        self.inner.copy_opts(from, to, opts).await
+    }
+}
+
+async fn fixture() -> Result<(GraphRuns, Arc<FailLists>)> {
+    let runtime = RuntimeEnv::default();
+    let store = Arc::new(FailLists {
+        inner: InMemory::new(),
+        failures_remaining: AtomicUsize::new(0),
+        list_calls: AtomicUsize::new(0),
+    });
+    runtime.register_object_store(
+        &url::Url::parse("memory:///").map_err(|e| plan_datafusion_err!("{e}"))?,
+        store.clone(),
+    );
+    let runs = GraphRuns::new(&runtime, "memory:///graphs")?;
+    for _ in 0..3 {
+        runs.execute(Request {
+            verb: Some(Verb::Mkdir(Mkdir {
+                root: String::new(),
+                request_id: uuid::Uuid::new_v4().to_string(),
+            })),
+        })
+        .await?;
+    }
+    Ok((runs, store))
+}
+
+#[tokio::test]
+async fn production_cleanup_retries_a_transient_store_failure_and_attempts_every_run() -> Result<()>
+{
+    let (runs, store) = fixture().await?;
+    store.failures_remaining.store(1, Ordering::SeqCst);
+    // Exercise exactly the method called by session teardown: no manual retry.
+    runs.cleanup().await?;
+    // First pass attempts all three runs despite its first failure. A second
+    // pass revisits every run, including those already cleaned successfully.
+    assert_eq!(store.list_calls.load(Ordering::SeqCst), 6);
+    assert!(store.inner.list(None).try_next().await?.is_none());
+    Ok(())
+}
+
+#[tokio::test]
+async fn production_cleanup_stops_after_bounded_attempts_and_preserves_failure() -> Result<()> {
+    let (runs, store) = fixture().await?;
+    store.failures_remaining.store(100, Ordering::SeqCst);
+    let error = runs
+        .cleanup()
+        .await
+        .err()
+        .ok_or_else(|| plan_datafusion_err!("cleanup unexpectedly succeeded"))?;
+    assert!(error.to_string().contains("exhausted 3 attempts"));
+    assert!(error.to_string().contains("injected list failure"));
+    assert_eq!(store.list_calls.load(Ordering::SeqCst), 9);
+    assert_eq!(
+        store.inner.list(None).try_collect::<Vec<_>>().await?.len(),
+        3
+    );
+    Ok(())
+}
```

## 41. crates/sail-session/src/extensions/graph_utils/functions.rs {#host-patch-41}

```diff
diff --git a/crates/sail-session/src/extensions/graph_utils/functions.rs b/crates/sail-session/src/extensions/graph_utils/functions.rs
new file mode 100644
index 0000000000000000000000000000000000000000..9caa557a5a0b940cd01754c7b735cd09e7f1ad5f
--- /dev/null
+++ b/crates/sail-session/src/extensions/graph_utils/functions.rs
@@ -0,0 +1,98 @@
+use std::sync::Arc;
+
+use datafusion::arrow::array::{Array, Int64Array};
+use datafusion::arrow::datatypes::DataType;
+use datafusion_common::{Result, ScalarValue, exec_datafusion_err};
+use datafusion_expr::{ColumnarValue, ScalarUDF, Volatility, create_udf};
+use sail_common_datafusion::native_scalar::{OwnedScalar, retain_scalar};
+
+// Carry-less multiplication modulo x^64 + x^4 + x^3 + x + 1. Signed SQL
+// BIGINTs represent all 64 bit patterns; wrapping is polynomial arithmetic.
+fn multiply(mut a: u64, mut x: u64) -> u64 {
+    let mut result = 0;
+    for _ in 0..64 {
+        result ^= a & (0_u64.wrapping_sub(x & 1));
+        let high = a >> 63;
+        a = (a << 1) ^ (0x1b & (0_u64.wrapping_sub(high)));
+        x >>= 1;
+    }
+    result
+}
+
+pub(super) fn register() -> Result<Vec<ScalarUDF>> {
+    let axpb = create_udf(
+        "gf_axpb",
+        vec![DataType::Int64; 3],
+        DataType::Int64,
+        Volatility::Immutable,
+        Arc::new(|args| {
+            let arrays = ColumnarValue::values_to_arrays(args)?;
+            let arrays = arrays
+                .iter()
+                .map(|array| {
+                    array.as_any().downcast_ref::<Int64Array>().ok_or_else(|| {
+                        exec_datafusion_err!("gf_axpb requires three BIGINT arguments")
+                    })
+                })
+                .collect::<Result<Vec<_>>>()?;
+            if arrays.len() != 3 {
+                return Err(exec_datafusion_err!(
+                    "gf_axpb requires three BIGINT arguments"
+                ));
+            }
+            let result = Int64Array::from_iter((0..arrays[0].len()).map(|i| {
+                if arrays.iter().any(|a| a.is_null(i)) {
+                    None
+                } else {
+                    Some(
+                        (multiply(arrays[0].value(i) as u64, arrays[1].value(i) as u64)
+                            ^ arrays[2].value(i) as u64) as i64,
+                    )
+                }
+            }));
+            Ok(ColumnarValue::Array(Arc::new(result)))
+        }),
+    );
+    let version = create_udf(
+        "gf_version",
+        vec![],
+        DataType::Utf8,
+        Volatility::Immutable,
+        Arc::new(|_| {
+            Ok(ColumnarValue::Scalar(ScalarValue::Utf8(Some(
+                "sail-gf-utils/1".into(),
+            ))))
+        }),
+    );
+    [axpb, version]
+        .into_iter()
+        .map(|udf| {
+            let scalar = ScalarUDF::new_from_impl(OwnedScalar {
+                name: udf.name().into(),
+                identity: "sail-gf-utils/1:gf64-polynomial-1b".into(),
+                udf,
+                owner: Arc::new(()),
+            });
+            retain_scalar(scalar.clone())?;
+            Ok(scalar)
+        })
+        .collect()
+}
+
+#[cfg(test)]
+mod tests {
+    use super::*;
+    #[test]
+    fn gf64_vectors_and_field_properties() {
+        assert_eq!(multiply(1 << 63, 2), 0x1b);
+        assert_eq!(multiply(u64::MAX, 2), 0xffff_ffff_ffff_ffe5);
+        assert_eq!(multiply(0, u64::MAX), 0);
+        assert_eq!(multiply(1, u64::MAX), u64::MAX);
+        for a in [0, 1, 2, 0x83, 1 << 63, u64::MAX] {
+            for x in [0, 1, 2, 0xaabb_ccdd_1122_3344, u64::MAX] {
+                assert_eq!(multiply(a, x), multiply(x, a));
+                assert_eq!(multiply(a, x ^ 0x42), multiply(a, x) ^ multiply(a, 0x42));
+            }
+        }
+    }
+}
```

## 42. crates/sail-session/src/extensions/graph_utils/local.rs {#host-patch-42}

```diff
diff --git a/crates/sail-session/src/extensions/graph_utils/local.rs b/crates/sail-session/src/extensions/graph_utils/local.rs
new file mode 100644
index 0000000000000000000000000000000000000000..4ab437ad40bf08a97e263d6556d4fbfef37fde10
--- /dev/null
+++ b/crates/sail-session/src/extensions/graph_utils/local.rs
@@ -0,0 +1,114 @@
+//! A no-follow check for the explicitly trusted, exclusively managed local root.
+//!
+//! ObjectStore's local listing follows symbolic links. Checking an owned URI's
+//! lexical prefix therefore is not sufficient before listing/deleting its tree.
+//! This check rejects existing links; it is not a descriptor-relative sandbox
+//! against an OS user racing filesystem changes between the check and operation.
+use std::path::{Path, PathBuf};
+
+use datafusion_common::{Result, exec_datafusion_err, exec_err, plan_datafusion_err, plan_err};
+use url::Url;
+
+#[derive(Debug, Clone)]
+pub(super) struct LocalRoot(PathBuf);
+
+impl LocalRoot {
+    pub(super) fn canonicalize(url: &Url) -> Result<(Url, Option<Self>)> {
+        if url.scheme() != "file" {
+            return Ok((url.clone(), None));
+        }
+        let path = url
+            .to_file_path()
+            .map_err(|()| plan_datafusion_err!("graph utils requires a local file URI"))?;
+        let root = path.canonicalize().map_err(|e| {
+            plan_datafusion_err!(
+                "precreate the trusted graph staging directory before starting Sail: {e}"
+            )
+        })?;
+        if !root.is_dir() || root.parent().is_none() {
+            return plan_err!("graph staging root must be an existing non-root directory");
+        }
+        let url = Url::from_directory_path(&root)
+            .map_err(|()| plan_datafusion_err!("invalid canonical graph staging root"))?;
+        if url.path().trim_matches('/').split('/').any(|part| {
+            !part
+                .bytes()
+                .all(|b| b.is_ascii_alphanumeric() || b"-_.=".contains(&b))
+        }) {
+            return plan_err!(
+                "canonical graph staging root requires unambiguous ASCII path segments"
+            );
+        }
+        Ok((url, Some(Self(root))))
+    }
+
+    pub(super) async fn check(&self, relative: PathBuf) -> Result<()> {
+        let root = self.0.clone();
+        tokio::task::spawn_blocking(move || {
+            // Recheck all root components too: replacing the allocated run or
+            // an ancestor with a symlink must not redirect a later request.
+            let mut current = PathBuf::new();
+            for component in root.components() {
+                current.push(component);
+                reject_link(&current)?;
+            }
+            for component in relative.components() {
+                current.push(component);
+                match std::fs::symlink_metadata(&current) {
+                    Ok(metadata) => reject_type(&current, &metadata)?,
+                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
+                    Err(error) => return Err(error.into()),
+                }
+            }
+            let metadata = std::fs::symlink_metadata(&current)?;
+            reject_type(&current, &metadata)?;
+            if !metadata.is_dir() {
+                return Ok(());
+            }
+            // Keep one iterator per directory depth, rather than accumulating
+            // every object path in memory. read_dir/file_type do not follow links.
+            let mut directories = vec![std::fs::read_dir(&current)?];
+            while let Some(directory) = directories.last_mut() {
+                if let Some(entry) = directory.next() {
+                    let entry = entry?;
+                    let kind = entry.file_type()?;
+                    if kind.is_symlink() {
+                        return exec_err!(
+                            "symbolic links are not allowed in graph staging: {}",
+                            entry.path().display()
+                        );
+                    }
+                    if kind.is_dir() {
+                        directories.push(std::fs::read_dir(entry.path())?);
+                    } else if !kind.is_file() {
+                        return exec_err!(
+                            "non-regular file in graph staging: {}",
+                            entry.path().display()
+                        );
+                    }
+                } else {
+                    directories.pop();
+                }
+            }
+            Ok(())
+        })
+        .await
+        .map_err(|e| exec_datafusion_err!("graph staging path check: {e}"))?
+    }
+}
+
+fn reject_link(path: &Path) -> Result<()> {
+    reject_type(path, &std::fs::symlink_metadata(path)?)
+}
+fn reject_type(path: &Path, metadata: &std::fs::Metadata) -> Result<()> {
+    if metadata.file_type().is_symlink() {
+        return exec_err!(
+            "symbolic links are not allowed in graph staging: {}",
+            path.display()
+        );
+    }
+    if !metadata.is_dir() && !metadata.is_file() {
+        return exec_err!("non-regular file in graph staging: {}", path.display());
+    }
+    Ok(())
+}
```

## 43. crates/sail-session/src/extensions/graph_utils/local_tests.rs {#host-patch-43}

```diff
diff --git a/crates/sail-session/src/extensions/graph_utils/local_tests.rs b/crates/sail-session/src/extensions/graph_utils/local_tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..b0a1a362fd16344c2ef89f37ad78a4075ed1093e
--- /dev/null
+++ b/crates/sail-session/src/extensions/graph_utils/local_tests.rs
@@ -0,0 +1,138 @@
+use std::os::unix::fs::symlink;
+use std::path::PathBuf;
+
+use datafusion::execution::runtime_env::RuntimeEnv;
+use datafusion_common::{Result, plan_datafusion_err};
+
+use super::proto::request::Verb;
+use super::proto::{Exists, Ls, Mkdir, Request, Rm};
+use super::storage::GraphRuns;
+
+async fn allocate(runs: &GraphRuns) -> Result<(String, String, String, PathBuf)> {
+    let id = uuid::Uuid::new_v4().to_string();
+    let rows = runs.execute(mkdir(&id)).await?;
+    let uri = rows[0]
+        .path
+        .clone()
+        .ok_or_else(|| plan_datafusion_err!("missing path"))?;
+    let token = rows[0]
+        .token
+        .clone()
+        .ok_or_else(|| plan_datafusion_err!("missing token"))?;
+    let path = url::Url::parse(&uri)
+        .map_err(|e| plan_datafusion_err!("{e}"))?
+        .to_file_path()
+        .map_err(|()| plan_datafusion_err!("invalid local receipt URI"))?;
+    Ok((id, uri, token, path))
+}
+fn mkdir(id: &str) -> Request {
+    Request {
+        verb: Some(Verb::Mkdir(Mkdir {
+            root: String::new(),
+            request_id: id.into(),
+        })),
+    }
+}
+fn remove(path: &str, token: &str) -> Request {
+    Request {
+        verb: Some(Verb::Rm(Rm {
+            path: path.into(),
+            token: token.into(),
+        })),
+    }
+}
+fn fixture(root: &std::path::Path) -> Result<GraphRuns> {
+    let uri = url::Url::from_directory_path(root)
+        .map_err(|()| plan_datafusion_err!("invalid fixture directory"))?;
+    GraphRuns::new(&RuntimeEnv::default(), uri.as_str())
+}
+
+#[tokio::test]
+async fn local_link_cannot_list_or_delete_outside_run_and_other_cleanup_continues() -> Result<()> {
+    let directory = tempfile::tempdir()?;
+    let root = directory.path().join("root");
+    let outside = directory.path().join("outside");
+    std::fs::create_dir_all(&root)?;
+    std::fs::create_dir_all(&outside)?;
+    let sentinel = outside.join("keep.parquet");
+    std::fs::write(&sentinel, b"outside sentinel")?;
+    let runs = fixture(&root)?;
+    let (id, uri, token, path) = allocate(&runs).await?;
+    let (_, _, _, sibling) = allocate(&runs).await?;
+    std::fs::write(sibling.join("part.parquet"), b"owned")?;
+    symlink(&outside, path.join("escape"))?;
+    for verb in [
+        Verb::Exists(Exists {
+            path: uri.clone(),
+            token: token.clone(),
+        }),
+        Verb::Ls(Ls {
+            path: uri.clone(),
+            token: token.clone(),
+            limit: 1,
+        }),
+        Verb::Rm(Rm {
+            path: uri.clone(),
+            token: token.clone(),
+        }),
+        Verb::Rm(Rm {
+            path: format!("{uri}/escape/keep.parquet"),
+            token: token.clone(),
+        }),
+    ] {
+        let error = runs
+            .execute(Request { verb: Some(verb) })
+            .await
+            .err()
+            .ok_or_else(|| plan_datafusion_err!("symlink request unexpectedly succeeded"))?;
+        assert!(error.to_string().contains("symbolic links"));
+        assert_eq!(std::fs::read(&sentinel)?, b"outside sentinel");
+    }
+    assert!(runs.execute(mkdir(&id)).await.is_err());
+    assert!(runs.cleanup().await.is_err());
+    assert_eq!(std::fs::read(&sentinel)?, b"outside sentinel");
+    assert!(!sibling.join("part.parquet").exists());
+    assert!(!sibling.join("_sail_graph_run").exists());
+    // A dangling link is equally invalid and must not be mistaken for a missing path.
+    std::fs::remove_file(path.join("escape"))?;
+    symlink(outside.join("missing"), path.join("escape"))?;
+    assert!(runs.cleanup().await.is_err());
+    std::fs::remove_file(path.join("escape"))?;
+    runs.cleanup().await?;
+    Ok(())
+}
+
+#[tokio::test]
+async fn local_run_replaced_by_link_cannot_mutate_sibling_run() -> Result<()> {
+    let root = tempfile::tempdir()?;
+    let runs = fixture(root.path())?;
+    let (id, uri, token, path) = allocate(&runs).await?;
+    let (_, _, _, sibling) = allocate(&runs).await?;
+    let sentinel = sibling.join("keep.parquet");
+    std::fs::write(&sentinel, b"sibling sentinel")?;
+    std::fs::remove_dir_all(&path)?;
+    symlink(&sibling, &path)?;
+    assert!(runs.execute(remove(&uri, &token)).await.is_err());
+    assert!(runs.execute(mkdir(&id)).await.is_err());
+    assert_eq!(std::fs::read(&sentinel)?, b"sibling sentinel");
+    std::fs::remove_file(&path)?;
+    runs.cleanup().await?;
+    Ok(())
+}
+
+#[tokio::test]
+async fn local_root_alias_is_canonicalized_before_ownership_is_assigned() -> Result<()> {
+    let directory = tempfile::tempdir()?;
+    let root = directory.path().join("actual");
+    std::fs::create_dir(&root)?;
+    let alias = directory.path().join("alias");
+    symlink(&root, &alias)?;
+    let runs = fixture(&alias)?;
+    let (_, _, _, allocated) = allocate(&runs).await?;
+    let canonical = root.canonicalize()?;
+    assert_eq!(allocated.parent(), Some(canonical.as_path()));
+    runs.cleanup().await?;
+    let missing = directory.path().join("not-created");
+    assert!(fixture(&missing).is_err());
+    Ok(())
+}
```

## 44. crates/sail-session/src/extensions/graph_utils/mod.rs {#host-patch-44}

```diff
diff --git a/crates/sail-session/src/extensions/graph_utils/mod.rs b/crates/sail-session/src/extensions/graph_utils/mod.rs
new file mode 100644
index 0000000000000000000000000000000000000000..a5a3907ee2c8ca63d57837ab4e611fc8472afd39
--- /dev/null
+++ b/crates/sail-session/src/extensions/graph_utils/mod.rs
@@ -0,0 +1,64 @@
+//! Opt-in, host-owned storage utilities for relational graph clients.
+//!
+//! This is a compiled-in adapter: object-store credentials/runtime never cross
+//! the native wheel interface. The ordinary scalar codec handles its functions.
+#[cfg(test)]
+mod cleanup_tests;
+mod functions;
+mod local;
+#[cfg(all(test, unix))]
+mod local_tests;
+mod plan;
+mod storage;
+#[cfg(test)]
+mod tests;
+
+use std::sync::Arc;
+
+use datafusion::execution::runtime_env::RuntimeEnv;
+use datafusion::prelude::SessionConfig;
+use datafusion_common::{Result, plan_err};
+use datafusion_expr::ScalarUDF;
+use sail_common_datafusion::connect_extension::ConnectExtensionRegistry;
+use sail_common_datafusion::driver_extension::DriverExtensionRegistry;
+pub(crate) use storage::GraphRuns;
+
+pub(super) mod proto {
+    include!(concat!(env!("OUT_DIR"), "/gf.utils.v1.rs"));
+}
+
+pub(super) const TYPE_URL: &str = "type.googleapis.com/gf.utils.v1.Request";
+
+pub(super) fn register(
+    config: &mut SessionConfig,
+    runtime: &Arc<RuntimeEnv>,
+    registry: &mut ConnectExtensionRegistry,
+    driver: Option<Arc<DriverExtensionRegistry>>,
+) -> Result<Vec<ScalarUDF>> {
+    let root = match std::env::var("SAIL_GRAPH_UTILS_ROOT") {
+        Ok(root) if !root.is_empty() => root,
+        Ok(_) => return plan_err!("SAIL_GRAPH_UTILS_ROOT must be a nonempty absolute URI"),
+        Err(std::env::VarError::NotPresent) => return Ok(vec![]),
+        Err(error) => return plan_err!("SAIL_GRAPH_UTILS_ROOT: {error}"),
+    };
+    let runs = Arc::new(GraphRuns::new(runtime, &root)?);
+    registry.register(
+        TYPE_URL.into(),
+        true,
+        0,
+        0,
+        Arc::new(plan::Handler {
+            runs: runs.clone(),
+            driver,
+        }),
+    )?;
+    config.set_extension(runs);
+    functions::register()
+}
+
+pub(super) fn register_worker_functions() -> Result<()> {
+    // Workers need no filesystem capability or configured driver root. The
+    // function identity is versioned with its bit-level implementation contract.
+    functions::register()?;
+    Ok(())
+}
```

## 45. crates/sail-session/src/extensions/graph_utils/plan.rs {#host-patch-45}

```diff
diff --git a/crates/sail-session/src/extensions/graph_utils/plan.rs b/crates/sail-session/src/extensions/graph_utils/plan.rs
new file mode 100644
index 0000000000000000000000000000000000000000..20d86842778e6d186aeaed872db781276d5310b8
--- /dev/null
+++ b/crates/sail-session/src/extensions/graph_utils/plan.rs
@@ -0,0 +1,231 @@
+use std::sync::Arc;
+
+use async_trait::async_trait;
+use datafusion::arrow::array::{ArrayRef, BooleanArray, Int32Array, Int64Array, StringArray};
+use datafusion::arrow::datatypes::{DataType, Field, Schema, SchemaRef};
+use datafusion::arrow::record_batch::RecordBatch;
+use datafusion::catalog::{Session, TableProvider};
+use datafusion::execution::{SendableRecordBatchStream, TaskContext};
+use datafusion::physical_expr::{EquivalenceProperties, Partitioning};
+use datafusion::physical_plan::execution_plan::{Boundedness, EmissionType};
+use datafusion::physical_plan::stream::RecordBatchStreamAdapter;
+use datafusion::physical_plan::{DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties};
+use datafusion_common::{Result, plan_datafusion_err, plan_err};
+use datafusion_expr::{Expr, TableType};
+use prost::Message;
+use sail_common_datafusion::connect_extension::ConnectRelationHandler;
+use sail_common_datafusion::driver_extension::DriverExtensionRegistry;
+
+use super::super::driver::DriverTableProvider;
+use super::proto::Request;
+use super::storage::GraphRuns;
+
+#[derive(Default)]
+pub(super) struct Row {
+    pub kind: String,
+    pub path: Option<String>,
+    pub size: Option<i64>,
+    pub value: Option<bool>,
+    pub count: Option<i64>,
+    pub capabilities: Option<String>,
+    pub token: Option<String>,
+    pub truncated: bool,
+}
+impl Row {
+    pub fn new(kind: &str) -> Self {
+        Self {
+            kind: kind.into(),
+            ..Self::default()
+        }
+    }
+}
+
+pub(super) fn schema() -> SchemaRef {
+    Arc::new(Schema::new(vec![
+        Field::new("kind", DataType::Utf8, false),
+        Field::new("path", DataType::Utf8, true),
+        Field::new("size", DataType::Int64, true),
+        Field::new("value", DataType::Boolean, true),
+        Field::new("count", DataType::Int64, true),
+        Field::new("capabilities", DataType::Utf8, true),
+        Field::new("token", DataType::Utf8, true),
+        Field::new("truncated", DataType::Boolean, false),
+        Field::new("engine", DataType::Utf8, false),
+        Field::new("protocol_version", DataType::Int32, false),
+        Field::new("lease_seconds", DataType::Int64, false),
+    ]))
+}
+
+fn batch(rows: &[Row]) -> Result<RecordBatch> {
+    let arrays: Vec<ArrayRef> = vec![
+        Arc::new(StringArray::from_iter_values(
+            rows.iter().map(|r| r.kind.as_str()),
+        )),
+        Arc::new(StringArray::from_iter(
+            rows.iter().map(|r| r.path.as_deref()),
+        )),
+        Arc::new(Int64Array::from_iter(rows.iter().map(|r| r.size))),
+        Arc::new(BooleanArray::from_iter(rows.iter().map(|r| r.value))),
+        Arc::new(Int64Array::from_iter(rows.iter().map(|r| r.count))),
+        Arc::new(StringArray::from_iter(
+            rows.iter().map(|r| r.capabilities.as_deref()),
+        )),
+        Arc::new(StringArray::from_iter(
+            rows.iter().map(|r| r.token.as_deref()),
+        )),
+        Arc::new(BooleanArray::from_iter(
+            rows.iter().map(|r| Some(r.truncated)),
+        )),
+        Arc::new(StringArray::from_iter_values(rows.iter().map(|_| "sail"))),
+        Arc::new(Int32Array::from(vec![1; rows.len()])),
+        Arc::new(Int64Array::from(vec![0; rows.len()])),
+    ];
+    Ok(RecordBatch::try_new(schema(), arrays)?)
+}
+
+pub(super) struct Handler {
+    pub runs: Arc<GraphRuns>,
+    pub driver: Option<Arc<DriverExtensionRegistry>>,
+}
+impl ConnectRelationHandler for Handler {
+    fn plan(
+        &self,
+        payload: &[u8],
+        inputs: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn TableProvider>> {
+        if payload.len() > 8192 || !inputs.is_empty() {
+            return plan_err!("graph utils requires zero inputs and at most 8192 request bytes");
+        }
+        let request = Request::decode(payload)
+            .map_err(|e| plan_datafusion_err!("graph utils protobuf: {e}"))?;
+        GraphRuns::validate(&request)?;
+        let provider: Arc<dyn TableProvider> = Arc::new(Provider {
+            runs: self.runs.clone(),
+            request,
+        });
+        match &self.driver {
+            Some(registry) => Ok(Arc::new(DriverTableProvider {
+                inner: provider,
+                inputs: vec![],
+                names: vec![],
+                owner: "sail-gf-utils/1".into(),
+                registry: registry.clone(),
+            })),
+            None => Ok(provider),
+        }
+    }
+}
+
+struct Provider {
+    runs: Arc<GraphRuns>,
+    request: Request,
+}
+impl std::fmt::Debug for Provider {
+    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
+        f.debug_struct("GraphUtilsProvider").finish_non_exhaustive()
+    }
+}
+#[async_trait]
+impl TableProvider for Provider {
+    fn schema(&self) -> SchemaRef {
+        schema()
+    }
+    fn table_type(&self) -> TableType {
+        TableType::Temporary
+    }
+    async fn scan(
+        &self,
+        _session: &dyn Session,
+        projection: Option<&Vec<usize>>,
+        _filters: &[Expr],
+        _limit: Option<usize>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        let schema = match projection {
+            Some(p) => Arc::new(schema().project(p)?),
+            None => schema(),
+        };
+        let properties = Arc::new(PlanProperties::new(
+            EquivalenceProperties::new(schema),
+            Partitioning::UnknownPartitioning(1),
+            EmissionType::Final,
+            Boundedness::Bounded,
+        ));
+        Ok(Arc::new(UtilsExec {
+            runs: self.runs.clone(),
+            request: self.request.clone(),
+            projection: projection.cloned(),
+            properties,
+        }))
+    }
+}
+
+struct UtilsExec {
+    runs: Arc<GraphRuns>,
+    request: Request,
+    projection: Option<Vec<usize>>,
+    properties: Arc<PlanProperties>,
+}
+impl std::fmt::Debug for UtilsExec {
+    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
+        self.fmt_as(DisplayFormatType::Default, f)
+    }
+}
+impl DisplayAs for UtilsExec {
+    fn fmt_as(&self, _: DisplayFormatType, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
+        // Never print token-bearing requests in explain output or logs.
+        write!(f, "GraphUtilsExec: host storage, placement=driver")
+    }
+}
+impl ExecutionPlan for UtilsExec {
+    fn apply_expressions(
+        &self,
+        _f: &mut dyn FnMut(
+            &Arc<dyn datafusion::physical_expr::PhysicalExpr>,
+        ) -> Result<datafusion_common::tree_node::TreeNodeRecursion>,
+    ) -> Result<datafusion_common::tree_node::TreeNodeRecursion> {
+        Ok(datafusion_common::tree_node::TreeNodeRecursion::Continue)
+    }
+    fn name(&self) -> &'static str {
+        "GraphUtilsExec"
+    }
+    fn properties(&self) -> &Arc<PlanProperties> {
+        &self.properties
+    }
+    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
+        vec![]
+    }
+    fn with_new_children(
+        self: Arc<Self>,
+        children: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        if !children.is_empty() {
+            return plan_err!("graph utils has no children");
+        }
+        Ok(self)
+    }
+    fn execute(
+        &self,
+        partition: usize,
+        _context: Arc<TaskContext>,
+    ) -> Result<SendableRecordBatchStream> {
+        if partition != 0 {
+            return plan_err!("graph utils supports only partition zero");
+        }
+        let (runs, request, projection) = (
+            self.runs.clone(),
+            self.request.clone(),
+            self.projection.clone(),
+        );
+        let stream = futures::stream::once(async move {
+            let batch = batch(&runs.execute(request).await?)?;
+            match projection {
+                Some(p) => Ok(batch.project(&p)?),
+                None => Ok(batch),
+            }
+        });
+        Ok(Box::pin(RecordBatchStreamAdapter::new(
+            self.schema(),
+            stream,
+        )))
+    }
+}
```

## 46. crates/sail-session/src/extensions/graph_utils/storage.rs {#host-patch-46}

```diff
diff --git a/crates/sail-session/src/extensions/graph_utils/storage.rs b/crates/sail-session/src/extensions/graph_utils/storage.rs
new file mode 100644
index 0000000000000000000000000000000000000000..cae3975061349b909d1f3fd8ce4f804ff77844d1
--- /dev/null
+++ b/crates/sail-session/src/extensions/graph_utils/storage.rs
@@ -0,0 +1,356 @@
+use std::collections::HashMap;
+use std::sync::Arc;
+
+use datafusion::execution::runtime_env::RuntimeEnv;
+use datafusion_common::{DataFusionError, Result, exec_err, plan_datafusion_err, plan_err};
+use futures::TryStreamExt;
+use object_store::path::Path;
+use object_store::{ObjectStore, ObjectStoreExt, PutPayload};
+use sail_common_datafusion::extension::SessionExtension;
+use sail_object_store::resolve_object_store_path;
+use tokio::sync::Mutex;
+use url::Url;
+
+use super::local::LocalRoot;
+use super::plan::Row;
+use super::proto::Request;
+use super::proto::request::Verb;
+
+const MARKER: &str = "_sail_graph_run";
+const MAX_RUNS: usize = 1024;
+
+#[derive(Debug)]
+struct Run {
+    uri: String,
+    prefix: Path,
+    token: String,
+    released: bool,
+}
+#[derive(Debug, Default)]
+struct State {
+    runs: HashMap<String, Run>,
+    closed: bool,
+}
+
+pub(crate) struct GraphRuns {
+    root: String,
+    prefix: Path,
+    store: Arc<dyn ObjectStore>,
+    local: Option<LocalRoot>,
+    state: Mutex<State>,
+}
+
+impl std::fmt::Debug for GraphRuns {
+    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
+        f.debug_struct("GraphRuns")
+            .field("root", &self.root)
+            .finish_non_exhaustive()
+    }
+}
+
+impl SessionExtension for GraphRuns {
+    fn name() -> &'static str {
+        "GraphUtilsOwnedRuns"
+    }
+}
+
+impl GraphRuns {
+    pub(super) fn new(runtime: &RuntimeEnv, root: &str) -> Result<Self> {
+        // Reject ambiguous spellings before URL parsing normalizes traversal.
+        if root.len() > 4096
+            || root.contains(['%', '\\', '?', '#'])
+            || root.split('/').any(|s| s == "." || s == "..")
+        {
+            return plan_err!("graph utils root contains an ambiguous path");
+        }
+        let url = Url::parse(root).map_err(|e| plan_datafusion_err!("graph utils root: {e}"))?;
+        if !url.username().is_empty()
+            || url.password().is_some()
+            || url.cannot_be_a_base()
+            || url.path().trim_matches('/').is_empty()
+        {
+            return plan_err!("graph utils root must be an absolute URI with a non-root prefix");
+        }
+        if url.path().trim_matches('/').split('/').any(|s| {
+            s.is_empty()
+                || !s
+                    .bytes()
+                    .all(|b| b.is_ascii_alphanumeric() || b"-_.=".contains(&b))
+        }) {
+            return plan_err!("graph utils root requires unambiguous ASCII path segments");
+        }
+        let (url, local) = LocalRoot::canonicalize(&url)?;
+        let root = url.to_string().trim_end_matches('/').to_owned();
+        let resolved = resolve_object_store_path(runtime, &root)?;
+        Ok(Self {
+            root,
+            prefix: resolved.prefix().clone(),
+            store: resolved.store().clone(),
+            local,
+            state: Mutex::new(State::default()),
+        })
+    }
+
+    pub(super) fn validate(request: &Request) -> Result<()> {
+        let Some(verb) = &request.verb else {
+            return plan_err!("graph utils request has no verb");
+        };
+        match verb {
+            Verb::Ping(p) if p.client_version.len() > 128 => {
+                return plan_err!("client version too long");
+            }
+            Verb::Mkdir(m) => {
+                uuid::Uuid::parse_str(&m.request_id)
+                    .map_err(|_| plan_datafusion_err!("Mkdir.request_id must be a UUID"))?;
+                if m.root.len() > 4096 {
+                    return plan_err!("root URI too long");
+                }
+            }
+            Verb::Ls(l) if l.limit > 1000 => return plan_err!("Ls.limit must be at most 1000"),
+            _ => {}
+        }
+        Ok(())
+    }
+
+    fn owned_path(&self, run: &Run, path: &str) -> Result<Path> {
+        if path.len() > 4096 || path.contains(['%', '\\', '?', '#']) {
+            return plan_err!("invalid owned run path");
+        }
+        let path = path.trim_end_matches('/');
+        if path == run.uri {
+            return Ok(run.prefix.clone());
+        }
+        let suffix = path
+            .strip_prefix(&format!("{}/", run.uri))
+            .ok_or_else(|| plan_datafusion_err!("path is outside the token's owned run"))?;
+        if suffix.split('/').any(|s| {
+            s.is_empty()
+                || s == "."
+                || s == ".."
+                || !s
+                    .bytes()
+                    .all(|b| b.is_ascii_alphanumeric() || b"-_.=".contains(&b))
+        }) {
+            return plan_err!("owned run suffix must contain unambiguous ASCII path segments");
+        }
+        Ok(suffix
+            .split('/')
+            .fold(run.prefix.clone(), |path, segment| path.join(segment)))
+    }
+
+    async fn remove(&self, prefix: &Path) -> Result<i64> {
+        self.check_local(prefix).await?;
+        let mut listing = self.store.list(Some(prefix));
+        let mut count = 0_i64;
+        while let Some(entry) = listing.try_next().await? {
+            match self.store.delete(&entry.location).await {
+                Ok(()) => count += 1,
+                Err(object_store::Error::NotFound { .. }) => {}
+                Err(error) => return Err(DataFusionError::ObjectStore(Box::new(error))),
+            }
+        }
+        Ok(count)
+    }
+
+    async fn check_local(&self, prefix: &Path) -> Result<()> {
+        if let Some(local) = &self.local {
+            let parts = prefix.prefix_match(&self.prefix).ok_or_else(|| {
+                plan_datafusion_err!("local graph path is outside the staging root")
+            })?;
+            let relative = parts
+                .map(|part| part.as_ref().to_string())
+                .collect::<std::path::PathBuf>();
+            local.check(relative).await?;
+        }
+        Ok(())
+    }
+
+    pub(super) async fn execute(&self, request: Request) -> Result<Vec<Row>> {
+        Self::validate(&request)?;
+        let Some(verb) = request.verb else {
+            return exec_err!("graph utils request has no verb");
+        };
+        let mut state = self.state.lock().await;
+        if state.closed {
+            return exec_err!("graph utils session has closed");
+        }
+        match verb {
+            Verb::Ping(_) => Ok(vec![Row {
+                path: Some(self.root.clone()),
+                capabilities: Some(r#"["fs","owned_runs_v1","axpb"]"#.into()),
+                ..Row::new("pong")
+            }]),
+            Verb::Mkdir(request) => {
+                if !request.root.is_empty() && request.root.trim_end_matches('/') != self.root {
+                    return exec_err!("Mkdir.root differs from the configured trusted root");
+                }
+                let key = uuid::Uuid::parse_str(&request.request_id)
+                    .map_err(|e| plan_datafusion_err!("request UUID: {e}"))?
+                    .to_string();
+                if !state.runs.contains_key(&key) {
+                    if state.runs.len() >= MAX_RUNS {
+                        return exec_err!("graph utils session reached the 1024 run limit");
+                    }
+                    let id = uuid::Uuid::new_v4().to_string();
+                    let run = Run {
+                        uri: format!("{}/{id}", self.root),
+                        prefix: self.prefix.clone().join(id),
+                        token: uuid::Uuid::new_v4().to_string(),
+                        released: false,
+                    };
+                    // Record ownership before awaiting storage: cancelled allocation
+                    // attempts remain discoverable by retry and session cleanup.
+                    state.runs.insert(key.clone(), run);
+                }
+                let run = state
+                    .runs
+                    .get(&key)
+                    .ok_or_else(|| plan_datafusion_err!("run missing"))?;
+                if run.released {
+                    return exec_err!("Mkdir request refers to a released run");
+                }
+                self.check_local(&run.prefix).await?;
+                self.store
+                    .put(
+                        &run.prefix.clone().join(MARKER),
+                        PutPayload::from_static(b"gf-utils-v1"),
+                    )
+                    .await?;
+                Ok(vec![Row {
+                    path: Some(run.uri.clone()),
+                    token: Some(run.token.clone()),
+                    ..Row::new("mkdir")
+                }])
+            }
+            verb => {
+                let (path, token) = match &verb {
+                    Verb::Exists(v) => (&v.path, &v.token),
+                    Verb::Ls(v) => (&v.path, &v.token),
+                    Verb::Rm(v) => (&v.path, &v.token),
+                    _ => return exec_err!("invalid filesystem verb"),
+                };
+                let run = state
+                    .runs
+                    .values_mut()
+                    .find(|r| r.token == *token)
+                    .ok_or_else(|| plan_datafusion_err!("unknown run token in this session"))?;
+                let prefix = self.owned_path(run, path)?;
+                if run.released && !matches!(verb, Verb::Rm(_)) {
+                    return exec_err!("graph run has been released");
+                }
+                match verb {
+                    Verb::Exists(request) => {
+                        self.check_local(&prefix).await?;
+                        let exists = self.store.list(Some(&prefix)).try_next().await?.is_some();
+                        Ok(vec![Row {
+                            path: Some(request.path),
+                            value: Some(exists),
+                            ..Row::new("exists")
+                        }])
+                    }
+                    Verb::Ls(request) => {
+                        self.check_local(&prefix).await?;
+                        let limit = if request.limit == 0 {
+                            100
+                        } else {
+                            request.limit
+                        } as usize;
+                        let mut listing = self.store.list(Some(&prefix));
+                        let mut rows = vec![];
+                        let mut truncated = false;
+                        while let Some(entry) = listing.try_next().await? {
+                            if entry.location == run.prefix.clone().join(MARKER) {
+                                continue;
+                            }
+                            if rows.len() == limit {
+                                truncated = true;
+                                break;
+                            }
+                            let suffix = entry
+                                .location
+                                .as_ref()
+                                .strip_prefix(run.prefix.as_ref())
+                                .ok_or_else(|| {
+                                    plan_datafusion_err!("store returned object outside owned run")
+                                })?;
+                            rows.push(Row {
+                                path: Some(format!("{}{suffix}", run.uri)),
+                                size: Some(
+                                    i64::try_from(entry.size)
+                                        .map_err(|e| plan_datafusion_err!("object size: {e}"))?,
+                                ),
+                                ..Row::new("entry")
+                            });
+                        }
+                        rows.push(Row {
+                            path: Some(request.path),
+                            count: Some(rows.len() as i64),
+                            truncated,
+                            ..Row::new("ls")
+                        });
+                        Ok(rows)
+                    }
+                    Verb::Rm(request) => {
+                        let count = if run.released {
+                            0
+                        } else {
+                            self.remove(&prefix).await?
+                        };
+                        if prefix == run.prefix {
+                            run.released = true;
+                        }
+                        Ok(vec![Row {
+                            path: Some(request.path),
+                            count: Some(count),
+                            ..Row::new("rm")
+                        }])
+                    }
+                    _ => exec_err!("invalid filesystem verb"),
+                }
+            }
+        }
+    }
+
+    /// Best-effort cleanup after session teardown has requested executor/job
+    /// shutdown. That shutdown is not a join barrier for every detached writer;
+    /// interrupted writes can still require operator cleanup of late objects.
+    /// Transient store failures get bounded retries, with every owned namespace
+    /// attempted on each pass. The caller logs any error after exhaustion.
+    pub(crate) async fn cleanup(&self) -> Result<()> {
+        const ATTEMPTS: usize = 3;
+        for attempt in 1..=ATTEMPTS {
+            match self.cleanup_once().await {
+                Ok(()) => return Ok(()),
+                Err(error) if attempt == ATTEMPTS => {
+                    return exec_err!("graph run cleanup exhausted {ATTEMPTS} attempts: {error}");
+                }
+                Err(error) => {
+                    log::warn!("graph run cleanup attempt {attempt}/{ATTEMPTS} failed: {error}");
+                    tokio::time::sleep(std::time::Duration::from_millis(200)).await;
+                }
+            }
+        }
+        Ok(())
+    }
+
+    async fn cleanup_once(&self) -> Result<()> {
+        let mut state = self.state.lock().await;
+        state.closed = true;
+        let mut errors = vec![];
+        for run in state.runs.values_mut() {
+            match self.remove(&run.prefix).await {
+                Ok(_) => run.released = true,
+                Err(error) => errors.push(error.to_string()),
+            }
+        }
+        if errors.is_empty() {
+            Ok(())
+        } else {
+            exec_err!(
+                "graph run cleanup failed for {} namespaces: {}",
+                errors.len(),
+                errors.join("; ")
+            )
+        }
+    }
+}
```

## 47. crates/sail-session/src/extensions/graph_utils/tests.rs {#host-patch-47}

```diff
diff --git a/crates/sail-session/src/extensions/graph_utils/tests.rs b/crates/sail-session/src/extensions/graph_utils/tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..f34200e977bc382b16f0b8be18bbf56e0e696a48
--- /dev/null
+++ b/crates/sail-session/src/extensions/graph_utils/tests.rs
@@ -0,0 +1,267 @@
+#![expect(
+    clippy::expect_used,
+    reason = "test fixtures assert their typed receipt contract"
+)]
+
+use std::sync::Arc;
+
+use datafusion::execution::runtime_env::RuntimeEnv;
+use datafusion::prelude::SessionContext;
+use datafusion_common::Result;
+use futures::TryStreamExt;
+use object_store::memory::InMemory;
+use object_store::path::Path;
+use object_store::{ObjectStore, ObjectStoreExt, PutPayload};
+use prost::Message;
+use sail_common_datafusion::connect_extension::ConnectRelationHandler;
+
+use super::plan::Handler;
+use super::proto::request::Verb;
+use super::proto::{Exists, Ls, Mkdir, Request, Rm};
+use super::storage::GraphRuns;
+
+fn request(verb: Verb) -> Request {
+    Request { verb: Some(verb) }
+}
+fn mkdir(id: &str) -> Request {
+    request(Verb::Mkdir(Mkdir {
+        root: String::new(),
+        request_id: id.into(),
+    }))
+}
+fn fixture() -> Result<(Arc<GraphRuns>, Arc<InMemory>)> {
+    let runtime = RuntimeEnv::default();
+    let store = Arc::new(InMemory::new());
+    runtime.register_object_store(
+        &url::Url::parse("memory:///").expect("constant URL"),
+        store.clone(),
+    );
+    Ok((
+        Arc::new(GraphRuns::new(&runtime, "memory:///graphs")?),
+        store,
+    ))
+}
+async fn allocate(runs: &GraphRuns) -> Result<(String, String)> {
+    let rows = runs
+        .execute(mkdir(&uuid::Uuid::new_v4().to_string()))
+        .await?;
+    Ok((
+        rows[0].path.clone().expect("path"),
+        rows[0].token.clone().expect("token"),
+    ))
+}
+
+#[tokio::test]
+async fn planning_and_schema_analysis_have_no_storage_effects() -> Result<()> {
+    let (runs, store) = fixture()?;
+    let handler = Handler { runs, driver: None };
+    let provider = handler.plan(
+        &mkdir(&uuid::Uuid::new_v4().to_string()).encode_to_vec(),
+        vec![],
+    )?;
+    assert_eq!(provider.schema().field(0).name(), "kind");
+    let session = SessionContext::new();
+    let plan = provider.scan(&session.state(), None, &[], None).await?;
+    assert!(store.list(None).try_next().await?.is_none());
+    let batches = datafusion::physical_plan::collect(plan, session.task_ctx()).await?;
+    assert_eq!(batches[0].num_rows(), 1);
+    assert!(store.list(None).try_next().await?.is_some());
+    Ok(())
+}
+
+#[tokio::test]
+async fn allocation_retry_and_release_are_session_owned_and_idempotent() -> Result<()> {
+    let (runs, store) = fixture()?;
+    let id = uuid::Uuid::new_v4().to_string();
+    let first = runs.execute(mkdir(&id)).await?;
+    let second = runs.execute(mkdir(&id)).await?;
+    assert_eq!(first[0].path, second[0].path);
+    assert_eq!(first[0].token, second[0].token);
+    let path = first[0].path.clone().expect("path");
+    let token = first[0].token.clone().expect("token");
+    let exists = request(Verb::Exists(Exists {
+        path: path.clone(),
+        token: token.clone(),
+    }));
+    assert_eq!(runs.execute(exists.clone()).await?[0].value, Some(true));
+    let remove = request(Verb::Rm(Rm { path, token }));
+    assert_eq!(runs.execute(remove.clone()).await?[0].count, Some(1));
+    assert_eq!(runs.execute(remove).await?[0].count, Some(0));
+    assert!(runs.execute(mkdir(&id)).await.is_err());
+    assert!(runs.execute(exists).await.is_err());
+    assert!(store.list(None).try_next().await?.is_none());
+    Ok(())
+}
+
+#[tokio::test]
+async fn capabilities_reject_other_runs_roots_traversal_and_sessions() -> Result<()> {
+    let (runs, _) = fixture()?;
+    let (path, token) = allocate(&runs).await?;
+    let (other, _) = allocate(&runs).await?;
+    for invalid in [
+        "memory:///graphs".to_string(),
+        other,
+        format!("{path}extra"),
+        format!("{path}/../escape"),
+        format!("{path}/%2e%2e/escape"),
+        format!("{path}/a//b"),
+        format!("{path}/a\\b"),
+        format!("{path}/stage?query"),
+    ] {
+        assert!(
+            runs.execute(request(Verb::Rm(Rm {
+                path: invalid,
+                token: token.clone()
+            })))
+            .await
+            .is_err()
+        );
+    }
+    let (other_session, _) = fixture()?;
+    assert!(
+        other_session
+            .execute(request(Verb::Rm(Rm { path, token })))
+            .await
+            .is_err()
+    );
+    Ok(())
+}
+
+#[tokio::test]
+async fn bounded_listing_and_session_cleanup_preserve_foreign_objects() -> Result<()> {
+    let (runs, store) = fixture()?;
+    let (path, token) = allocate(&runs).await?;
+    let prefix = path.strip_prefix("memory:///").expect("memory URI");
+    for suffix in [
+        "stage-1/part-1.parquet",
+        "stage-1/part-2.parquet",
+        "stage-2/part-1.parquet",
+        "stage-10/part-1.parquet",
+    ] {
+        store
+            .put(
+                &Path::from(format!("{prefix}/{suffix}")),
+                PutPayload::from_static(b"test"),
+            )
+            .await?;
+    }
+    store
+        .put(
+            &Path::from("graphs/unowned/keep"),
+            PutPayload::from_static(b"keep"),
+        )
+        .await?;
+    let rows = runs
+        .execute(request(Verb::Ls(Ls {
+            path: path.clone(),
+            token: token.clone(),
+            limit: 1,
+        })))
+        .await?;
+    assert_eq!(rows.len(), 2);
+    assert_eq!(rows[0].kind, "entry");
+    assert_eq!(rows[1].kind, "ls");
+    assert_eq!(rows[1].count, Some(1));
+    assert!(rows[1].truncated);
+    let removed = runs
+        .execute(request(Verb::Rm(Rm {
+            path: format!("{path}/stage-1"),
+            token: token.clone(),
+        })))
+        .await?;
+    assert_eq!(removed[0].count, Some(2));
+    assert!(
+        store
+            .head(&Path::from(format!("{prefix}/stage-10/part-1.parquet")))
+            .await
+            .is_ok()
+    );
+    assert_eq!(
+        runs.execute(request(Verb::Exists(Exists {
+            path: path.clone(),
+            token
+        })))
+        .await?[0]
+            .value,
+        Some(true)
+    );
+    runs.cleanup().await?;
+    let remaining = store.list(None).try_collect::<Vec<_>>().await?;
+    assert_eq!(remaining.len(), 1);
+    assert_eq!(remaining[0].location, Path::from("graphs/unowned/keep"));
+    assert!(allocate(&runs).await.is_err());
+    Ok(())
+}
+
+#[test]
+fn request_limits_and_root_spelling_are_validated() -> Result<()> {
+    let (runs, _) = fixture()?;
+    let handler = Handler { runs, driver: None };
+    assert!(handler.plan(&[0; 8193], vec![]).is_err());
+    assert!(handler.plan(&[], vec![]).is_err());
+    assert!(GraphRuns::validate(&mkdir("not-a-uuid")).is_err());
+    assert!(
+        GraphRuns::validate(&request(Verb::Ls(Ls {
+            path: String::new(),
+            token: String::new(),
+            limit: 1001
+        })))
+        .is_err()
+    );
+    for invalid in [
+        "/tmp/root",
+        "file:///",
+        "file:///a/../b",
+        "file:///a/%2e",
+        "file:///a?b",
+        "file:///a#b",
+    ] {
+        assert!(GraphRuns::new(&RuntimeEnv::default(), invalid).is_err());
+    }
+    Ok(())
+}
+
+#[tokio::test]
+async fn graph_scalar_codec_and_signed_null_semantics() -> Result<()> {
+    use datafusion_common::ScalarValue;
+    use datafusion_expr::lit;
+
+    let session = SessionContext::new();
+    let mut functions = vec![];
+    for function in super::functions::register()? {
+        let mut bytes = vec![];
+        assert!(sail_common_datafusion::native_scalar::encode_scalar(
+            &function, &mut bytes
+        )?);
+        let decoded =
+            sail_common_datafusion::native_scalar::decode_scalar(function.name(), &bytes)?;
+        session.register_udf((*decoded).clone());
+        functions.push(decoded);
+    }
+    let batches = session
+        .read_empty()?
+        .select(vec![
+            functions[0]
+                .call(vec![lit(i64::MIN), lit(2_i64), lit(0_i64)])
+                .alias("a"),
+            functions[0]
+                .call(vec![lit(ScalarValue::Int64(None)), lit(1_i64), lit(0_i64)])
+                .alias("b"),
+            functions[1].call(vec![]).alias("v"),
+        ])?
+        .collect()
+        .await?;
+    let batch = &batches[0];
+    use datafusion::arrow::array::{Array, Int64Array};
+    assert_eq!(
+        batch
+            .column(0)
+            .as_any()
+            .downcast_ref::<Int64Array>()
+            .expect("int64")
+            .value(0),
+        27
+    );
+    assert!(batch.column(1).is_null(0));
+    Ok(())
+}
```

## 48. crates/sail-session/src/extensions/manifest.rs {#host-patch-48}

```diff
diff --git a/crates/sail-session/src/extensions/manifest.rs b/crates/sail-session/src/extensions/manifest.rs
new file mode 100644
index 0000000000000000000000000000000000000000..496fcef728fc875731c06a18159542f1d3bd9189
--- /dev/null
+++ b/crates/sail-session/src/extensions/manifest.rs
@@ -0,0 +1,132 @@
+use std::collections::HashSet;
+
+use datafusion_common::{Result, plan_err};
+use serde::Deserialize;
+
+/// Python metadata is checked before touching any native capsule layout.
+#[derive(Debug, Deserialize)]
+#[serde(deny_unknown_fields)]
+pub(super) struct Manifest {
+    pub name: String,
+    pub version: String,
+    pub api_version: u32,
+    pub datafusion_version: String,
+    pub arrow_version: String,
+    pub placement: String,
+    /// A driver-native session quota prepaid from the host's DataFusion pool.
+    #[serde(default)]
+    pub memory_bytes: Option<usize>,
+    pub relation_types: Vec<RelationType>,
+}
+
+#[derive(Debug, Deserialize)]
+#[serde(deny_unknown_fields)]
+pub(super) struct RelationType {
+    pub type_url: String,
+    pub accepts_bare: bool,
+    pub min_inputs: usize,
+    pub max_inputs: usize,
+}
+
+impl Manifest {
+    pub fn validate(&self) -> Result<()> {
+        if self.name.is_empty() || self.version.is_empty() {
+            return plan_err!("extension name and version must not be empty");
+        }
+        if self.api_version != 1
+            || self.datafusion_version != "55.1.0"
+            || self.arrow_version != "59.3.0"
+        {
+            return plan_err!(
+                "extension {} build mismatch: host api=1 DataFusion=55.1.0 Arrow=59.3.0; package api={} DataFusion={} Arrow={}",
+                self.name,
+                self.api_version,
+                self.datafusion_version,
+                self.arrow_version
+            );
+        }
+        if !matches!(self.placement.as_str(), "driver" | "any") {
+            return plan_err!(
+                "extension {} has unsupported placement {}",
+                self.name,
+                self.placement
+            );
+        }
+        if let Some(bytes) = self.memory_bytes
+            && (bytes == 0 || self.placement != "driver")
+        {
+            return plan_err!(
+                "extension {} memory_bytes must be positive and placement must be driver",
+                self.name
+            );
+        }
+        let mut urls = HashSet::new();
+        for relation in &self.relation_types {
+            if relation.type_url.is_empty()
+                || relation.min_inputs > relation.max_inputs
+                || relation.max_inputs > 16
+                || !urls.insert(&relation.type_url)
+            {
+                return plan_err!(
+                    "extension {} has invalid or duplicate relation type {}",
+                    self.name,
+                    relation.type_url
+                );
+            }
+        }
+        Ok(())
+    }
+}
+
+#[cfg(test)]
+mod tests {
+    use super::*;
+
+    fn valid() -> Manifest {
+        Manifest {
+            name: "fixture".into(),
+            version: "1".into(),
+            api_version: 1,
+            datafusion_version: "55.1.0".into(),
+            arrow_version: "59.3.0".into(),
+            placement: "driver".into(),
+            memory_bytes: None,
+            relation_types: vec![],
+        }
+    }
+
+    #[test]
+    fn validates_before_native_layout_access() {
+        assert!(valid().validate().is_ok());
+        let mut manifest = valid();
+        manifest.datafusion_version = "54.1.0".into();
+        assert!(
+            matches!(manifest.validate(), Err(error) if error.to_string().contains("fixture") && error.to_string().contains("55.1.0") && error.to_string().contains("54.1.0"))
+        );
+    }
+
+    #[test]
+    fn rejects_unknown_fields_and_bad_bounds() {
+        assert!(serde_json::from_str::<Manifest>(r#"{"future_layout":2}"#).is_err());
+        let mut manifest = valid();
+        manifest.relation_types.push(RelationType {
+            type_url: "x".into(),
+            accepts_bare: false,
+            min_inputs: 2,
+            max_inputs: 1,
+        });
+        assert!(manifest.validate().is_err());
+    }
+
+    #[test]
+    fn native_session_quota_requires_a_positive_driver_only_cap() {
+        let mut manifest = valid();
+        manifest.memory_bytes = Some(64);
+        assert!(manifest.validate().is_ok());
+        manifest.memory_bytes = Some(0);
+        assert!(manifest.validate().is_err());
+        manifest.memory_bytes = Some(64);
+        manifest.placement = "any".into();
+        assert!(manifest.validate().is_err());
+    }
+}
```

## 49. crates/sail-session/src/extensions/mod.rs {#host-patch-49}

```diff
diff --git a/crates/sail-session/src/extensions/mod.rs b/crates/sail-session/src/extensions/mod.rs
new file mode 100644
index 0000000000000000000000000000000000000000..4bd79a811e2f0cdf1c49c89e2a2b28e54abc9c33
--- /dev/null
+++ b/crates/sail-session/src/extensions/mod.rs
@@ -0,0 +1,420 @@
+//! Experimental, exact-build native packages for local Sail sessions.
+//!
+//! Python metadata is the bootstrap protocol; native objects use DataFusion's
+//! named capsules. This is deliberately not a promise of a stable Sail C ABI.
+mod driver;
+pub(crate) mod graph_utils;
+mod manifest;
+mod plan;
+mod python_owner;
+#[cfg(test)]
+mod resource_tests;
+
+use std::collections::{HashMap, HashSet};
+use std::sync::{Arc, Mutex, OnceLock};
+
+use datafusion::catalog::TableProvider;
+use datafusion::execution::runtime_env::RuntimeEnv;
+use datafusion::physical_plan::ExecutionPlan;
+use datafusion::prelude::SessionConfig;
+use datafusion_common::{DataFusionError, Result, plan_err};
+use datafusion_expr::ScalarUDF;
+use datafusion_ffi::execution_plan::FFI_ExecutionPlan;
+use datafusion_ffi::table_provider::FFI_TableProvider;
+use datafusion_ffi::udf::FFI_ScalarUDF;
+use pyo3::prelude::*;
+use pyo3::types::{PyBytes, PyCapsule, PyCapsuleMethods, PyDict, PyList};
+use sail_catalog::manager::CatalogManager;
+use sail_common::config::ExecutionMode;
+use sail_common_datafusion::connect_extension::{
+    ConnectExtensionRegistry, ConnectRelationHandler, HostInputExec,
+};
+use sail_common_datafusion::driver_extension::DriverExtensionRegistry;
+use sail_common_datafusion::native_resource::{MEMORY_LEASE_CAPSULE, NativeResourceTracker};
+use sail_common_datafusion::native_scalar::{OwnedScalar, retain_scalar};
+use sail_plan::function::is_built_in_function_name;
+
+use self::driver::{DriverTableProvider, InputPlaceholder};
+use self::manifest::Manifest;
+use self::plan::NativeTableProvider;
+use self::python_owner::PythonOwner;
+
+fn py_error(error: impl std::fmt::Display) -> DataFusionError {
+    DataFusionError::Plan(format!("native extension: {error}"))
+}
+
+fn package_identity(
+    py: Python<'_>,
+    entry: &Bound<'_, PyAny>,
+    metadata: &Bound<'_, PyAny>,
+) -> Result<String> {
+    let source = std::ffi::CString::new(include_str!("package_identity.py")).map_err(py_error)?;
+    pyo3::types::PyModule::from_code(
+        py,
+        &source,
+        c"sail_extension_identity.py",
+        c"sail_extension_identity",
+    )
+    .and_then(|module| module.call_method1("identity", (entry, metadata)))
+    .and_then(|value| value.extract())
+    .map_err(py_error)
+}
+
+/// Loaded native code is process-lifetime; session state is never stored here.
+/// This also protects release callbacks in Arrow arrays retained beyond a query.
+fn retain_package(py: Python<'_>, identity: String, factory: &Bound<'_, PyAny>) -> Result<()> {
+    static PACKAGES: OnceLock<Mutex<HashMap<String, Py<PyAny>>>> = OnceLock::new();
+    let mut packages = PACKAGES
+        .get_or_init(Mutex::default)
+        .lock()
+        .map_err(py_error)?;
+    packages
+        .entry(identity)
+        .or_insert_with(|| factory.clone().unbind());
+    let _ = py;
+    Ok(())
+}
+
+struct PythonRelationHandler {
+    owner: Arc<PythonOwner>,
+    type_url: String,
+    identity: String,
+    driver_registry: Option<Arc<DriverExtensionRegistry>>,
+}
+
+impl ConnectRelationHandler for PythonRelationHandler {
+    fn plan(
+        &self,
+        payload: &[u8],
+        inputs: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn TableProvider>> {
+        Python::attach(|py| {
+            let capsules = PyList::empty(py);
+            let mut driver_inputs = Vec::new();
+            let mut names = Vec::new();
+            for input in inputs {
+                let input = if self.driver_registry.is_some() {
+                    let host = input
+                        .downcast_ref::<HostInputExec>()
+                        .ok_or_else(|| py_error("native driver input is missing host adapter"))?;
+                    let input = host.gathered_input();
+                    let name = format!("SailNativeInput_{}", uuid::Uuid::new_v4());
+                    let placeholder = Arc::new(InputPlaceholder {
+                        name: name.clone(),
+                        properties: input.properties().clone(),
+                    });
+                    driver_inputs.push(input);
+                    names.push(name);
+                    placeholder as Arc<dyn ExecutionPlan>
+                } else {
+                    input
+                };
+                let ffi = FFI_ExecutionPlan::new(input, tokio::runtime::Handle::try_current().ok());
+                capsules
+                    .append(
+                        PyCapsule::new_with_value(py, ffi, c"datafusion_execution_plan")
+                            .map_err(py_error)?,
+                    )
+                    .map_err(py_error)?;
+            }
+            let result = self
+                .owner
+                .bind(py)
+                .map_err(py_error)?
+                .call_method1(
+                    "plan_relation",
+                    (&self.type_url, PyBytes::new(py, payload), capsules),
+                )
+                .map_err(|e| py_error(format!("{}: {e}", self.identity)))?;
+            let capsule = result.cast::<PyCapsule>().map_err(py_error)?;
+            let pointer = capsule
+                .pointer_checked(Some(c"datafusion_table_provider"))
+                .map_err(py_error)?;
+            // SAFETY: exact build metadata was checked before binding this handler;
+            // the trusted package promises the named DataFusion capsule layout. No
+            // Python code runs between obtaining the pointer and cloning its owner.
+            let provider = unsafe { pointer.cast::<FFI_TableProvider>().as_ref().clone() };
+            if let Some(registry) = &self.driver_registry {
+                return Ok(Arc::new(DriverTableProvider {
+                    inner: Arc::<dyn TableProvider>::from(&provider),
+                    inputs: driver_inputs,
+                    names,
+                    owner: self.identity.clone(),
+                    registry: registry.clone(),
+                }) as Arc<dyn TableProvider>);
+            }
+            Ok(
+                Arc::new(NativeTableProvider::new(Arc::<dyn TableProvider>::from(
+                    &provider,
+                ))) as Arc<dyn TableProvider>,
+            )
+        })
+    }
+}
+
+/// All installation work happens on a fresh session. Validate every component
+/// before mutating the session's catalog, so a failure cannot expose a partial
+/// extension set to a client.
+pub(crate) fn register_extensions(
+    mut config: SessionConfig,
+    mode: &ExecutionMode,
+    runtime: &Arc<RuntimeEnv>,
+) -> Result<SessionConfig> {
+    let mut registry = ConnectExtensionRegistry::new();
+    if std::env::var("SAIL_EXPERIMENTAL_EXTENSIONS").as_deref() != Ok("1") {
+        config.set_extension(Arc::new(registry));
+        return Ok(config);
+    }
+    let distributed = !matches!(mode, ExecutionMode::Local);
+    let resources = Arc::new(NativeResourceTracker::default());
+    config.set_extension(resources.clone());
+    let driver_registry = Arc::new(DriverExtensionRegistry::default());
+    config.set_extension(driver_registry.clone());
+    let catalog = config
+        .get_extension::<CatalogManager>()
+        .ok_or_else(|| py_error("session catalog is missing"))?;
+    let scalars = Python::attach(|py| -> Result<Vec<ScalarUDF>> {
+        let kwargs = PyDict::new(py);
+        kwargs
+            .set_item("group", "pysail.extensions")
+            .map_err(py_error)?;
+        let entries = py
+            .import("importlib.metadata")
+            .and_then(|m| m.getattr("entry_points"))
+            .and_then(|f| f.call((), Some(&kwargs)))
+            .map_err(py_error)?;
+        let mut entries = entries
+            .try_iter()
+            .map_err(py_error)?
+            .map(|item| {
+                let item = item?;
+                let name = item.getattr("name")?.extract::<String>()?;
+                Ok((name, item))
+            })
+            .collect::<PyResult<Vec<_>>>()
+            .map_err(py_error)?;
+        entries.sort_by(|a, b| a.0.cmp(&b.0));
+        let mut identities = HashSet::new();
+        let mut names = HashSet::new();
+        let mut scalars = Vec::new();
+        // A fresh host-issued incarnation, not a client-selected graph namespace.
+        let incarnation = uuid::Uuid::new_v4().to_string();
+        for (entry_name, entry) in entries {
+            let loaded = entry.call_method0("load").map_err(py_error)?;
+            let factory = if loaded.is_callable() {
+                loaded.call0().map_err(py_error)?
+            } else {
+                loaded
+            };
+            let metadata = factory.call_method0("manifest").map_err(py_error)?;
+            let json = py
+                .import("json")
+                .and_then(|m| m.call_method1("dumps", (&metadata,)))
+                .and_then(|s| s.extract::<String>())
+                .map_err(py_error)?;
+            let manifest: Manifest = serde_json::from_str(&json).map_err(py_error)?;
+            manifest.validate()?;
+            if distributed && manifest.placement != "driver" && !manifest.relation_types.is_empty()
+            {
+                return plan_err!(
+                    "extension {} requires a worker relation codec; only driver-resident relations are supported",
+                    manifest.name
+                );
+            }
+            if !identities.insert(manifest.name.to_ascii_lowercase()) {
+                return plan_err!(
+                    "duplicate native extension name: {} (entry point {entry_name})",
+                    manifest.name
+                );
+            }
+            let identity = package_identity(py, &entry, &metadata)?;
+            retain_package(py, identity.clone(), &factory)?;
+            let bound = if let Some(bytes) = manifest.memory_bytes {
+                let lease = resources.reserve(&runtime.memory_pool, &identity, bytes)?;
+                let capsule =
+                    PyCapsule::new_with_value(py, lease, MEMORY_LEASE_CAPSULE).map_err(py_error)?;
+                factory.call_method1("bind_with_resources", (&incarnation, bytes, capsule))
+            } else {
+                factory.call_method1("bind", (&incarnation,))
+            }
+            .map_err(py_error)?;
+            let owner = Arc::new(PythonOwner::new(bound.unbind()));
+            let functions = owner
+                .bind(py)
+                .map_err(py_error)?
+                .call_method0("scalar_udfs")
+                .map_err(py_error)?;
+            for function in functions.try_iter().map_err(py_error)? {
+                let function = function.map_err(py_error)?;
+                if manifest.placement == "driver" {
+                    return plan_err!(
+                        "driver-only extension {} cannot export scalar functions",
+                        manifest.name
+                    );
+                }
+                let capsule = function
+                    .call_method0("__datafusion_scalar_udf__")
+                    .map_err(py_error)?;
+                let capsule = capsule.cast::<PyCapsule>().map_err(py_error)?;
+                let pointer = capsule
+                    .pointer_checked(Some(c"datafusion_scalar_udf"))
+                    .map_err(py_error)?;
+                // SAFETY: see the provider import above; clone while capsule is live.
+                let ffi = unsafe { pointer.cast::<FFI_ScalarUDF>().as_ref().clone() };
+                let udf = ScalarUDF::new_from_shared_impl((&ffi).into());
+                let mut aliases = vec![udf.name().to_ascii_lowercase()];
+                aliases.extend(udf.aliases().iter().map(|s| s.to_ascii_lowercase()));
+                aliases.sort();
+                aliases.dedup();
+                // Retain both the bound session and the exporting object.
+                let owner: Arc<dyn std::any::Any + Send + Sync> = Arc::new(PythonOwner::new(
+                    (owner.bind(py).map_err(py_error)?, function)
+                        .into_pyobject(py)
+                        .map_err(py_error)?
+                        .into_any()
+                        .unbind(),
+                ));
+                for name in aliases {
+                    if is_built_in_function_name(&name)
+                        || catalog.get_function(&name).map_err(py_error)?.is_some()
+                        || !names.insert(name.clone())
+                    {
+                        return plan_err!(
+                            "extension {} function name collision: {name}",
+                            manifest.name
+                        );
+                    }
+                    let scalar = ScalarUDF::new_from_impl(OwnedScalar {
+                        name,
+                        identity: identity.clone(),
+                        udf: udf.clone(),
+                        owner: Arc::clone(&owner),
+                    });
+                    retain_scalar(scalar.clone())?;
+                    scalars.push(scalar);
+                }
+            }
+            for relation in manifest.relation_types {
+                registry.register(
+                    relation.type_url.clone(),
+                    relation.accepts_bare,
+                    relation.min_inputs,
+                    relation.max_inputs,
+                    Arc::new(PythonRelationHandler {
+                        owner: Arc::clone(&owner),
+                        type_url: relation.type_url,
+                        identity: identity.clone(),
+                        driver_registry: distributed.then(|| driver_registry.clone()),
+                    }),
+                )?;
+            }
+            log::info!("bound native extension {identity} to session incarnation {incarnation}");
+        }
+        Ok(scalars)
+    })?;
+    let graph_scalars = graph_utils::register(
+        &mut config,
+        runtime,
+        &mut registry,
+        distributed.then_some(driver_registry),
+    )?;
+    for udf in scalars.into_iter().chain(graph_scalars) {
+        if catalog
+            .get_function(udf.name())
+            .map_err(py_error)?
+            .is_some()
+        {
+            return plan_err!("extension function name collision: {}", udf.name());
+        }
+        catalog.register_function(udf).map_err(py_error)?;
+    }
+    config.set_extension(Arc::new(registry));
+    Ok(config)
+}
+
+/// Load scalar implementations on an execution worker before it decodes a
+/// distributed physical plan. The worker does not install relation handlers or
+/// mutate the driver catalog; the codec resolves native scalar descriptors from
+/// the process-local registry populated here.
+pub(crate) fn load_worker_extensions() -> Result<()> {
+    graph_utils::register_worker_functions()?;
+    Python::attach(|py| {
+        let kwargs = PyDict::new(py);
+        kwargs
+            .set_item("group", "pysail.extensions")
+            .map_err(py_error)?;
+        let entries = py
+            .import("importlib.metadata")
+            .and_then(|m| m.getattr("entry_points"))
+            .and_then(|f| f.call((), Some(&kwargs)))
+            .map_err(py_error)?;
+        for entry in entries.try_iter().map_err(py_error)? {
+            let entry = entry.map_err(py_error)?;
+            let loaded = entry.call_method0("load").map_err(py_error)?;
+            let factory = if loaded.is_callable() {
+                loaded.call0().map_err(py_error)?
+            } else {
+                loaded
+            };
+            let metadata = factory.call_method0("manifest").map_err(py_error)?;
+            let json = py
+                .import("json")
+                .and_then(|m| m.call_method1("dumps", (&metadata,)))
+                .and_then(|s| s.extract::<String>())
+                .map_err(py_error)?;
+            let manifest: Manifest = serde_json::from_str(&json).map_err(py_error)?;
+            manifest.validate()?;
+            if manifest.placement == "driver" {
+                continue;
+            }
+            let identity = package_identity(py, &entry, &metadata)?;
+            retain_package(py, identity.clone(), &factory)?;
+            log::info!(
+                "worker loaded native extension {identity}, pid={}",
+                std::process::id()
+            );
+            let owner = factory
+                .call_method1("bind", (format!("worker-{identity}"),))
+                .map_err(py_error)?;
+            for function in owner
+                .call_method0("scalar_udfs")
+                .map_err(py_error)?
+                .try_iter()
+                .map_err(py_error)?
+            {
+                let function = function.map_err(py_error)?;
+                let capsule = function
+                    .call_method0("__datafusion_scalar_udf__")
+                    .map_err(py_error)?;
+                let capsule = capsule.cast::<PyCapsule>().map_err(py_error)?;
+                let pointer = capsule
+                    .pointer_checked(Some(c"datafusion_scalar_udf"))
+                    .map_err(py_error)?;
+                // SAFETY: the validated capsule owns an FFI_ScalarUDF, and the
+                // Python owner/function are retained below for its full lifetime.
+                let ffi = unsafe { pointer.cast::<FFI_ScalarUDF>().as_ref().clone() };
+                let udf = ScalarUDF::new_from_shared_impl((&ffi).into());
+                let owner: Arc<dyn std::any::Any + Send + Sync> = Arc::new(
+                    (owner.clone(), function)
+                        .into_pyobject(py)
+                        .map_err(py_error)?
+                        .into_any()
+                        .unbind(),
+                );
+                let mut names = vec![udf.name().to_ascii_lowercase()];
+                names.extend(udf.aliases().iter().map(|name| name.to_ascii_lowercase()));
+                names.sort_unstable();
+                names.dedup();
+                for name in names {
+                    retain_scalar(ScalarUDF::new_from_impl(OwnedScalar {
+                        name,
+                        identity: identity.clone(),
+                        udf: udf.clone(),
+                        owner: Arc::clone(&owner),
+                    }))?;
+                }
+            }
+        }
+        Ok(())
+    })
+}
```

## 50. crates/sail-session/src/extensions/package_identity.py {#host-patch-50}

```diff
diff --git a/crates/sail-session/src/extensions/package_identity.py b/crates/sail-session/src/extensions/package_identity.py
new file mode 100644
index 0000000000000000000000000000000000000000..f2e13a1b887ac5fa06dcc0fe59b5f2e7d931de04
--- /dev/null
+++ b/crates/sail-session/src/extensions/package_identity.py
@@ -0,0 +1,26 @@
+"""Content identity for installed native wheels and immutable manifest options."""
+import hashlib
+import json
+
+
+def identity(entry, manifest):
+    digest = hashlib.sha256()
+    digest.update(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode())
+    files = entry.dist.files
+    if not files:
+        raise ValueError("native extension needs an installed wheel file manifest")
+    count = 0
+    for relative in sorted(files, key=str):
+        name = str(relative)
+        if ".dist-info/" in name or "__pycache__/" in name or name.endswith(".pyc"):
+            continue
+        path = entry.dist.locate_file(relative)
+        if not path.is_file():
+            raise ValueError(f"native extension package file missing: {relative}")
+        digest.update(name.encode() + b"\0")
+        with path.open("rb") as stream:
+            digest.update(hashlib.file_digest(stream, "sha256").digest())
+        count += 1
+    if count == 0:
+        raise ValueError("native extension wheel contains no package files")
+    return f"{manifest['name']}@{manifest['version']}:{digest.hexdigest()}"
```

## 51. crates/sail-session/src/extensions/plan.rs {#host-patch-51}

```diff
diff --git a/crates/sail-session/src/extensions/plan.rs b/crates/sail-session/src/extensions/plan.rs
new file mode 100644
index 0000000000000000000000000000000000000000..b189616806e6169a538e07668f9d098fef4f199f
--- /dev/null
+++ b/crates/sail-session/src/extensions/plan.rs
@@ -0,0 +1,126 @@
+//! Local physical-plan boundary for an already-planned native relation.
+//!
+//! DataFusion's FFI does not preserve all input requirements, and foreign child
+//! replacement can export host-added nodes without a host Tokio runtime. Do not
+//! let the outer host optimizer rewrite this mixed-library execution region.
+
+use std::fmt::{Formatter, Result as FmtResult};
+use std::sync::Arc;
+
+use arrow_schema::SchemaRef;
+use async_trait::async_trait;
+use datafusion::catalog::{Session, TableProvider};
+use datafusion::execution::{SendableRecordBatchStream, TaskContext};
+use datafusion::physical_expr::PhysicalExpr;
+use datafusion::physical_plan::{DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties};
+use datafusion_common::tree_node::TreeNodeRecursion;
+use datafusion_common::{Result, Statistics, plan_err};
+use datafusion_expr::{Expr, TableProviderFilterPushDown, TableType};
+
+#[derive(Debug)]
+pub(super) struct NativeTableProvider {
+    inner: Arc<dyn TableProvider>,
+}
+
+impl NativeTableProvider {
+    pub fn new(inner: Arc<dyn TableProvider>) -> Self {
+        Self { inner }
+    }
+}
+
+#[async_trait]
+impl TableProvider for NativeTableProvider {
+    fn schema(&self) -> SchemaRef {
+        self.inner.schema()
+    }
+
+    fn table_type(&self) -> TableType {
+        self.inner.table_type()
+    }
+
+    fn supports_filters_pushdown(
+        &self,
+        filters: &[&Expr],
+    ) -> Result<Vec<TableProviderFilterPushDown>> {
+        self.inner.supports_filters_pushdown(filters)
+    }
+
+    fn statistics(&self) -> Option<Statistics> {
+        self.inner.statistics()
+    }
+
+    async fn scan(
+        &self,
+        session: &dyn Session,
+        projection: Option<&Vec<usize>>,
+        filters: &[Expr],
+        limit: Option<usize>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        let inner = self.inner.scan(session, projection, filters, limit).await?;
+        Ok(Arc::new(NativeRelationExec {
+            inner,
+            // Keep provider-owned native resources alive with its execution.
+            _provider: Arc::clone(&self.inner),
+        }))
+    }
+}
+
+#[derive(Debug)]
+struct NativeRelationExec {
+    inner: Arc<dyn ExecutionPlan>,
+    _provider: Arc<dyn TableProvider>,
+}
+
+impl DisplayAs for NativeRelationExec {
+    fn fmt_as(&self, _t: DisplayFormatType, f: &mut Formatter<'_>) -> FmtResult {
+        write!(
+            f,
+            "NativeRelationExec: local, opaque_region=true, native={}",
+            self.inner.name()
+        )
+    }
+}
+
+impl ExecutionPlan for NativeRelationExec {
+    fn name(&self) -> &'static str {
+        "NativeRelationExec"
+    }
+
+    fn properties(&self) -> &Arc<PlanProperties> {
+        self.inner.properties()
+    }
+
+    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
+        // Host inputs were optimized before export. The package owns the
+        // complete region below this leaf, including its input distribution.
+        vec![]
+    }
+
+    fn apply_expressions(
+        &self,
+        _f: &mut dyn FnMut(&Arc<dyn PhysicalExpr>) -> Result<TreeNodeRecursion>,
+    ) -> Result<TreeNodeRecursion> {
+        Ok(TreeNodeRecursion::Continue)
+    }
+
+    fn with_new_children(
+        self: Arc<Self>,
+        children: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        if !children.is_empty() {
+            return plan_err!("NativeRelationExec is an opaque leaf and does not accept children");
+        }
+        Ok(self)
+    }
+
+    fn execute(
+        &self,
+        partition: usize,
+        context: Arc<TaskContext>,
+    ) -> Result<SendableRecordBatchStream> {
+        self.inner.execute(partition, context)
+    }
+}
+
+#[cfg(test)]
+mod tests;
```

## 52. crates/sail-session/src/extensions/plan/tests.rs {#host-patch-52}

```diff
diff --git a/crates/sail-session/src/extensions/plan/tests.rs b/crates/sail-session/src/extensions/plan/tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..bbfffd2f512e83c4c7fbd74b7d13e7ce700c96a2
--- /dev/null
+++ b/crates/sail-session/src/extensions/plan/tests.rs
@@ -0,0 +1,90 @@
+use datafusion::arrow::array::Int64Array;
+use datafusion::arrow::datatypes::{DataType, Field, Schema};
+use datafusion::arrow::record_batch::RecordBatch;
+use datafusion::physical_optimizer::PhysicalOptimizerRule;
+use datafusion::physical_optimizer::ensure_requirements::EnsureRequirements;
+use datafusion::physical_plan::coalesce_partitions::CoalescePartitionsExec;
+use datafusion::physical_plan::common::collect;
+use datafusion::physical_plan::displayable;
+use datafusion::prelude::{SessionConfig, SessionContext};
+use datafusion_datasource::memory::MemorySourceConfig;
+use datafusion_ffi::execution_plan::{FFI_ExecutionPlan, ForeignExecutionPlan};
+use sail_common_datafusion::connect_extension::HostInputExec;
+
+use super::*;
+
+#[derive(Debug)]
+struct FixedProvider(Arc<dyn ExecutionPlan>);
+
+#[async_trait]
+impl TableProvider for FixedProvider {
+    fn schema(&self) -> SchemaRef {
+        self.0.schema()
+    }
+    fn table_type(&self) -> TableType {
+        TableType::Temporary
+    }
+    async fn scan(
+        &self,
+        _session: &dyn Session,
+        _projection: Option<&Vec<usize>>,
+        _filters: &[Expr],
+        _limit: Option<usize>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        Ok(Arc::clone(&self.0))
+    }
+}
+
+#[tokio::test]
+async fn native_region_blocks_host_repartition_insertion_inside_ffi_plan() -> Result<()> {
+    // Keep the two-row fixture above the optimizer's one-batch threshold;
+    // otherwise its exact in-memory statistics suppress repartitioning.
+    let ctx = SessionContext::new_with_config(
+        SessionConfig::new()
+            .with_target_partitions(4)
+            .with_batch_size(1),
+    );
+    let state = ctx.state();
+    let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)]));
+    let batch = RecordBatch::try_new(schema.clone(), vec![Arc::new(Int64Array::from(vec![1, 2]))])?;
+    let source = MemorySourceConfig::try_new_exec(&[vec![batch]], schema, None)?;
+    let input = Arc::new(HostInputExec::new(
+        source,
+        ctx.task_ctx(),
+        tokio::runtime::Handle::current(),
+    ));
+    // Force the actual foreign adapter even in this one-library fixture. Its
+    // default input requirements permit host repartitioning of its local child.
+    let ffi = FFI_ExecutionPlan::new(
+        Arc::new(CoalescePartitionsExec::new(input)),
+        Some(tokio::runtime::Handle::current()),
+    );
+    let foreign: Arc<dyn ExecutionPlan> = Arc::new(ForeignExecutionPlan::try_from(ffi)?);
+    assert!(!foreign.children().is_empty());
+    let optimizer = EnsureRequirements::new();
+    let rewritten = optimizer.optimize(Arc::clone(&foreign), state.config_options())?;
+    assert!(
+        displayable(rewritten.as_ref())
+            .indent(true)
+            .to_string()
+            .contains("RepartitionExec"),
+        "fixture must reproduce host insertion within an exposed foreign graph"
+    );
+
+    let provider = NativeTableProvider::new(Arc::new(FixedProvider(Arc::clone(&foreign))));
+    let plan = provider.scan(&state, None, &[], None).await?;
+    assert_eq!(plan.schema(), foreign.schema());
+    assert!(Arc::ptr_eq(plan.properties(), foreign.properties()));
+    let plan = optimizer.optimize(plan, state.config_options())?;
+    assert_eq!(plan.name(), "NativeRelationExec");
+    assert!(plan.children().is_empty());
+    #[expect(deprecated)]
+    let unchanged = Arc::clone(&plan).with_new_children(vec![])?;
+    #[expect(deprecated)]
+    let rejected = Arc::clone(&plan).with_new_children(vec![foreign]);
+    assert!(rejected.is_err());
+    assert!(Arc::ptr_eq(&plan, &unchanged));
+    let batches = collect(plan.execute(0, ctx.task_ctx())?).await?;
+    assert_eq!(batches.iter().map(RecordBatch::num_rows).sum::<usize>(), 2);
+    Ok(())
+}
```

## 53. crates/sail-session/src/extensions/python_owner.rs {#host-patch-53}

```diff
diff --git a/crates/sail-session/src/extensions/python_owner.rs b/crates/sail-session/src/extensions/python_owner.rs
new file mode 100644
index 0000000000000000000000000000000000000000..21651b1340b18817c6828c5cf1d492eaaa994560
--- /dev/null
+++ b/crates/sail-session/src/extensions/python_owner.rs
@@ -0,0 +1,66 @@
+use pyo3::prelude::*;
+
+/// Finalize session-owned Python objects when the last native owner is dropped.
+/// PyO3 otherwise queues a decref outside the GIL until a later Python entry,
+/// which can retain native session quotas indefinitely on an idle server.
+pub(super) struct PythonOwner(Option<Py<PyAny>>);
+
+impl PythonOwner {
+    pub(super) fn new(value: Py<PyAny>) -> Self {
+        Self(Some(value))
+    }
+
+    pub(super) fn bind<'py>(&self, py: Python<'py>) -> PyResult<&Bound<'py, PyAny>> {
+        self.0.as_ref().map(|value| value.bind(py)).ok_or_else(|| {
+            pyo3::exceptions::PyRuntimeError::new_err("native Python owner was already dropped")
+        })
+    }
+}
+
+impl Drop for PythonOwner {
+    fn drop(&mut self) {
+        if let Some(value) = self.0.take() {
+            Python::attach(|_| drop(value));
+        }
+    }
+}
+
+#[cfg(test)]
+mod tests {
+    use std::sync::Arc;
+    use std::sync::atomic::{AtomicUsize, Ordering};
+
+    use pyo3::types::PyCapsule;
+
+    use super::*;
+
+    struct Released(Arc<AtomicUsize>);
+
+    impl Drop for Released {
+        fn drop(&mut self) {
+            self.0.fetch_add(1, Ordering::SeqCst);
+        }
+    }
+
+    #[test]
+    fn last_owner_releases_without_a_later_python_request() -> PyResult<()> {
+        Python::initialize();
+        let released = Arc::new(AtomicUsize::new(0));
+        let owner = Python::attach(|py| -> PyResult<_> {
+            Ok(Arc::new(PythonOwner::new(
+                PyCapsule::new_with_value(py, Released(released.clone()), c"resource_test")?
+                    .into_any()
+                    .unbind(),
+            )))
+        })?;
+        let output_owner = owner.clone();
+        drop(owner);
+        assert_eq!(released.load(Ordering::SeqCst), 0);
+        // No further request, Python attachment, or GC occurs after this drop.
+        std::thread::spawn(move || drop(output_owner))
+            .join()
+            .map_err(|_| pyo3::exceptions::PyRuntimeError::new_err("owner thread panicked"))?;
+        assert_eq!(released.load(Ordering::SeqCst), 1);
+        Ok(())
+    }
+}
```

## 54. crates/sail-session/src/extensions/resource_tests.rs {#host-patch-54}

```diff
diff --git a/crates/sail-session/src/extensions/resource_tests.rs b/crates/sail-session/src/extensions/resource_tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..a755517229c96ceba2b0be23932dacf0cc2d0f10
--- /dev/null
+++ b/crates/sail-session/src/extensions/resource_tests.rs
@@ -0,0 +1,188 @@
+use std::fmt::Formatter;
+use std::io::Write;
+use std::sync::Arc;
+
+use datafusion::arrow::datatypes::Schema;
+use datafusion::arrow::record_batch::RecordBatch;
+use datafusion::execution::disk_manager::{DiskManagerBuilder, DiskManagerMode};
+use datafusion::execution::memory_pool::{GreedyMemoryPool, MemoryConsumer, MemoryPool};
+use datafusion::execution::runtime_env::RuntimeEnvBuilder;
+use datafusion::execution::{SendableRecordBatchStream, TaskContext};
+use datafusion::physical_expr::PhysicalExpr;
+use datafusion::physical_plan::common::collect;
+use datafusion::physical_plan::empty::EmptyExec;
+use datafusion::physical_plan::stream::RecordBatchStreamAdapter;
+use datafusion::physical_plan::{DisplayAs, DisplayFormatType, ExecutionPlan, PlanProperties};
+use datafusion::prelude::{SessionConfig, SessionContext};
+use datafusion_common::tree_node::TreeNodeRecursion;
+use datafusion_common::{Result, plan_err};
+use datafusion_ffi::execution_plan::{FFI_ExecutionPlan, ForeignExecutionPlan};
+use sail_common_datafusion::connect_extension::HostInputExec;
+use sail_common_datafusion::native_resource::reserve_native_quota;
+
+/// A participating host input whose fixed reservation gives the pressure test
+/// an exact boundary independent of allocator sizes or DataFusion heuristics.
+#[derive(Debug)]
+struct ReservingInput {
+    bytes: usize,
+    spill_bytes: usize,
+    properties: Arc<PlanProperties>,
+}
+
+impl DisplayAs for ReservingInput {
+    fn fmt_as(&self, _: DisplayFormatType, f: &mut Formatter<'_>) -> std::fmt::Result {
+        write!(f, "ReservingInput: bytes={}", self.bytes)
+    }
+}
+
+impl ExecutionPlan for ReservingInput {
+    fn name(&self) -> &str {
+        "ReservingInput"
+    }
+    fn properties(&self) -> &Arc<PlanProperties> {
+        &self.properties
+    }
+    fn children(&self) -> Vec<&Arc<dyn ExecutionPlan>> {
+        vec![]
+    }
+    fn apply_expressions(
+        &self,
+        _: &mut dyn FnMut(&Arc<dyn PhysicalExpr>) -> Result<TreeNodeRecursion>,
+    ) -> Result<TreeNodeRecursion> {
+        Ok(TreeNodeRecursion::Continue)
+    }
+    fn with_new_children(
+        self: Arc<Self>,
+        children: Vec<Arc<dyn ExecutionPlan>>,
+    ) -> Result<Arc<dyn ExecutionPlan>> {
+        if !children.is_empty() {
+            return plan_err!("reserving input has no children");
+        }
+        Ok(self)
+    }
+    fn execute(&self, _: usize, context: Arc<TaskContext>) -> Result<SendableRecordBatchStream> {
+        let reservation =
+            MemoryConsumer::new("foreign parent host input").register(context.memory_pool());
+        reservation.try_grow(self.bytes)?;
+        let spill = if self.spill_bytes > 0 {
+            let file = context
+                .runtime_env()
+                .disk_manager
+                .create_tmp_file("foreign input spill")?;
+            let mut writer = file.open_writer()?;
+            writer.write_all(&vec![0; self.spill_bytes])?;
+            writer.finish()?;
+            Some(file)
+        } else {
+            None
+        };
+        let schema = self.schema();
+        Ok(Box::pin(RecordBatchStreamAdapter::new(
+            schema.clone(),
+            futures::stream::once(async move {
+                let _reservation = reservation;
+                let _spill = spill;
+                Ok(RecordBatch::new_empty(schema))
+            }),
+        )))
+    }
+}
+
+#[tokio::test]
+async fn foreign_input_refuses_host_pressure_instead_of_using_an_unbounded_default() -> Result<()> {
+    let pool: Arc<dyn MemoryPool> = Arc::new(GreedyMemoryPool::new(128));
+    let runtime = Arc::new(
+        RuntimeEnvBuilder::default()
+            .with_memory_pool(pool.clone())
+            .build()?,
+    );
+    let host = SessionContext::new_with_config_rt(SessionConfig::new(), runtime);
+    let quota = reserve_native_quota(&pool, "nutmeg-test", 96)?;
+    let input: Arc<dyn ExecutionPlan> = Arc::new(ReservingInput {
+        bytes: 33,
+        spill_bytes: 0,
+        properties: EmptyExec::new(Arc::new(Schema::empty()))
+            .properties()
+            .clone(),
+    });
+    let foreign_context = Arc::new(TaskContext::default());
+    // Control proves that losing the host's pool would silently admit the work.
+    collect(input.execute(0, foreign_context.clone())?).await?;
+    let adapter = Arc::new(HostInputExec::new(
+        input,
+        host.task_ctx(),
+        tokio::runtime::Handle::current(),
+    ));
+    let ffi = FFI_ExecutionPlan::new(adapter, Some(tokio::runtime::Handle::current()));
+    // Force the real foreign adapter, bypassing its same-library shortcut.
+    let foreign: Arc<dyn ExecutionPlan> = Arc::new(ForeignExecutionPlan::try_from(ffi)?);
+    let result = match foreign.execute(0, foreign_context.clone()) {
+        Ok(stream) => collect(stream).await.map(|_| ()),
+        Err(error) => Err(error),
+    };
+    let message = match result {
+        Ok(()) => return plan_err!("96 native + 33 input unexpectedly fitted the 128-byte pool"),
+        Err(error) => error.to_string(),
+    };
+    assert!(message.contains("Resources exhausted"), "{message}");
+    assert!(message.contains("foreign parent host input"), "{message}");
+    assert_eq!(
+        pool.reserved(),
+        96,
+        "refused host input must leak no reservation"
+    );
+    drop(quota);
+    collect(foreign.execute(0, foreign_context)?).await?;
+    assert_eq!(pool.reserved(), 0);
+    Ok(())
+}
+
+#[tokio::test]
+async fn foreign_input_preserves_disabled_and_exhausted_host_spill_policies() -> Result<()> {
+    for (mode, expected) in [
+        (DiskManagerMode::Disabled, "DiskManager is disabled"),
+        (
+            DiskManagerMode::OsTmpDirectory,
+            "spilling process has exceeded the allowable limit",
+        ),
+    ] {
+        let runtime = Arc::new(
+            RuntimeEnvBuilder::default()
+                .with_disk_manager_builder(
+                    DiskManagerBuilder::default()
+                        .with_mode(mode)
+                        .with_max_temp_directory_size(1),
+                )
+                .build()?,
+        );
+        let host = SessionContext::new_with_config_rt(SessionConfig::new(), runtime.clone());
+        let input: Arc<dyn ExecutionPlan> = Arc::new(ReservingInput {
+            bytes: 0,
+            spill_bytes: 2,
+            properties: EmptyExec::new(Arc::new(Schema::empty()))
+                .properties()
+                .clone(),
+        });
+        let foreign_context = Arc::new(TaskContext::default());
+        // Losing the disk policy would permit this exact two-byte spill.
+        collect(input.execute(0, foreign_context.clone())?).await?;
+        let adapted = Arc::new(HostInputExec::new(
+            input,
+            host.task_ctx(),
+            tokio::runtime::Handle::current(),
+        ));
+        let ffi = FFI_ExecutionPlan::new(adapted, Some(tokio::runtime::Handle::current()));
+        let foreign = ForeignExecutionPlan::try_from(ffi)?;
+        let result = match foreign.execute(0, foreign_context) {
+            Ok(stream) => collect(stream).await.map(|_| ()),
+            Err(error) => Err(error),
+        };
+        let message = match result {
+            Ok(()) => return plan_err!("foreign input ignored its host spill policy"),
+            Err(error) => error.to_string(),
+        };
+        assert!(message.contains(expected), "{message}");
+        assert_eq!(runtime.disk_manager.used_disk_space(), 0);
+    }
+    Ok(())
+}
```

## 55. crates/sail-session/src/lib.rs {#host-patch-55}

```diff
diff --git a/crates/sail-session/src/lib.rs b/crates/sail-session/src/lib.rs
index fb388c54b86705fb9c2566fddf051765a85aac48..25fd67d0e5b9427b869085bd5958b9d3b855a05e 100644
--- a/crates/sail-session/src/lib.rs
+++ b/crates/sail-session/src/lib.rs
@@ -1,5 +1,6 @@
 pub mod catalog;
 pub mod error;
+mod extensions;
 pub mod formats;
 pub mod optimizer;
 pub mod planner;
```

## 56. crates/sail-session/src/runtime.rs {#host-patch-56}

```diff
diff --git a/crates/sail-session/src/runtime.rs b/crates/sail-session/src/runtime.rs
index d0004dc4d763b98a05da438072cf7828b8d662c8..1807e9bed7656ea78eab75ddaa49886cc292211a 100644
--- a/crates/sail-session/src/runtime.rs
+++ b/crates/sail-session/src/runtime.rs
@@ -1,22 +1,19 @@
 use std::sync::Arc;
 
+mod memory;
 use datafusion::execution::DiskManager;
 use datafusion::execution::cache::cache_manager::{
     CacheManagerConfig, FileMetadataCache, FileStatisticsCache, ListFilesCache,
 };
 use datafusion::execution::disk_manager::{DiskManagerBuilder, DiskManagerMode};
-use datafusion::execution::memory_pool::{
-    FairSpillPool, GreedyMemoryPool, MemoryPool, UnboundedMemoryPool,
-};
 use datafusion::execution::runtime_env::{RuntimeEnv, RuntimeEnvBuilder};
 use datafusion_common::Result;
 use log::debug;
+pub use memory::MemoryResourceDomain;
 use sail_cache::file_listing_cache::MokaFileListingCache;
 use sail_cache::file_metadata_cache::MokaFileMetadataCache;
 use sail_cache::file_statistics_cache::MokaFileStatisticsCache;
-use sail_common::config::{
-    AppConfig, CacheType, FairMemoryPoolConfig, GreedyMemoryPoolConfig, MemoryPoolConfig,
-};
+use sail_common::config::{AppConfig, CacheType};
 use sail_common::runtime::RuntimeHandle;
 use sail_object_store::DynamicObjectStoreRegistry;
 
@@ -39,7 +36,11 @@ impl RuntimeEnvFactory {
         }
     }
 
-    pub fn create<M>(&mut self, mutator: M) -> Result<Arc<RuntimeEnv>>
+    pub fn create<M>(
+        &mut self,
+        domain: Option<&MemoryResourceDomain>,
+        mutator: M,
+    ) -> Result<Arc<RuntimeEnv>>
     where
         M: FnOnce(RuntimeEnvBuilder) -> Result<RuntimeEnvBuilder>,
     {
@@ -63,24 +64,15 @@ impl RuntimeEnvFactory {
         let builder = RuntimeEnvBuilder::default()
             .with_object_store_registry(Arc::new(registry))
             .with_cache_manager(cache_config)
-            .with_memory_pool(self.create_memory_pool())
+            .with_memory_pool(domain.map_or_else(
+                || memory::new_pool(&self.config.runtime.memory_pool),
+                MemoryResourceDomain::pool,
+            ))
             .with_disk_manager_builder(self.create_disk_manager_builder());
         let builder = mutator(builder)?;
         Ok(Arc::new(builder.build()?))
     }
 
-    fn create_memory_pool(&self) -> Arc<dyn MemoryPool> {
-        match self.config.runtime.memory_pool {
-            MemoryPoolConfig::Unbounded => Arc::new(UnboundedMemoryPool::default()),
-            MemoryPoolConfig::Greedy(GreedyMemoryPoolConfig { max_size }) => {
-                Arc::new(GreedyMemoryPool::new(max_size))
-            }
-            MemoryPoolConfig::Fair(FairMemoryPoolConfig { max_size }) => {
-                Arc::new(FairSpillPool::new(max_size))
-            }
-        }
-    }
-
     fn create_disk_manager_builder(&self) -> DiskManagerBuilder {
         let max_size = self.config.runtime.temporary_files.max_size;
         let paths = self.config.runtime.temporary_files.paths.as_slice();
```

## 57. crates/sail-session/src/runtime/memory.rs {#host-patch-57}

```diff
diff --git a/crates/sail-session/src/runtime/memory.rs b/crates/sail-session/src/runtime/memory.rs
new file mode 100644
index 0000000000000000000000000000000000000000..47252029f88a445fdac3eb120b74772c0bf445cc
--- /dev/null
+++ b/crates/sail-session/src/runtime/memory.rs
@@ -0,0 +1,126 @@
+//! Explicit admission domains. Configuration equality never implies shared ownership.
+use std::sync::Arc;
+
+use datafusion::execution::memory_pool::{
+    FairSpillPool, GreedyMemoryPool, MemoryPool, UnboundedMemoryPool,
+};
+use sail_common::config::{FairMemoryPoolConfig, GreedyMemoryPoolConfig, MemoryPoolConfig};
+
+/// One explicitly owned admission domain. Clone this value to share admission;
+/// constructing another domain, even with identical settings, creates isolation.
+/// The standard server owns one per session manager and injects it into its
+/// sessions and in-process workers. Separate worker processes own their own.
+#[derive(Clone, Debug)]
+pub struct MemoryResourceDomain {
+    pool: Arc<dyn MemoryPool>,
+}
+
+impl MemoryResourceDomain {
+    pub fn new(config: &MemoryPoolConfig) -> Self {
+        Self {
+            pool: new_pool(config),
+        }
+    }
+
+    pub fn pool(&self) -> Arc<dyn MemoryPool> {
+        self.pool.clone()
+    }
+}
+
+pub(super) fn new_pool(config: &MemoryPoolConfig) -> Arc<dyn MemoryPool> {
+    match config {
+        MemoryPoolConfig::Unbounded => Arc::new(UnboundedMemoryPool::default()),
+        MemoryPoolConfig::Greedy(GreedyMemoryPoolConfig { max_size }) => {
+            Arc::new(GreedyMemoryPool::new(*max_size))
+        }
+        MemoryPoolConfig::Fair(FairMemoryPoolConfig { max_size }) => {
+            Arc::new(FairSpillPool::new(*max_size))
+        }
+    }
+}
+
+#[cfg(test)]
+mod tests {
+    use datafusion::execution::memory_pool::MemoryConsumer;
+    use sail_common_datafusion::native_resource::reserve_native_quota;
+
+    use super::*;
+
+    #[test]
+    fn explicit_clones_contend_but_equal_config_domains_are_isolated()
+    -> datafusion_common::Result<()> {
+        for config in [
+            MemoryPoolConfig::Greedy(GreedyMemoryPoolConfig { max_size: 113 }),
+            MemoryPoolConfig::Fair(FairMemoryPoolConfig { max_size: 113 }),
+        ] {
+            let domain = MemoryResourceDomain::new(&config);
+            let worker = domain.clone();
+            let unrelated = MemoryResourceDomain::new(&config);
+            assert!(Arc::ptr_eq(&domain.pool(), &worker.pool()));
+            assert!(!Arc::ptr_eq(&domain.pool(), &unrelated.pool()));
+            let a = reserve_native_quota(&domain.pool(), "session-a", 64)?;
+            let b = reserve_native_quota(&domain.pool(), "session-b", 32)?;
+            let query = MemoryConsumer::new("worker join").register(&worker.pool());
+            assert!(query.try_grow(18).is_err());
+            query.try_grow(17)?;
+            let other = reserve_native_quota(&unrelated.pool(), "other-server", 113)?;
+            assert_eq!(domain.pool().reserved(), 113);
+            drop(domain);
+            // A lease and an explicitly shared worker keep admission alive.
+            drop(a);
+            assert_eq!(worker.pool().reserved(), 49);
+            assert_eq!(unrelated.pool().reserved(), 113);
+            query.try_grow(64)?;
+            drop(b);
+            drop(query);
+            assert_eq!(worker.pool().reserved(), 0);
+            drop(other);
+            assert_eq!(unrelated.pool().reserved(), 0);
+        }
+        Ok(())
+    }
+    #[tokio::test]
+    async fn runtime_factories_share_only_the_injected_domain() -> datafusion_common::Result<()> {
+        use sail_common::config::AppConfig;
+        use sail_common::runtime::RuntimeHandle;
+
+        use crate::runtime::RuntimeEnvFactory;
+
+        let mut config = AppConfig::load()
+            .map_err(|e| datafusion_common::DataFusionError::External(Box::new(e)))?;
+        config.runtime.memory_pool =
+            MemoryPoolConfig::Greedy(GreedyMemoryPoolConfig { max_size: 113 });
+        let domain = MemoryResourceDomain::new(&config.runtime.memory_pool);
+        let other = MemoryResourceDomain::new(&config.runtime.memory_pool);
+        let handle = tokio::runtime::Handle::current();
+        let runtime = RuntimeHandle::new(handle.clone(), handle);
+        let config = Arc::new(config);
+        let mut server = RuntimeEnvFactory::new(config.clone(), runtime.clone());
+        let mut worker = RuntimeEnvFactory::new(config, runtime);
+        let a = server.create(Some(&domain), Ok)?;
+        let b = server.create(Some(&domain), Ok)?;
+        let w = worker.create(Some(&domain), Ok)?;
+        let unrelated = server.create(Some(&other), Ok)?;
+        let standalone = server.create(None, Ok)?;
+        let standalone2 = server.create(None, Ok)?;
+        assert!(Arc::ptr_eq(&a.memory_pool, &b.memory_pool));
+        assert!(Arc::ptr_eq(&a.memory_pool, &w.memory_pool));
+        assert!(!Arc::ptr_eq(&a.memory_pool, &unrelated.memory_pool));
+        assert!(!Arc::ptr_eq(&a.memory_pool, &standalone.memory_pool));
+        assert!(!Arc::ptr_eq(
+            &standalone.memory_pool,
+            &standalone2.memory_pool
+        ));
+        let native = reserve_native_quota(&a.memory_pool, "native", 100)?;
+        let query = MemoryConsumer::new("worker").register(&w.memory_pool);
+        assert!(query.try_grow(14).is_err());
+        query.try_grow(13)?;
+        let independent = reserve_native_quota(&unrelated.memory_pool, "independent", 113)?;
+        drop(native);
+        drop(query);
+        drop(independent);
+        assert_eq!(a.memory_pool.reserved(), 0);
+        assert_eq!(unrelated.memory_pool.reserved(), 0);
+        Ok(())
+    }
+}
```

## 58. crates/sail-session/src/session_factory/job_runner.rs {#host-patch-58}

```diff
diff --git a/crates/sail-session/src/session_factory/job_runner.rs b/crates/sail-session/src/session_factory/job_runner.rs
index 616b0855ba3c31c716fe5275ee959d823aaf2013..85038a84ce4301cf7f8d38b0b0e2315ca5ba5cfd 100644
--- a/crates/sail-session/src/session_factory/job_runner.rs
+++ b/crates/sail-session/src/session_factory/job_runner.rs
@@ -13,6 +13,7 @@ use sail_execution::worker_manager::{
 use sail_telemetry::events::SystemEventReporter;
 
 use crate::error::{SessionError, SessionResult};
+use crate::runtime::MemoryResourceDomain;
 use crate::session_factory::{SessionFactory, WorkerSessionFactory};
 
 pub struct SessionJobRunner {
@@ -42,6 +43,7 @@ impl SessionJobRunner {
 }
 
 pub struct SessionJobRunnerInfo {
+    pub resource_domain: Option<MemoryResourceDomain>,
     pub session_id: String,
     pub driver_id: DriverId,
     pub driver_server_port: Option<u16>,
@@ -103,8 +105,16 @@ impl SessionJobRunnerFactory for ServerSessionJobRunnerFactory {
                 info.session_id,
             ))),
             ExecutionMode::LocalCluster => {
+                if std::env::var("SAIL_EXPERIMENTAL_PROCESS_WORKERS").as_deref() == Ok("1") {
+                    return self.create_cluster_runner(
+                        system,
+                        info,
+                        Box::new(sail_execution::worker_manager::ProcessWorkerManager::default()),
+                    );
+                }
                 let worker_session =
                     WorkerSessionFactory::new(self.config.clone(), self.runtime.clone())
+                        .with_resource_domain(info.resource_domain.clone())
                         .create(())?;
                 self.create_cluster_runner(
                     system,
```

## 59. crates/sail-session/src/session_factory/server.rs {#host-patch-59}

```diff
diff --git a/crates/sail-session/src/session_factory/server.rs b/crates/sail-session/src/session_factory/server.rs
index 2828250fd36a6115dade54f9d70f177ea559722e..c187fd8f023d518937ccde24067ded62020907b7 100644
--- a/crates/sail-session/src/session_factory/server.rs
+++ b/crates/sail-session/src/session_factory/server.rs
@@ -26,11 +26,12 @@ use crate::catalog::create_catalog_manager;
 use crate::formats::create_data_source_registry;
 use crate::optimizer::{default_analyzer_rules, default_optimizer_rules};
 use crate::planner::new_query_planner;
-use crate::runtime::RuntimeEnvFactory;
+use crate::runtime::{MemoryResourceDomain, RuntimeEnvFactory};
 use crate::session_factory::SessionFactory;
 use crate::session_manager::SessionManagerActor;
 
 pub struct ServerSessionInfo {
+    pub resource_domain: Option<MemoryResourceDomain>,
     pub session_id: String,
     pub user_id: String,
     pub session_manager: ActorHandle<SessionManagerActor>,
@@ -130,15 +131,17 @@ impl ServerSessionFactory {
         self.apply_execution_config(&mut config)?;
         self.apply_execution_parquet_config(&mut config);
         self.apply_optimizer_config(&mut config)?;
-        let config = self.mutator.mutate_config(config, info)?;
-        Ok(config)
+        self.mutator.mutate_config(config, info)
     }
 
     fn create_session_state(&mut self, info: &mut ServerSessionInfo) -> Result<SessionState> {
         let config = self.create_session_config(info)?;
         let runtime = self
             .runtime_env
-            .create(|builder| self.mutator.mutate_runtime_env(builder, info))?;
+            .create(info.resource_domain.as_ref(), |builder| {
+                self.mutator.mutate_runtime_env(builder, info)
+            })?;
+        let config = crate::extensions::register_extensions(config, &self.config.mode, &runtime)?;
         // We do not add default features to the session state,
         // since we manage data sources and functions ourselves.
         let builder = SessionStateBuilder::new()
```

## 60. crates/sail-session/src/session_factory/worker.rs {#host-patch-60}

```diff
diff --git a/crates/sail-session/src/session_factory/worker.rs b/crates/sail-session/src/session_factory/worker.rs
index 9ad40ec869dd566bcf6565f70481b3a2c26a877f..311cd38d61fc379e85ff7062519bebb84a30d717 100644
--- a/crates/sail-session/src/session_factory/worker.rs
+++ b/crates/sail-session/src/session_factory/worker.rs
@@ -9,10 +9,11 @@ use sail_common::runtime::RuntimeHandle;
 use sail_common_datafusion::session::repartition::RepartitionBufferConfig;
 use sail_delta_lake::session_extension::DeltaTableCache;
 
-use crate::runtime::RuntimeEnvFactory;
+use crate::runtime::{MemoryResourceDomain, RuntimeEnvFactory};
 use crate::session_factory::SessionFactory;
 
 pub struct WorkerSessionFactory {
+    resource_domain: Option<MemoryResourceDomain>,
     runtime_env: RuntimeEnvFactory,
     batch_size: usize,
     repartition_buffer_size: usize,
@@ -22,18 +23,28 @@ impl WorkerSessionFactory {
     pub fn new(config: Arc<AppConfig>, runtime: RuntimeHandle) -> Self {
         let batch_size = config.execution.batch_size;
         let repartition_buffer_size = config.cluster.task_stream_buffer;
+        let resource_domain = (std::env::var("SAIL_EXPERIMENTAL_EXTENSIONS").as_deref() == Ok("1"))
+            .then(|| MemoryResourceDomain::new(&config.runtime.memory_pool));
         let runtime_env = RuntimeEnvFactory::new(config, runtime.clone());
         Self {
+            resource_domain,
             runtime_env,
             batch_size,
             repartition_buffer_size,
         }
     }
+    pub fn with_resource_domain(mut self, domain: Option<MemoryResourceDomain>) -> Self {
+        self.resource_domain = domain;
+        self
+    }
 }
 
 impl SessionFactory<()> for WorkerSessionFactory {
     fn create(&mut self, _info: ()) -> Result<SessionContext> {
-        let runtime = self.runtime_env.create(Ok)?;
+        if std::env::var("SAIL_EXPERIMENTAL_EXTENSIONS").as_deref() == Ok("1") {
+            crate::extensions::load_worker_extensions()?;
+        }
+        let runtime = self.runtime_env.create(self.resource_domain.as_ref(), Ok)?;
         // We still add default features for the worker session
         // since we need built-in functions to be available for the codec
         // when decoding the execution plan.
```

## 61. crates/sail-session/src/session_manager/actor/core.rs {#host-patch-61}

```diff
diff --git a/crates/sail-session/src/session_manager/actor/core.rs b/crates/sail-session/src/session_manager/actor/core.rs
index f3fb136cba15130426467877c34b273f99c7e264..85c12e1429dca1b2d3ce04ae025cdc75c3a207ef 100644
--- a/crates/sail-session/src/session_manager/actor/core.rs
+++ b/crates/sail-session/src/session_manager/actor/core.rs
@@ -3,12 +3,16 @@ use std::sync::Arc;
 use indexmap::IndexMap;
 use log::{info, warn};
 use sail_common::actor::{Actor, ActorAction, ActorContext, ActorHandle};
+use sail_common_datafusion::extension::SessionExtensionAccessor;
+use sail_common_datafusion::native_resource::NativeResourceTracker;
+use sail_common_datafusion::session::lifecycle::SessionLifecycle;
 use sail_execution::driver::{DriverHandle, DriverRegistryAccessor};
 use sail_execution::error::{ExecutionError, ExecutionResult};
 use sail_execution::{DriverId, IdGenerator};
 use sail_system_store::SystemEvent;
 
 use crate::session_manager::actor::SessionManagerActor;
+use crate::session_manager::session::ServerSessionState;
 use crate::session_manager::{
     SessionManagerComponents, SessionManagerMessage, SessionManagerOptions,
 };
@@ -53,6 +57,7 @@ impl Actor for SessionManagerActor {
             session_factory,
             job_runner_factory,
             sessions: IndexMap::new(),
+            cleanup: Default::default(),
             drivers: Default::default(),
             driver_gateway,
             driver_id_generator: IdGenerator::new(),
@@ -118,6 +123,26 @@ impl Actor for SessionManagerActor {
     }
 
     async fn stop(mut self, ctx: &mut ActorContext<Self>) {
+        let native_resources = self
+            .sessions
+            .values()
+            .filter_map(|session| {
+                let ServerSessionState::Running { context, .. } = &session.state else {
+                    return None;
+                };
+                context.extension::<NativeResourceTracker>().ok()
+            })
+            .collect::<Vec<_>>();
+        // A local job has no driver to stop its client-owned stream. Protocol
+        // operations must terminate before contexts are dropped or gRPC drains.
+        for (session_id, session) in &self.sessions {
+            if let ServerSessionState::Running { context, .. } = &session.state
+                && let Ok(lifecycle) = context.extension::<SessionLifecycle>()
+                && let Err(error) = lifecycle.stop().await
+            {
+                warn!("failed to stop session resources for {session_id}: {error}");
+            }
+        }
         // Keep the gateway available while drivers stop. Graceful gateway shutdown waits for
         // active task stream connections, which are owned by the drivers.
         let drivers = self.drivers.drain().collect::<Vec<_>>();
@@ -127,6 +152,17 @@ impl Actor for SessionManagerActor {
             }
         }
         ctx.children_mut().join().await;
+        self.sessions.clear();
+        // Stream cancellation signals detached native producers; their final
+        // buffers may be released afterwards. Do not let process exit race that
+        // release or silently reclaim their quota through OS teardown.
+        for resources in native_resources {
+            resources.wait_for_release().await;
+        }
+        // A Deleted session has already left self.sessions' live contexts, but
+        // its final native producer may still be releasing retained outputs.
+        // Unlike idle-probe timers, this work must finish before actor teardown.
+        self.cleanup.finish().await;
         if let Some(mut driver_gateway) = self.driver_gateway {
             driver_gateway.stop().await;
             info!("driver server has stopped");
```

## 62. crates/sail-session/src/session_manager/actor/handler.rs {#host-patch-62}

```diff
diff --git a/crates/sail-session/src/session_manager/actor/handler.rs b/crates/sail-session/src/session_manager/actor/handler.rs
index 2061e7c874a0a4814e102d02b23d03cf25b74f44..68c4b8dfcd4e512542a07a2fc84fd091b9f098c3 100644
--- a/crates/sail-session/src/session_manager/actor/handler.rs
+++ b/crates/sail-session/src/session_manager/actor/handler.rs
@@ -7,8 +7,10 @@ use sail_cache::remote_checkpoint::RemoteCheckpointRegistry;
 use sail_common::actor::{ActorAction, ActorContext};
 use sail_common::telemetry::SpanAttribute;
 use sail_common_datafusion::extension::SessionExtensionAccessor;
+use sail_common_datafusion::native_resource::NativeResourceTracker;
 use sail_common_datafusion::session::activity::ActivityTracker;
 use sail_common_datafusion::session::job::JobService;
+use sail_common_datafusion::session::lifecycle::SessionLifecycle;
 use sail_execution::DriverId;
 use sail_execution::driver::DriverHandle;
 use sail_execution::error::ExecutionResult;
@@ -20,6 +22,7 @@ use crate::error::{SessionError, SessionResult};
 use crate::session_factory::{ServerSessionInfo, SessionJobRunnerInfo};
 use crate::session_manager::SessionManagerMessage;
 use crate::session_manager::actor::SessionManagerActor;
+use crate::session_manager::cleanup::SessionCleanup;
 use crate::session_manager::session::{ServerSession, ServerSessionState};
 
 impl SessionManagerActor {
@@ -80,6 +83,7 @@ impl SessionManagerActor {
         let runner = match self.job_runner_factory.create(
             ctx.children_mut(),
             SessionJobRunnerInfo {
+                resource_domain: self.options.resource_domain.clone(),
                 session_id: session_id.clone(),
                 driver_id,
                 driver_server_port: self.driver_gateway.as_ref().map(|x| x.port()),
@@ -118,6 +122,7 @@ impl SessionManagerActor {
             return ActorAction::Continue;
         }
         let info = ServerSessionInfo {
+            resource_domain: self.options.resource_domain.clone(),
             session_id: session_id.clone(),
             user_id: user_id.clone(),
             session_manager: ctx.handle().clone(),
@@ -268,7 +273,7 @@ impl SessionManagerActor {
 
     pub(super) fn handle_probe_idle_session(
         &mut self,
-        ctx: &mut ActorContext<Self>,
+        _ctx: &mut ActorContext<Self>,
         session_id: String,
         instant: Instant,
     ) -> ActorAction {
@@ -279,7 +284,7 @@ impl SessionManagerActor {
             && tracker.active_at().is_ok_and(|x| x <= instant)
         {
             info!("removing idle session {session_id}");
-            Self::delete_session(ctx, session_id.clone(), context);
+            Self::delete_session(&mut self.cleanup, session_id.clone(), context);
             if let Some(driver_id) = *driver_id {
                 self.drivers.remove(driver_id);
             }
@@ -296,7 +301,7 @@ impl SessionManagerActor {
 
     pub(super) fn handle_delete_session(
         &mut self,
-        ctx: &mut ActorContext<Self>,
+        _ctx: &mut ActorContext<Self>,
         session_id: String,
         result: oneshot::Sender<SessionResult<()>>,
     ) -> ActorAction {
@@ -304,7 +309,7 @@ impl SessionManagerActor {
         let output = if let Some(session) = session {
             if let ServerSessionState::Running { context, driver_id } = &mut session.state {
                 info!("removing session {session_id}");
-                Self::delete_session(ctx, session_id.clone(), context);
+                Self::delete_session(&mut self.cleanup, session_id.clone(), context);
                 if let Some(driver_id) = *driver_id {
                     self.drivers.remove(driver_id);
                 }
@@ -370,16 +375,32 @@ impl SessionManagerActor {
         ActorAction::Continue
     }
 
-    fn delete_session(ctx: &mut ActorContext<Self>, session_id: String, context: &SessionContext) {
+    fn delete_session(cleanup: &mut SessionCleanup, session_id: String, context: &SessionContext) {
         let Ok(service) = context.extension::<JobService>() else {
             warn!("job service not found for session {session_id}");
             return;
         };
         let checkpoint_registry = context.extension::<RemoteCheckpointRegistry>().ok();
+        let lifecycle = context.extension::<SessionLifecycle>().ok();
+        let native_resources = context.extension::<NativeResourceTracker>().ok();
+        let graph_runs = context
+            .extension::<crate::extensions::graph_utils::GraphRuns>()
+            .ok();
         let runtime_env = context.runtime_env();
-        ctx.spawn(async move {
-            // Stop tasks before deleting the namespace so late attempts cannot recreate objects.
+        cleanup.spawn(async move {
+            if let Some(lifecycle) = lifecycle
+                && let Err(error) = lifecycle.stop().await
+            {
+                warn!("failed to stop session resources for {session_id}: {error}");
+            }
+            // Request executor/job shutdown before cleanup. Detached data-source
+            // writers are not all joined here, so storage cleanup is best effort.
             service.runner().stop().await;
+            if let Some(graph_runs) = graph_runs
+                && let Err(error) = graph_runs.cleanup().await
+            {
+                warn!("failed to clean graph runs for session {session_id}: {error}");
+            }
             if let Some(checkpoint_registry) = checkpoint_registry
                 && let Err(error) = checkpoint_registry
                     .cleanup_session(runtime_env.as_ref())
@@ -387,6 +408,9 @@ impl SessionManagerActor {
             {
                 warn!("failed to clean checkpoints for session {session_id}: {error}");
             }
+            if let Some(resources) = native_resources {
+                resources.wait_for_release().await;
+            }
         });
     }
 }
```

## 63. crates/sail-session/src/session_manager/actor/mod.rs {#host-patch-63}

```diff
diff --git a/crates/sail-session/src/session_manager/actor/mod.rs b/crates/sail-session/src/session_manager/actor/mod.rs
index 9061fc33ca14da714d6ce9e0497f69d04150488b..ec75defa80b6162a501a7533e241754d4fddac3c 100644
--- a/crates/sail-session/src/session_manager/actor/mod.rs
+++ b/crates/sail-session/src/session_manager/actor/mod.rs
@@ -11,6 +11,7 @@ use sail_execution::{DriverId, IdGenerator};
 use sail_telemetry::events::SystemEventReporter;
 
 use crate::session_factory::{ServerSessionInfo, SessionFactory, SessionJobRunnerFactory};
+use crate::session_manager::cleanup::SessionCleanup;
 use crate::session_manager::session::ServerSession;
 
 pub struct SessionManagerActor {
@@ -18,6 +19,7 @@ pub struct SessionManagerActor {
     session_factory: Box<dyn SessionFactory<ServerSessionInfo>>,
     job_runner_factory: Box<dyn SessionJobRunnerFactory>,
     sessions: IndexMap<String, ServerSession>,
+    cleanup: SessionCleanup,
     drivers: DriverRegistry,
     driver_gateway: Option<DriverGateway>,
     driver_id_generator: IdGenerator<DriverId>,
```

## 64. crates/sail-session/src/session_manager/actor/options.rs {#host-patch-64}

```diff
diff --git a/crates/sail-session/src/session_manager/actor/options.rs b/crates/sail-session/src/session_manager/actor/options.rs
index 5956d741b427a32820dba4c34b6a3ae148cd4e1e..44aa034ee76de1c67a487cfd40ab090de5980f72 100644
--- a/crates/sail-session/src/session_manager/actor/options.rs
+++ b/crates/sail-session/src/session_manager/actor/options.rs
@@ -4,10 +4,12 @@ use sail_common::runtime::RuntimeHandle;
 use sail_execution::driver::DriverGateway;
 use sail_telemetry::events::SystemEventReporter;
 
+use crate::runtime::MemoryResourceDomain;
 use crate::session_factory::{ServerSessionInfo, SessionFactory, SessionJobRunnerFactory};
 
 #[readonly::make]
 pub struct SessionManagerOptions {
+    pub resource_domain: Option<MemoryResourceDomain>,
     pub session_timeout: Duration,
     pub runtime: RuntimeHandle,
     /// The application configuration options as key-value pairs,
@@ -25,12 +27,18 @@ pub struct SessionManagerComponents {
 impl SessionManagerOptions {
     pub fn new(runtime: RuntimeHandle) -> Self {
         Self {
+            resource_domain: None,
             session_timeout: Duration::MAX,
             runtime,
             options: Vec::new(),
         }
     }
 
+    pub fn with_resource_domain(mut self, domain: MemoryResourceDomain) -> Self {
+        self.resource_domain = Some(domain);
+        self
+    }
+
     pub fn with_session_timeout(mut self, timeout: Duration) -> Self {
         self.session_timeout = timeout;
         self
```

## 65. crates/sail-session/src/session_manager/cleanup.rs {#host-patch-65}

```diff
diff --git a/crates/sail-session/src/session_manager/cleanup.rs b/crates/sail-session/src/session_manager/cleanup.rs
new file mode 100644
index 0000000000000000000000000000000000000000..1aba8815d832cd5cd1f7ef77f64834622a1df0e5
--- /dev/null
+++ b/crates/sail-session/src/session_manager/cleanup.rs
@@ -0,0 +1,85 @@
+use std::future::Future;
+
+use log::warn;
+use tokio::task::JoinSet;
+
+/// Session deletion is acknowledged before its asynchronous cleanup completes.
+/// Keep those tasks separate from abortable actor timers, and drain them before
+/// graceful shutdown releases the actor and its already-deleted sessions.
+#[derive(Default)]
+pub(super) struct SessionCleanup {
+    tasks: JoinSet<()>,
+}
+
+impl SessionCleanup {
+    pub(super) fn spawn(&mut self, task: impl Future<Output = ()> + Send + 'static) {
+        while let Some(result) = self.tasks.try_join_next() {
+            Self::report(result);
+        }
+        self.tasks.spawn(task);
+    }
+
+    pub(super) async fn finish(&mut self) {
+        while let Some(result) = self.tasks.join_next().await {
+            Self::report(result);
+        }
+    }
+
+    fn report(result: Result<(), tokio::task::JoinError>) {
+        if let Err(error) = result {
+            warn!("session cleanup task failed: {error}");
+        }
+    }
+}
+
+#[cfg(test)]
+mod tests {
+    use std::sync::Arc;
+    use std::sync::atomic::{AtomicBool, Ordering};
+
+    use datafusion::execution::memory_pool::{GreedyMemoryPool, MemoryPool};
+    use sail_common_datafusion::native_resource::NativeResourceTracker;
+    use tokio::sync::oneshot;
+
+    use super::*;
+
+    #[tokio::test]
+    async fn immediate_shutdown_waits_for_held_cleanup_and_final_native_release()
+    -> Result<(), Box<dyn std::error::Error>> {
+        let pool: Arc<dyn MemoryPool> = Arc::new(GreedyMemoryPool::new(64));
+        let tracker = Arc::new(NativeResourceTracker::default());
+        let output = tracker.reserve(&pool, "deleted-session-output", 64)?;
+        let completed = Arc::new(AtomicBool::new(false));
+        let (entered, entered_rx) = oneshot::channel();
+        let (released, released_rx) = oneshot::channel();
+        let producer = std::thread::spawn(move || -> Result<(), oneshot::error::RecvError> {
+            // Hold the last output independently of the Tokio scheduler. Its
+            // admission cannot disappear because an actor dropped its tasks.
+            released_rx.blocking_recv()?;
+            drop(output);
+            Ok(())
+        });
+        let mut cleanup = SessionCleanup::default();
+        let ended = completed.clone();
+        cleanup.spawn(async move {
+            assert!(entered.send(()).is_ok());
+            tracker.wait_for_release().await;
+            ended.store(true, Ordering::SeqCst);
+        });
+        entered_rx.await?;
+        let mut shutdown = Box::pin(cleanup.finish());
+        assert!(futures::poll!(shutdown.as_mut()).is_pending());
+        assert_eq!(pool.reserved(), 64);
+        assert!(!completed.load(Ordering::SeqCst));
+        released
+            .send(())
+            .map_err(|_| "native producer exited before release")?;
+        shutdown.await;
+        producer
+            .join()
+            .map_err(|_| "native producer thread panicked")??;
+        assert!(completed.load(Ordering::SeqCst));
+        assert_eq!(pool.reserved(), 0);
+        Ok(())
+    }
+}
```

## 66. crates/sail-session/src/session_manager/mod.rs {#host-patch-66}

```diff
diff --git a/crates/sail-session/src/session_manager/mod.rs b/crates/sail-session/src/session_manager/mod.rs
index 0cca1eee1a30ec0aae28fd112fc0f634055a1390..b6ce85481ed07878d131f65252ec10b40015bb45 100644
--- a/crates/sail-session/src/session_manager/mod.rs
+++ b/crates/sail-session/src/session_manager/mod.rs
@@ -1,4 +1,5 @@
 mod actor;
+mod cleanup;
 mod session;
 
 use std::fmt;
@@ -114,6 +115,13 @@ pub async fn create_session_manager(
                 .raw()
                 .map_err(|e| SessionError::internal(e.to_string()))?,
         );
+    let options = if std::env::var("SAIL_EXPERIMENTAL_EXTENSIONS").as_deref() == Ok("1") {
+        options.with_resource_domain(crate::runtime::MemoryResourceDomain::new(
+            &config.runtime.memory_pool,
+        ))
+    } else {
+        options
+    };
     let components = SessionManagerComponents {
         session_factory,
         job_runner_factory,
```

## 67. crates/sail-spark-connect/Cargo.toml {#host-patch-67}

```diff
diff --git a/crates/sail-spark-connect/Cargo.toml b/crates/sail-spark-connect/Cargo.toml
index 2b288f5ea39fbb38338379a6a1e055088a6eb5cc..0b79022cbb0a11582dfbaf3477728dcb600703f5 100644
--- a/crates/sail-spark-connect/Cargo.toml
+++ b/crates/sail-spark-connect/Cargo.toml
@@ -7,6 +7,7 @@ edition = { workspace = true }
 workspace = true
 
 [dependencies]
+stacker = { workspace = true }
 sail-cache = { path = "../sail-cache" }
 sail-common = { path = "../sail-common" }
 sail-common-datafusion = { path = "../sail-common-datafusion" }
```

## 68. crates/sail-spark-connect/proto/sail/extension/v1/extension.proto {#host-patch-68}

```diff
diff --git a/crates/sail-spark-connect/proto/sail/extension/v1/extension.proto b/crates/sail-spark-connect/proto/sail/extension/v1/extension.proto
new file mode 100644
index 0000000000000000000000000000000000000000..86db5179a4a70c68fa80483e5abbb1f309ec8e0c
--- /dev/null
+++ b/crates/sail-spark-connect/proto/sail/extension/v1/extension.proto
@@ -0,0 +1,20 @@
+// Experimental local-mode protocol. This schema is a wire contract, not a native ABI.
+syntax = "proto3";
+package sail.extension.v1;
+
+import "spark/connect/base.proto";
+import "spark/connect/expressions.proto";
+
+// Pack into Relation.extension with type URL:
+// type.googleapis.com/sail.extension.v1.SailExtensionRequest
+message SailExtensionRequest {
+  string payload_type_url = 1;
+  bytes payload = 2;
+  // Only Plan.root is accepted. Names are restored to the input DataFrame's
+  // user-facing names before the native handler receives a physical plan.
+  repeated spark.connect.Plan inputs = 3;
+  // Reserved by the proposal; this PoC rejects any occurrence of this field.
+  repeated spark.connect.Expression input_expressions = 4;
+  // Required value: 1. An omitted proto3 value (0) is rejected.
+  uint32 envelope_version = 5;
+}
```

## 69. crates/sail-spark-connect/src/entrypoint.rs {#host-patch-69}

```diff
diff --git a/crates/sail-spark-connect/src/entrypoint.rs b/crates/sail-spark-connect/src/entrypoint.rs
index b95cb4dfce456921f362fa51260e9f3f342cff04..4d8fa4187ed492c9805c2593f1f3f22e460a5068 100644
--- a/crates/sail-spark-connect/src/entrypoint.rs
+++ b/crates/sail-spark-connect/src/entrypoint.rs
@@ -50,6 +50,7 @@ where
     let session_manager =
         create_spark_session_manager_with_factory(config, runtime, &mut system, session_factory_fn)
             .await?;
+    let mut shutdown_result = None;
     let result = {
         let server = SparkConnectServer::new(session_manager.clone());
         let service = SparkConnectServiceServer::new(server)
@@ -63,11 +64,20 @@ where
         ServerBuilder::new("sail_spark_connect", Default::default())
             .add_service(service, Some(crate::spark::connect::FILE_DESCRIPTOR_SET))
             .await
-            .serve(listener, signal)
+            .serve(listener, async {
+                signal.await;
+                // Tonic's graceful drain waits for active responses. Stop their
+                // session-owned producers first so unbounded work cannot keep
+                // the server and native reservations alive during shutdown.
+                shutdown_result = Some(session_manager.shutdown().await);
+            })
             .await
             .map_err(|e| std::io::Error::other(e.to_string()))
     };
-    session_manager.shutdown().await?;
+    match shutdown_result {
+        Some(result) => result?,
+        None => session_manager.shutdown().await?,
+    }
     system.join().await;
     result.map_err(Into::into)
 }
```

## 70. crates/sail-spark-connect/src/error.rs {#host-patch-70}

```diff
diff --git a/crates/sail-spark-connect/src/error.rs b/crates/sail-spark-connect/src/error.rs
index acfe4e8737530758f1f9d27f9b9bb922cf9bd498..955776f93976032484a4e5bc8cc343e86b5ed29b 100644
--- a/crates/sail-spark-connect/src/error.rs
+++ b/crates/sail-spark-connect/src/error.rs
@@ -49,6 +49,8 @@ pub enum SparkError {
     AnalysisError(String),
     #[error("parse error: {0}")]
     ParseError(String),
+    #[error("operation interrupted: {0}")]
+    OperationInterrupted(String),
 }
 
 impl SparkError {
@@ -460,6 +462,9 @@ impl From<SparkError> for Status {
             }
             SparkError::AnalysisError(s) => SparkThrowable::AnalysisException(s).into(),
             SparkError::ParseError(s) => SparkThrowable::ParseException(s).into(),
+            e @ SparkError::OperationInterrupted(_) => {
+                SparkThrowable::QueryExecutionException(e.to_string()).into()
+            }
             e @ SparkError::SendError(_) => {
                 Status::cancelled(truncate_grpc_message(&e.to_string()))
             }
```

## 71. crates/sail-spark-connect/src/executor.rs {#host-patch-71}

```diff
diff --git a/crates/sail-spark-connect/src/executor.rs b/crates/sail-spark-connect/src/executor.rs
index 0ebc2ad21b6394f862abaaeeb76b9d74d235c1e3..82fb2debf15da7c8027252d623cd75bc0c19e0bb 100644
--- a/crates/sail-spark-connect/src/executor.rs
+++ b/crates/sail-spark-connect/src/executor.rs
@@ -122,6 +122,9 @@ enum ExecutorState {
         span: Span,
     },
     Pausing,
+    // Retain only the terminal identity so a reattaching client receives the
+    // interruption, without retaining the plan, native buffers, or task context.
+    Interrupted,
     Failed(SparkError),
 }
 
@@ -401,6 +404,12 @@ impl Executor {
                 *state = x;
                 return Err(SparkError::internal("task is being paused"));
             }
+            ExecutorState::Interrupted => {
+                *state = ExecutorState::Interrupted;
+                return Err(SparkError::OperationInterrupted(
+                    self.metadata.operation_id.clone(),
+                ));
+            }
         };
         let (tx, rx) = mpsc::channel(1);
         let (notifier, listener) = oneshot::channel();
@@ -445,16 +454,42 @@ impl Executor {
             ExecutorTaskResult::Completed => ExecutorState::Idle,
             ExecutorTaskResult::Failed(e) => ExecutorState::Failed(e),
         };
-        *(self.state.lock()?) = state;
+        let mut current = self.state.lock()?;
+        // An interrupt may have terminalized the operation while the paused
+        // task was being joined. Never restore that task's context afterwards.
+        if matches!(*current, ExecutorState::Pausing) {
+            *current = state;
+        }
         Ok(())
     }
 
+    pub(crate) async fn interrupt(&self) -> SparkResult<bool> {
+        let previous = {
+            let mut state = self.state.lock()?;
+            mem::replace(state.deref_mut(), ExecutorState::Interrupted)
+        };
+        match previous {
+            ExecutorState::Interrupted => Ok(false),
+            ExecutorState::Running { task, .. } => {
+                let _ = task.notifier.send(());
+                // Drop the returned task context before acknowledging. Native
+                // blocking producers observe their stream cancellation next.
+                drop(task.handle.await?);
+                Ok(true)
+            }
+            _ => Ok(true),
+        }
+    }
+
     pub(crate) fn release(&self, response_id: String) -> SparkResult<()> {
         let state = self.state.lock()?;
         let buffer = match state.deref() {
             ExecutorState::Running { task, span: _ } => &task.buffer,
             ExecutorState::Pending { context, span: _ } => &context.buffer,
-            ExecutorState::Idle | ExecutorState::Failed(_) | ExecutorState::Pausing => {
+            ExecutorState::Idle
+            | ExecutorState::Failed(_)
+            | ExecutorState::Pausing
+            | ExecutorState::Interrupted => {
                 return Ok(());
             }
         };
@@ -463,6 +498,9 @@ impl Executor {
     }
 }
 
+#[cfg(test)]
+mod tests;
+
 pub(crate) fn to_arrow_batch(batch: &RecordBatch) -> SparkResult<ArrowBatch> {
     let mut output = ArrowBatch::default();
     {
```

## 72. crates/sail-spark-connect/src/executor/tests.rs {#host-patch-72}

```diff
diff --git a/crates/sail-spark-connect/src/executor/tests.rs b/crates/sail-spark-connect/src/executor/tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..fe8c666df2b81e3267bb9563cb3041832c81b2f9
--- /dev/null
+++ b/crates/sail-spark-connect/src/executor/tests.rs
@@ -0,0 +1,126 @@
+use std::sync::atomic::{AtomicUsize, Ordering};
+use std::task::{Context, Poll};
+
+use datafusion::arrow::datatypes::Schema;
+use datafusion::execution::RecordBatchStream;
+use sail_common_datafusion::session::lifecycle::SessionResource;
+
+use super::*;
+use crate::session::{SparkSession, SparkSessionOptions};
+
+struct PendingStream(Arc<AtomicUsize>);
+
+impl Stream for PendingStream {
+    type Item = datafusion::common::Result<RecordBatch>;
+
+    fn poll_next(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<Option<Self::Item>> {
+        Poll::Pending
+    }
+}
+
+impl RecordBatchStream for PendingStream {
+    fn schema(&self) -> SchemaRef {
+        Arc::new(Schema::empty())
+    }
+}
+
+impl Drop for PendingStream {
+    fn drop(&mut self) {
+        self.0.fetch_add(1, Ordering::SeqCst);
+    }
+}
+
+fn executor() -> (Executor, Arc<AtomicUsize>) {
+    let dropped = Arc::new(AtomicUsize::new(0));
+    let executor = Executor::new(
+        ExecutorMetadata {
+            operation_id: "interrupted-operation".into(),
+            tags: vec![],
+            reattachable: true,
+        },
+        Box::pin(PendingStream(Arc::clone(&dropped))),
+        Duration::from_secs(3600),
+        ExecutorMode::Query,
+    );
+    (executor, dropped)
+}
+
+fn assert_terminal(executor: &Executor, dropped: &AtomicUsize) {
+    assert_eq!(dropped.load(Ordering::SeqCst), 1);
+    // Repeated reattach cannot consume the error and accidentally restart work.
+    for _ in 0..2 {
+        assert!(matches!(
+            executor.start(),
+            Err(SparkError::OperationInterrupted(id)) if id == "interrupted-operation"
+        ));
+    }
+}
+
+#[tokio::test]
+async fn interrupt_drops_pending_and_running_contexts_but_preserves_terminal_identity()
+-> SparkResult<()> {
+    for started in [false, true] {
+        let (executor, dropped) = executor();
+        let mut output = if started {
+            Some(executor.start()?)
+        } else {
+            None
+        };
+        if let Some(output) = &mut output {
+            assert!(matches!(
+                output.next().await,
+                Some(Ok(ExecutorOutput {
+                    batch: ExecutorBatch::Schema(_),
+                    ..
+                }))
+            ));
+        }
+        assert!(executor.interrupt().await?);
+        assert!(!executor.interrupt().await?);
+        assert_terminal(&executor, &dropped);
+    }
+    Ok(())
+}
+
+#[tokio::test]
+async fn concurrent_pause_cannot_restore_an_interrupted_context() -> SparkResult<()> {
+    let (executor, dropped) = executor();
+    let mut output = executor.start()?;
+    assert!(output.next().await.is_some());
+    let mut pause = Box::pin(executor.pause_if_running());
+    // This current-thread runtime cannot join the executor task until yielding.
+    // Hold the exact Pausing state without a sleep or a clock race.
+    assert!(futures::poll!(pause.as_mut()).is_pending());
+    assert!(executor.interrupt().await?);
+    pause.await?;
+    assert_terminal(&executor, &dropped);
+    Ok(())
+}
+
+#[tokio::test]
+async fn session_stop_drops_owned_plans_and_rejects_in_flight_planning_completion()
+-> SparkResult<()> {
+    pyo3::Python::initialize();
+    let session = SparkSession::try_new(
+        "teardown-session".into(),
+        "test".into(),
+        SparkSessionOptions {
+            execution_heartbeat_interval: Duration::from_secs(3600),
+        },
+    )?;
+    let (pending, dropped) = executor();
+    session.add_executor(pending)?;
+    session.stop().await?;
+    assert_eq!(dropped.load(Ordering::SeqCst), 1);
+    assert!(session.get_executor("interrupted-operation")?.is_none());
+    // A request may have begun planning before teardown. Its completed plan
+    // must be dropped instead of resurrecting operations in the deleted session.
+    let (late, dropped) = executor();
+    assert!(matches!(
+        session.add_executor(late),
+        Err(SparkError::OperationInterrupted(_))
+    ));
+    assert_eq!(dropped.load(Ordering::SeqCst), 1);
+    session.stop().await?;
+    Ok(())
+}
```

## 73. crates/sail-spark-connect/src/proto/extension.rs {#host-patch-73}

```diff
diff --git a/crates/sail-spark-connect/src/proto/extension.rs b/crates/sail-spark-connect/src/proto/extension.rs
new file mode 100644
index 0000000000000000000000000000000000000000..99ac3123341ceca22f7f951e929dd77059e9e1bc
--- /dev/null
+++ b/crates/sail-spark-connect/src/proto/extension.rs
@@ -0,0 +1,173 @@
+//! Wire decoding for the experimental local Sail relation extension envelope.
+
+use std::cell::Cell;
+
+use pbjson_types::Any;
+use prost::Message;
+use sail_common::spec;
+
+use crate::error::{SparkError, SparkResult};
+use crate::spark::connect::Plan;
+
+mod wire;
+
+pub(crate) const ENVELOPE_TYPE_URL: &str =
+    "type.googleapis.com/sail.extension.v1.SailExtensionRequest";
+const MAX_ENVELOPE_BYTES: usize = 8 * 1024 * 1024;
+const MAX_PAYLOAD_BYTES: usize = 1024 * 1024;
+const MAX_INPUTS: usize = 16;
+const MAX_INPUT_DEPTH: usize = 64;
+const MAX_TYPE_URL_BYTES: usize = 512;
+const CONVERSION_STACK_BYTES: usize = 2 * 1024 * 1024;
+
+pub(crate) fn with_conversion_stack<T>(f: impl FnOnce() -> T) -> T {
+    // RelationNode conversion has a large enum-dispatch frame. Grow before
+    // entering it, including for an accepted nested extension on a small stack.
+    stacker::maybe_grow(64 * 1024, CONVERSION_STACK_BYTES, f)
+}
+
+// Embedded protobuf messages and bytes share their length-delimited wire format.
+// Keeping input Plans as bytes lets us validate arity and unsupported expression
+// fields before recursively decoding any input. The canonical .proto is checked
+// in under proto/sail/extension/v1/extension.proto.
+#[derive(Clone, PartialEq, Message)]
+struct SailExtensionRequest {
+    #[prost(string, tag = "1")]
+    payload_type_url: String,
+    #[prost(bytes = "vec", tag = "2")]
+    payload: Vec<u8>,
+    #[prost(bytes = "vec", repeated, tag = "3")]
+    inputs: Vec<Vec<u8>>,
+    #[prost(bytes = "vec", repeated, tag = "4")]
+    input_expressions: Vec<Vec<u8>>,
+    #[prost(uint32, tag = "5")]
+    envelope_version: u32,
+}
+
+thread_local! {
+    // Conversion is synchronous. This budget remains live while converting
+    // nested Any payloads, whose byte fields otherwise reset prost's recursion
+    // budget on every separate decode. Ordinary non-extension plans are unchanged.
+    static EXTENSION_INPUT_DEPTH: Cell<usize> = const { Cell::new(0) };
+}
+
+pub(crate) struct RelationConversionGuard {
+    active: bool,
+}
+
+impl RelationConversionGuard {
+    pub(crate) fn enter() -> SparkResult<Self> {
+        Self::enter_scope(false)
+    }
+
+    fn enter_scope(extension: bool) -> SparkResult<Self> {
+        EXTENSION_INPUT_DEPTH.with(|depth| {
+            let current = depth.get();
+            let active = extension || current != 0;
+            if active {
+                if current >= MAX_INPUT_DEPTH {
+                    return Err(SparkError::invalid(format!(
+                        "Sail extension input nesting exceeds {MAX_INPUT_DEPTH} levels"
+                    )));
+                }
+                depth.set(current + 1);
+            }
+            Ok(Self { active })
+        })
+    }
+}
+
+impl Drop for RelationConversionGuard {
+    fn drop(&mut self) {
+        if self.active {
+            EXTENSION_INPUT_DEPTH.with(|depth| depth.set(depth.get() - 1));
+        }
+    }
+}
+
+fn validate_type_url(type_url: &str) -> SparkResult<()> {
+    if type_url.is_empty() || type_url.len() > MAX_TYPE_URL_BYTES {
+        return Err(SparkError::invalid(format!(
+            "extension type URL must contain between 1 and {MAX_TYPE_URL_BYTES} bytes"
+        )));
+    }
+    Ok(())
+}
+
+/// Inspect tags without allocating input vectors or decoding nested messages.
+fn preflight_envelope(mut bytes: &[u8]) -> SparkResult<()> {
+    let mut input_count = 0;
+    while !bytes.is_empty() {
+        let (tag, _, _) = wire::next_field(&mut bytes)?;
+        if tag == 3 {
+            input_count += 1;
+            if input_count > MAX_INPUTS {
+                return Err(SparkError::invalid(format!(
+                    "Sail extension accepts at most {MAX_INPUTS} input plans"
+                )));
+            }
+        }
+        if tag == 4 {
+            return Err(SparkError::unsupported("Sail extension input expressions"));
+        }
+    }
+    Ok(())
+}
+
+pub(crate) fn convert_relation_extension(extension: Any) -> SparkResult<spec::QueryNode> {
+    validate_type_url(&extension.type_url)?;
+    if extension.type_url != ENVELOPE_TYPE_URL {
+        if extension.value.len() > MAX_PAYLOAD_BYTES {
+            return Err(SparkError::invalid(
+                "Connect extension payload exceeds 1 MiB",
+            ));
+        }
+        return Ok(spec::QueryNode::Extension {
+            payload_type_url: extension.type_url,
+            payload: extension.value.to_vec(),
+            inputs: vec![],
+            is_envelope: false,
+        });
+    }
+    if extension.value.len() > MAX_ENVELOPE_BYTES {
+        return Err(SparkError::invalid("Sail extension envelope exceeds 8 MiB"));
+    }
+    preflight_envelope(&extension.value)?;
+    let envelope = SailExtensionRequest::decode(extension.value.as_ref())?;
+    if envelope.envelope_version != 1 {
+        return Err(SparkError::invalid(format!(
+            "unsupported Sail extension envelope version {}; expected 1",
+            envelope.envelope_version
+        )));
+    }
+    validate_type_url(&envelope.payload_type_url)?;
+    if envelope.payload.len() > MAX_PAYLOAD_BYTES {
+        return Err(SparkError::invalid(
+            "Connect extension payload exceeds 1 MiB",
+        ));
+    }
+    let _depth = RelationConversionGuard::enter_scope(true)?;
+    let inputs = envelope
+        .inputs
+        .into_iter()
+        .map(|input| {
+            let remaining = EXTENSION_INPUT_DEPTH.with(|depth| MAX_INPUT_DEPTH - depth.get());
+            wire::validate_plan(&input, remaining)?;
+            // The generated decoder has no recursive call-site hook. Its raw
+            // message depth is already bounded above, so give this bounded
+            // decode a known stack even when called from a small initial one.
+            stacker::grow(CONVERSION_STACK_BYTES, || {
+                Plan::decode(input.as_slice())?.try_into()
+            })
+        })
+        .collect::<SparkResult<Vec<spec::QueryPlan>>>()?;
+    Ok(spec::QueryNode::Extension {
+        payload_type_url: envelope.payload_type_url,
+        payload: envelope.payload,
+        inputs,
+        is_envelope: true,
+    })
+}
+
+#[cfg(test)]
+mod tests;
```

## 74. crates/sail-spark-connect/src/proto/extension/tests.rs {#host-patch-74}

```diff
diff --git a/crates/sail-spark-connect/src/proto/extension/tests.rs b/crates/sail-spark-connect/src/proto/extension/tests.rs
new file mode 100644
index 0000000000000000000000000000000000000000..5b3286838001803d55a26e0db589e2dce2480eca
--- /dev/null
+++ b/crates/sail-spark-connect/src/proto/extension/tests.rs
@@ -0,0 +1,230 @@
+use super::*;
+use crate::spark::connect::{Command, Range, Relation, RelationCommon, plan, relation};
+
+fn request(inputs: Vec<Vec<u8>>) -> SailExtensionRequest {
+    SailExtensionRequest {
+        payload_type_url: "type.test/Nutmeg".into(),
+        payload: b"payload".to_vec(),
+        inputs,
+        input_expressions: vec![],
+        envelope_version: 1,
+    }
+}
+
+fn pack(request: SailExtensionRequest) -> Any {
+    Any {
+        type_url: ENVELOPE_TYPE_URL.into(),
+        value: request.encode_to_vec().into(),
+    }
+}
+
+fn range_plan() -> Plan {
+    Plan {
+        op_type: Some(plan::OpType::Root(Relation {
+            common: Some(RelationCommon {
+                plan_id: Some(91),
+                ..Default::default()
+            }),
+            rel_type: Some(relation::RelType::Range(Range {
+                start: Some(0),
+                end: 5,
+                step: 1,
+                num_partitions: Some(4),
+            })),
+        })),
+    }
+}
+
+#[test]
+fn envelope_retains_input_plans_payload_and_plan_ids() -> SparkResult<()> {
+    let node = convert_relation_extension(pack(request(vec![range_plan().encode_to_vec()])))?;
+    match node {
+        spec::QueryNode::Extension {
+            payload_type_url,
+            payload,
+            inputs,
+            is_envelope,
+        } => {
+            assert_eq!(payload_type_url, "type.test/Nutmeg");
+            assert_eq!(payload, b"payload");
+            assert!(is_envelope);
+            assert_eq!(inputs.len(), 1);
+            assert_eq!(inputs[0].plan_id, Some(91));
+            assert!(
+                matches!(&inputs[0].node, spec::QueryNode::Range(range) if range.num_partitions == Some(4))
+            );
+        }
+        other => return Err(SparkError::internal(format!("unexpected node {other:?}"))),
+    }
+    Ok(())
+}
+
+#[test]
+fn bare_any_keeps_its_type_url_and_has_no_inputs() -> SparkResult<()> {
+    let node = convert_relation_extension(Any {
+        type_url: "type.test/Read".into(),
+        value: vec![1, 2, 3].into(),
+    })?;
+    assert!(
+        matches!(node, spec::QueryNode::Extension { payload_type_url, inputs, is_envelope: false, .. }
+        if payload_type_url == "type.test/Read" && inputs.is_empty())
+    );
+    Ok(())
+}
+
+#[test]
+fn rejects_version_expressions_nonquery_inputs_and_malformed_payloads() {
+    let mut version = request(vec![]);
+    version.envelope_version = 0;
+    assert!(
+        matches!(convert_relation_extension(pack(version)), Err(e) if e.to_string().contains("expected 1"))
+    );
+    let mut expressions = request(vec![vec![255]]);
+    expressions.input_expressions.push(vec![255]);
+    assert!(
+        matches!(convert_relation_extension(pack(expressions)), Err(e) if e.to_string().contains("input expressions"))
+    );
+    let command = Plan {
+        op_type: Some(plan::OpType::Command(Command::default())),
+    };
+    assert!(
+        matches!(convert_relation_extension(pack(request(vec![command.encode_to_vec()]))), Err(e) if e.to_string().contains("relation expected"))
+    );
+    assert!(convert_relation_extension(pack(request(vec![vec![255]]))).is_err());
+}
+
+#[test]
+fn limits_input_count_before_decoding_any_child() {
+    // Each child is invalid protobuf; the count error must be returned first.
+    let envelope = request(vec![vec![255]; MAX_INPUTS + 1]);
+    assert!(
+        matches!(convert_relation_extension(pack(envelope)), Err(e) if e.to_string().contains("at most 16"))
+    );
+}
+
+#[test]
+fn limits_payload_and_envelope_bytes() {
+    let bare = Any {
+        type_url: "type.test/Read".into(),
+        value: vec![0; MAX_PAYLOAD_BYTES + 1].into(),
+    };
+    assert!(
+        matches!(convert_relation_extension(bare), Err(e) if e.to_string().contains("exceeds 1 MiB"))
+    );
+    let envelope = Any {
+        type_url: ENVELOPE_TYPE_URL.into(),
+        value: vec![0; MAX_ENVELOPE_BYTES + 1].into(),
+    };
+    assert!(
+        matches!(convert_relation_extension(envelope), Err(e) if e.to_string().contains("exceeds 8 MiB"))
+    );
+}
+
+#[test]
+fn nested_any_does_not_reset_recursion_budget_and_failure_releases_guard() -> SparkResult<()> {
+    let mut input = range_plan();
+    for _ in 0..1000 {
+        input = Plan {
+            op_type: Some(plan::OpType::Root(Relation {
+                common: None,
+                rel_type: Some(relation::RelType::Extension(pack(request(vec![
+                    input.encode_to_vec(),
+                ])))),
+            })),
+        };
+    }
+    let result = spec::QueryPlan::try_from(input);
+    assert!(matches!(result, Err(e) if e.to_string().contains("nesting exceeds")));
+    convert_relation_extension(pack(request(vec![range_plan().encode_to_vec()])))?;
+    Ok(())
+}
+
+#[test]
+fn accepts_near_limit_nested_envelopes_on_small_initial_stack() -> SparkResult<()> {
+    let mut input = range_plan();
+    // Each nested envelope traverses four protobuf message edges. Fifteen
+    // layers plus the final Plan/Relation/Range stay just below the 64 limit.
+    for _ in 0..15 {
+        input = Plan {
+            op_type: Some(plan::OpType::Root(Relation {
+                common: None,
+                rel_type: Some(relation::RelType::Extension(pack(request(vec![
+                    input.encode_to_vec(),
+                ])))),
+            })),
+        };
+    }
+    let envelope = pack(request(vec![input.encode_to_vec()]));
+    let thread = std::thread::Builder::new()
+        .stack_size(128 * 1024)
+        .spawn(move || convert_relation_extension(envelope).is_ok())?;
+    assert!(
+        thread
+            .join()
+            .map_err(|_| SparkError::internal("accepted input conversion thread panicked"))?
+    );
+    Ok(())
+}
+
+fn length_delimited(tag: u32, payload: &[u8]) -> Vec<u8> {
+    use prost::encoding::{WireType, encode_key, encode_varint};
+    let mut output = vec![];
+    encode_key(tag, WireType::LengthDelimited, &mut output);
+    encode_varint(payload.len() as u64, &mut output);
+    output.extend_from_slice(payload);
+    output
+}
+
+#[test]
+fn rejects_thousand_nested_projects_before_prost_decode_on_small_stack() -> SparkResult<()> {
+    // Construct wire bytes iteratively: Relation.project = 3, Project.input = 1.
+    // Never construct a recursive Rust message whose own Drop could overflow.
+    let mut relation = vec![];
+    for _ in 0..1000 {
+        relation = length_delimited(3, &length_delimited(1, &relation));
+    }
+    let plan = length_delimited(1, &relation);
+    let envelope = pack(request(vec![plan]));
+    let thread = std::thread::Builder::new()
+        .stack_size(128 * 1024)
+        .spawn(move || {
+            matches!(convert_relation_extension(envelope), Err(e) if e.to_string().contains("nesting exceeds"))
+        })?;
+    assert!(
+        thread
+            .join()
+            .map_err(|_| SparkError::internal("input validation thread panicked"))?
+    );
+    Ok(())
+}
+
+#[test]
+fn rejects_unknown_group_fields_without_recursive_skip() {
+    let groups = vec![0x0b; 1000]; // Field 1, start-group wire type.
+    let envelope = Any {
+        type_url: ENVELOPE_TYPE_URL.into(),
+        value: groups.clone().into(),
+    };
+    assert!(
+        matches!(convert_relation_extension(envelope), Err(e) if e.to_string().contains("groups are not supported"))
+    );
+    assert!(
+        matches!(wire::validate_plan(&groups, MAX_INPUT_DEPTH), Err(e) if e.to_string().contains("groups are not supported"))
+    );
+}
+
+#[test]
+fn preflight_treats_arrow_data_as_opaque_bytes() -> SparkResult<()> {
+    use crate::spark::connect::LocalRelation;
+    let input = Plan {
+        op_type: Some(plan::OpType::Root(Relation {
+            common: None,
+            rel_type: Some(relation::RelType::LocalRelation(LocalRelation {
+                data: Some(vec![0x0b; 1000]),
+                schema: None,
+            })),
+        })),
+    };
+    wire::validate_plan(&input.encode_to_vec(), MAX_INPUT_DEPTH)?;
+    Ok(())
+}
```

## 75. crates/sail-spark-connect/src/proto/extension/wire.rs {#host-patch-75}

```diff
diff --git a/crates/sail-spark-connect/src/proto/extension/wire.rs b/crates/sail-spark-connect/src/proto/extension/wire.rs
new file mode 100644
index 0000000000000000000000000000000000000000..7d3685497ce2ff0cf33b6d28126ff96f3b3c241b
--- /dev/null
+++ b/crates/sail-spark-connect/src/proto/extension/wire.rs
@@ -0,0 +1,150 @@
+//! Bounded raw protobuf traversal before prost decodes embedded input plans.
+//!
+//! The workspace enables prost's `no-recursion-limit`, so its generated decoder
+//! cannot protect this boundary. Visit only descriptor-declared message fields;
+//! arbitrary strings, Arrow IPC and extension-specific payloads remain opaque.
+//! Sail envelopes inside Any.value are traversed before any recursive decoding.
+
+use std::collections::BTreeMap;
+use std::sync::LazyLock;
+
+use prost::Message;
+use prost::encoding::{WireType, decode_key, decode_varint};
+use prost_types::field_descriptor_proto::Type;
+use prost_types::{DescriptorProto, FileDescriptorSet};
+
+use crate::error::{SparkError, SparkResult};
+use crate::spark::connect::FILE_DESCRIPTOR_SET;
+
+const ENVELOPE_MESSAGE: &str = ".sail.extension.v1.SailExtensionRequest";
+
+type MessageFields = BTreeMap<String, BTreeMap<u32, String>>;
+
+static MESSAGE_FIELDS: LazyLock<Result<MessageFields, String>> = LazyLock::new(|| {
+    // This is build-generated, trusted data, never a descriptor from a request.
+    let descriptors = FileDescriptorSet::decode(FILE_DESCRIPTOR_SET).map_err(|e| e.to_string())?;
+    let mut messages = BTreeMap::new();
+    for file in descriptors.file {
+        let prefix = format!(".{}", file.package.as_deref().unwrap_or_default());
+        for message in file.message_type {
+            register_message(&mut messages, &prefix, message)?;
+        }
+    }
+    messages.insert(
+        ENVELOPE_MESSAGE.into(),
+        BTreeMap::from([(3, ".spark.connect.Plan".into())]),
+    );
+    Ok(messages)
+});
+
+fn register_message(
+    messages: &mut MessageFields,
+    prefix: &str,
+    message: DescriptorProto,
+) -> Result<(), String> {
+    let name = message.name.ok_or("protobuf descriptor without a name")?;
+    let name = format!("{prefix}.{name}");
+    let mut fields = BTreeMap::new();
+    for field in message.field {
+        if field.r#type == Some(Type::Message as i32) {
+            let number = field.number.ok_or("protobuf field without a number")?;
+            let number = u32::try_from(number).map_err(|e| e.to_string())?;
+            let target = field
+                .type_name
+                .ok_or("protobuf message field without a type")?;
+            fields.insert(number, target);
+        }
+    }
+    messages.insert(name.clone(), fields);
+    for nested in message.nested_type {
+        register_message(messages, &name, nested)?;
+    }
+    Ok(())
+}
+
+/// Read one field without recursion or allocation. Groups are not part of the
+/// proto3 extension contract and are rejected even when their tag is unknown.
+pub(super) fn next_field<'a>(bytes: &mut &'a [u8]) -> SparkResult<(u32, WireType, &'a [u8])> {
+    let (tag, wire_type) = decode_key(bytes)?;
+    let length = match wire_type {
+        WireType::Varint => {
+            decode_varint(bytes)?;
+            0
+        }
+        WireType::ThirtyTwoBit => 4,
+        WireType::SixtyFourBit => 8,
+        WireType::LengthDelimited => usize::try_from(decode_varint(bytes)?)
+            .map_err(|_| SparkError::invalid("extension protobuf field length overflow"))?,
+        WireType::StartGroup | WireType::EndGroup => {
+            return Err(SparkError::invalid(
+                "protobuf groups are not supported in extension input plans",
+            ));
+        }
+    };
+    if length > bytes.len() {
+        return Err(SparkError::invalid("truncated extension protobuf field"));
+    }
+    let (value, rest) = bytes.split_at(length);
+    *bytes = rest;
+    Ok((tag, wire_type, value))
+}
+
+pub(super) fn validate_plan(bytes: &[u8], max_depth: usize) -> SparkResult<()> {
+    let messages = MESSAGE_FIELDS
+        .as_ref()
+        .map_err(|e| SparkError::internal(format!("invalid Spark protocol descriptor: {e}")))?;
+    // Depth-first iteration retains at most one unfinished message per level,
+    // rather than allocating an entry for every repeated field in the request.
+    let mut stack = vec![(".spark.connect.Plan", bytes, 0usize)];
+    while let Some((message, mut remaining, depth)) = stack.pop() {
+        if depth >= max_depth {
+            return Err(SparkError::invalid(format!(
+                "Sail extension input nesting exceeds the remaining {max_depth} protobuf levels"
+            )));
+        }
+        if message == ".google.protobuf.Any" {
+            let mut type_url = &[][..];
+            let mut value = &[][..];
+            while !remaining.is_empty() {
+                let (tag, wire_type, field) = next_field(&mut remaining)?;
+                if matches!(tag, 1 | 2) && wire_type != WireType::LengthDelimited {
+                    return Err(SparkError::invalid(
+                        "invalid wire type for extension Any field",
+                    ));
+                }
+                match tag {
+                    1 => type_url = field,
+                    2 => value = field,
+                    _ => {}
+                }
+            }
+            if type_url == super::ENVELOPE_TYPE_URL.as_bytes() {
+                if value.len() > super::MAX_ENVELOPE_BYTES {
+                    return Err(SparkError::invalid("Sail extension envelope exceeds 8 MiB"));
+                }
+                super::preflight_envelope(value)?;
+                stack.push((ENVELOPE_MESSAGE, value, depth + 1));
+            }
+            continue;
+        }
+        let fields = messages.get(message).ok_or_else(|| {
+            SparkError::internal(format!("missing Spark protocol descriptor for {message}"))
+        })?;
+        while !remaining.is_empty() {
+            let (tag, wire_type, value) = next_field(&mut remaining)?;
+            if let Some(child) = fields.get(&tag) {
+                if wire_type != WireType::LengthDelimited {
+                    return Err(SparkError::invalid(format!(
+                        "invalid protobuf wire type for message field {message}:{tag}"
+                    )));
+                }
+                if !remaining.is_empty() {
+                    stack.push((message, remaining, depth));
+                }
+                stack.push((child.as_str(), value, depth + 1));
+                break;
+            }
+        }
+    }
+    Ok(())
+}
```

## 76. crates/sail-spark-connect/src/proto/mod.rs {#host-patch-76}

```diff
diff --git a/crates/sail-spark-connect/src/proto/mod.rs b/crates/sail-spark-connect/src/proto/mod.rs
index 1dc12e61045d0fb638b08ceddc9c9c05b1e57e65..2d5e6371388750f86218d641c2bd546505e4c5ab 100644
--- a/crates/sail-spark-connect/src/proto/mod.rs
+++ b/crates/sail-spark-connect/src/proto/mod.rs
@@ -4,6 +4,7 @@ pub(crate) mod data_type;
 pub(crate) mod data_type_arrow;
 pub(crate) mod data_type_json;
 pub(crate) mod expression;
+pub(crate) mod extension;
 pub(crate) mod function;
 pub(crate) mod literal;
 pub(crate) mod plan;
```

## 77. crates/sail-spark-connect/src/proto/plan.rs {#host-patch-77}

```diff
diff --git a/crates/sail-spark-connect/src/proto/plan.rs b/crates/sail-spark-connect/src/proto/plan.rs
index f7d41776c81541130ea0d47ed6063282fdd9e79d..fe8dadf5f43b17216d689774d4569c56372098b6 100644
--- a/crates/sail-spark-connect/src/proto/plan.rs
+++ b/crates/sail-spark-connect/src/proto/plan.rs
@@ -102,9 +102,10 @@ impl TryFrom<Relation> for spec::Plan {
 
     /// Converts a relation to a plan, somehow SQL text is parsed here.
     fn try_from(relation: Relation) -> SparkResult<spec::Plan> {
+        let _depth = super::extension::RelationConversionGuard::enter()?;
         let Relation { common, rel_type } = relation;
         let rel_type = rel_type.required("relation type")?;
-        let node: RelationNode = rel_type.try_into()?;
+        let node: RelationNode = super::extension::with_conversion_stack(|| rel_type.try_into())?;
         let metadata: RelationMetadata = common.into();
         match node {
             RelationNode::Query(query) => Ok(spec::Plan::Query(spec::QueryPlan {
@@ -123,9 +124,10 @@ impl TryFrom<Relation> for spec::QueryPlan {
     type Error = SparkError;
 
     fn try_from(relation: Relation) -> SparkResult<spec::QueryPlan> {
+        let _depth = super::extension::RelationConversionGuard::enter()?;
         let Relation { common, rel_type } = relation;
         let rel_type = rel_type.required("relation type")?;
-        let node: RelationNode = rel_type.try_into()?;
+        let node: RelationNode = super::extension::with_conversion_stack(|| rel_type.try_into())?;
         let metadata: RelationMetadata = common.into();
         Ok(spec::QueryPlan {
             node: node.try_into_query()?,
@@ -138,9 +140,10 @@ impl TryFrom<Relation> for spec::CommandPlan {
     type Error = SparkError;
 
     fn try_from(relation: Relation) -> SparkResult<spec::CommandPlan> {
+        let _depth = super::extension::RelationConversionGuard::enter()?;
         let Relation { common, rel_type } = relation;
         let rel_type = rel_type.required("relation type")?;
-        let node: RelationNode = rel_type.try_into()?;
+        let node: RelationNode = super::extension::with_conversion_stack(|| rel_type.try_into())?;
         let metadata: RelationMetadata = common.into();
         Ok(spec::CommandPlan {
             node: node.try_into_command()?,
@@ -1336,7 +1339,9 @@ impl TryFrom<RelType> for RelationNode {
             RelType::RelationChanges(_) => Err(SparkError::unsupported("relation changes")),
             RelType::NearestByJoin(_) => Err(SparkError::unsupported("nearest-by join")),
             RelType::MlRelation(_) => Err(SparkError::unsupported("ML relation")),
-            RelType::Extension(_) => Err(SparkError::unsupported("extension relation")),
+            RelType::Extension(extension) => Ok(RelationNode::Query(
+                super::extension::convert_relation_extension(extension)?,
+            )),
             RelType::Unknown(_) => Err(SparkError::unsupported("unknown relation")),
         }
     }
```

## 78. crates/sail-spark-connect/src/server.rs {#host-patch-78}

```diff
diff --git a/crates/sail-spark-connect/src/server.rs b/crates/sail-spark-connect/src/server.rs
index 3032f8d1bf5f6077cf4beb06ef63bf66d3cdbea2..9455ed6e7bbce1fc355891459759c41097a72bf5 100644
--- a/crates/sail-spark-connect/src/server.rs
+++ b/crates/sail-spark-connect/src/server.rs
@@ -125,7 +125,12 @@ impl SparkConnectService for SparkConnectServer {
         request: Request<ExecutePlanRequest>,
     ) -> Result<Response<Self::ExecutePlanStream>, Status> {
         let request = request.into_inner();
-        debug!("{request:?}");
+        // Extension payloads can carry session-owned capabilities. Log routing
+        // identifiers, never opaque plan bytes or client argument values.
+        debug!(
+            "ExecutePlan session_id={} operation_id={:?}",
+            request.session_id, request.operation_id
+        );
         let session_id = request.session_id;
         let user_id = request.user_context.map(|u| u.user_id).unwrap_or_default();
         let metadata = ExecutorMetadata {
@@ -166,7 +171,7 @@ impl SparkConnectService for SparkConnectServer {
         use crate::spark::connect::analyze_plan_response;
 
         let request = request.into_inner();
-        debug!("{request:?}");
+        debug!("AnalyzePlan session_id={}", request.session_id);
         let session_id = request.session_id.clone();
         let user_id = request.user_context.map(|u| u.user_id).unwrap_or_default();
         let ctx = self
```

## 79. crates/sail-spark-connect/src/service/plan_analyzer.rs {#host-patch-79}

```diff
diff --git a/crates/sail-spark-connect/src/service/plan_analyzer.rs b/crates/sail-spark-connect/src/service/plan_analyzer.rs
index a15ac9c01405e131e11407e412ba5651fcf951bb..5a25fd0232b86031aa4c21e031b01ac5e47e5415 100644
--- a/crates/sail-spark-connect/src/service/plan_analyzer.rs
+++ b/crates/sail-spark-connect/src/service/plan_analyzer.rs
@@ -251,6 +251,7 @@ fn is_streaming_query_plan(plan: &spec::QueryPlan) -> bool {
 fn is_streaming_query_node(node: &spec::QueryNode) -> bool {
     match node {
         spec::QueryNode::Read { is_streaming, .. } => *is_streaming,
+        spec::QueryNode::Extension { inputs, .. } => inputs.iter().any(is_streaming_query_plan),
         // leaf nodes with no query plan inputs
         spec::QueryNode::LocalRelation { .. }
         | spec::QueryNode::CachedLocalRelation { .. }
```

## 80. crates/sail-spark-connect/src/service/plan_executor.rs {#host-patch-80}

```diff
diff --git a/crates/sail-spark-connect/src/service/plan_executor.rs b/crates/sail-spark-connect/src/service/plan_executor.rs
index 1c42e4eb2c46eaf2376003ff034ca0385c1657b2..d0e8d103079b01e8f32fe23721d5ca5391900559 100644
--- a/crates/sail-spark-connect/src/service/plan_executor.rs
+++ b/crates/sail-spark-connect/src/service/plan_executor.rs
@@ -566,9 +566,10 @@ pub(crate) async fn handle_execute_remove_cached_remote_relation_command(
 pub(crate) async fn handle_interrupt_all(ctx: &SessionContext) -> SparkResult<Vec<String>> {
     let spark = ctx.extension::<SparkSession>()?;
     let mut results = vec![];
-    for executor in spark.remove_all_executors()? {
-        executor.pause_if_running().await?;
-        results.push(executor.metadata.operation_id.clone());
+    for executor in spark.all_executors()? {
+        if executor.interrupt().await? {
+            results.push(executor.metadata.operation_id.clone());
+        }
     }
     Ok(results)
 }
@@ -579,9 +580,10 @@ pub(crate) async fn handle_interrupt_tag(
 ) -> SparkResult<Vec<String>> {
     let spark = ctx.extension::<SparkSession>()?;
     let mut results = vec![];
-    for executor in spark.remove_executors_by_tag(tag.as_str())? {
-        executor.pause_if_running().await?;
-        results.push(executor.metadata.operation_id.clone());
+    for executor in spark.executors_by_tag(tag.as_str())? {
+        if executor.interrupt().await? {
+            results.push(executor.metadata.operation_id.clone());
+        }
     }
     Ok(results)
 }
@@ -591,10 +593,13 @@ pub(crate) async fn handle_interrupt_operation_id(
     operation_id: String,
 ) -> SparkResult<Vec<String>> {
     let spark = ctx.extension::<SparkSession>()?;
-    match spark.remove_executor(operation_id.as_str())? {
+    match spark.get_executor(operation_id.as_str())? {
         Some(executor) => {
-            executor.pause_if_running().await?;
-            Ok(vec![executor.metadata.operation_id.clone()])
+            if executor.interrupt().await? {
+                Ok(vec![executor.metadata.operation_id.clone()])
+            } else {
+                Ok(vec![])
+            }
         }
         None => Ok(vec![]),
     }
```

## 81. crates/sail-spark-connect/src/session.rs {#host-patch-81}

```diff
diff --git a/crates/sail-spark-connect/src/session.rs b/crates/sail-spark-connect/src/session.rs
index 277060435d503c3b72bd9534d694dc57f0545948..c2e98ff3d8133874e04bc57e5d0a1fd6f06a07a4 100644
--- a/crates/sail-spark-connect/src/session.rs
+++ b/crates/sail-spark-connect/src/session.rs
@@ -7,6 +7,7 @@ use datafusion::execution::SendableRecordBatchStream;
 use datafusion::logical_expr::StringifiedPlan;
 use sail_common::utils::datetime::get_system_timezone;
 use sail_common_datafusion::extension::SessionExtension;
+use sail_common_datafusion::session::lifecycle::SessionResource;
 use sail_plan::config::PlanConfig;
 
 use crate::config::{ConfigKeyValue, SparkRuntimeConfig};
@@ -49,6 +50,34 @@ impl SessionExtension for SparkSession {
     }
 }
 
+#[tonic::async_trait]
+impl SessionResource for SparkSession {
+    async fn stop(&self) -> datafusion::common::Result<()> {
+        let executors = {
+            let mut state = self.state.lock().map_err(|error| {
+                datafusion::common::DataFusionError::Execution(error.to_string())
+            })?;
+            state.stopped = true;
+            // Dropping streaming query signals also cancels their producers.
+            state.streaming_queries = StreamingQueryManager::new();
+            state
+                .executors
+                .drain()
+                .map(|(_, executor)| executor)
+                .collect::<Vec<_>>()
+        };
+        let mut failure = None;
+        for executor in executors {
+            if let Err(error) = executor.interrupt().await {
+                failure = Some(datafusion::common::DataFusionError::Execution(
+                    error.to_string(),
+                ));
+            }
+        }
+        failure.map_or(Ok(()), Err)
+    }
+}
+
 impl SparkSession {
     pub(crate) fn try_new(
         session_id: String,
@@ -172,6 +201,9 @@ impl SparkSession {
     pub(crate) fn add_executor(&self, executor: Executor) -> SparkResult<()> {
         let mut state = self.state.lock()?;
         let id = executor.metadata.operation_id.clone();
+        if state.stopped {
+            return Err(SparkError::OperationInterrupted(id));
+        }
         state.executors.insert(id, Arc::new(executor));
         Ok(())
     }
@@ -189,31 +221,19 @@ impl SparkSession {
             .map(|(_, executor)| executor))
     }
 
-    pub(crate) fn remove_all_executors(&self) -> SparkResult<Vec<Arc<Executor>>> {
-        let mut state = self.state.lock()?;
-        let mut out = Vec::new();
-        for (_, executor) in state.executors.drain() {
-            out.push(executor);
-        }
-        Ok(out)
+    pub(crate) fn all_executors(&self) -> SparkResult<Vec<Arc<Executor>>> {
+        let state = self.state.lock()?;
+        Ok(state.executors.values().cloned().collect())
     }
 
-    pub(crate) fn remove_executors_by_tag(&self, tag: &str) -> SparkResult<Vec<Arc<Executor>>> {
-        let mut state = self.state.lock()?;
-        let tag = tag.to_string();
-        let mut ids = Vec::new();
-        let mut removed = Vec::new();
-        for (key, executor) in &state.executors {
-            if executor.metadata.tags.contains(&tag) {
-                ids.push(key.clone());
-            }
-        }
-        for key in ids.iter() {
-            if let Some(executor) = state.executors.remove(key) {
-                removed.push(executor);
-            }
-        }
-        Ok(removed)
+    pub(crate) fn executors_by_tag(&self, tag: &str) -> SparkResult<Vec<Arc<Executor>>> {
+        let state = self.state.lock()?;
+        Ok(state
+            .executors
+            .values()
+            .filter(|executor| executor.metadata.tags.iter().any(|value| value == tag))
+            .cloned()
+            .collect())
     }
 
     pub(crate) fn start_streaming_query(
@@ -234,6 +254,9 @@ impl SparkSession {
             run_id: uuid::Uuid::new_v4().to_string(),
         };
         let mut state = self.state.lock()?;
+        if state.stopped {
+            return Err(SparkError::OperationInterrupted(self.session_id.clone()));
+        }
         let query = StreamingQuery::new(name, info, stream);
         state.streaming_queries.add_query(id.clone(), query);
         Ok(id)
@@ -306,6 +329,7 @@ impl SparkSession {
 }
 
 struct SparkSessionState {
+    stopped: bool,
     config: SparkRuntimeConfig,
     executors: HashMap<String, Arc<Executor>>,
     streaming_queries: StreamingQueryManager,
@@ -314,6 +338,7 @@ struct SparkSessionState {
 impl SparkSessionState {
     fn try_new() -> SparkResult<Self> {
         Ok(Self {
+            stopped: false,
             config: SparkRuntimeConfig::try_new()?,
             executors: HashMap::new(),
             streaming_queries: StreamingQueryManager::new(),
```

## 82. crates/sail-spark-connect/src/session_manager.rs {#host-patch-82}

```diff
diff --git a/crates/sail-spark-connect/src/session_manager.rs b/crates/sail-spark-connect/src/session_manager.rs
index caece1c2892800e86b86c1c65d3e1b846a8a4a4b..818ee7f5115e1bac30ce573dc6a24d40cc01af95 100644
--- a/crates/sail-spark-connect/src/session_manager.rs
+++ b/crates/sail-spark-connect/src/session_manager.rs
@@ -9,6 +9,7 @@ use sail_common::actor::ActorSystem;
 use sail_common::config::AppConfig;
 use sail_common::runtime::RuntimeHandle;
 use sail_common_datafusion::catalog::display::DefaultCatalogDisplay;
+use sail_common_datafusion::session::lifecycle::SessionLifecycle;
 use sail_common_datafusion::session::plan::PlanService;
 use sail_plan::catalog::SparkCatalogObjectDisplay;
 use sail_plan::formatter::SparkPlanFormatter;
@@ -48,19 +49,22 @@ impl ServerSessionMutator for SparkSessionMutator {
             Box::new(DefaultCatalogDisplay::<SparkCatalogObjectDisplay>::default()),
             Box::new(SparkPlanFormatter),
         );
-        let spark = SparkSession::try_new(
-            info.session_id.clone(),
-            info.user_id.clone(),
-            SparkSessionOptions {
-                execution_heartbeat_interval: Duration::from_secs(
-                    self.config.spark.execution_heartbeat_interval_secs,
-                ),
-            },
-        )
-        .map_err(|e| internal_datafusion_err!("{e}"))?;
+        let spark = Arc::new(
+            SparkSession::try_new(
+                info.session_id.clone(),
+                info.user_id.clone(),
+                SparkSessionOptions {
+                    execution_heartbeat_interval: Duration::from_secs(
+                        self.config.spark.execution_heartbeat_interval_secs,
+                    ),
+                },
+            )
+            .map_err(|e| internal_datafusion_err!("{e}"))?,
+        );
         Ok(config
             .with_extension(Arc::new(plan_service))
-            .with_extension(Arc::new(spark)))
+            .with_extension(Arc::new(SessionLifecycle::new(spark.clone())))
+            .with_extension(spark))
     }
 
     fn mutate_state(
```

