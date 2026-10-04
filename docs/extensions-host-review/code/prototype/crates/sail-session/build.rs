fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto = "proto";
    println!("cargo:rerun-if-changed={proto}/gf/utils/v1/utils.proto");
    prost_build::compile_protos(&[format!("{proto}/gf/utils/v1/utils.proto")], &[proto])?;
    Ok(())
}
