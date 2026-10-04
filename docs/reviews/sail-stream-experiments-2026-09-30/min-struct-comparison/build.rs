use std::{env, fs, path::PathBuf};
fn main() {
    let output = PathBuf::from(env::var("OUT_DIR").unwrap());
    for (key, name) in [("DF_MINMAX_STRUCT_SOURCE", "original.rs"),
                        ("SAIL_COMPACT_STRUCT_SOURCE", "candidate.rs")] {
        let source = env::var(key).unwrap_or_else(|_| panic!("set {key}"));
        println!("cargo:rerun-if-env-changed={key}");
        println!("cargo:rerun-if-changed={source}");
        fs::copy(source, output.join(name)).unwrap();
    }
    fs::write(output.join("modules.rs"), format!(
        "#[allow(dead_code)]\n#[path = {:?}] mod original;\n#[path = {:?}] mod candidate;\n",
        output.join("original.rs"), output.join("candidate.rs"))).unwrap();
}
