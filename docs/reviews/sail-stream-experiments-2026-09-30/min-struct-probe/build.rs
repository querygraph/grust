use std::{env, fs, path::PathBuf};

fn main() {
    let source = env::var("DF_MINMAX_STRUCT_SOURCE").expect("set exact pinned min_max_struct.rs path");
    println!("cargo:rerun-if-env-changed=DF_MINMAX_STRUCT_SOURCE");
    println!("cargo:rerun-if-changed={source}");
    let output = PathBuf::from(env::var("OUT_DIR").unwrap()).join("min_max_struct.rs");
    fs::copy(source, output).unwrap();
}
