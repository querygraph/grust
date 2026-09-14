use std::{path::PathBuf, process::Command};
fn git(args: &[&str]) -> String {
    let result = Command::new("git")
        .args(args)
        .output()
        .expect("git must run for profiling provenance");
    assert!(result.status.success(), "git provenance command failed");
    String::from_utf8(result.stdout)
        .expect("git output is UTF-8")
        .trim()
        .to_owned()
}
fn main() {
    let root = PathBuf::from(git(&["rev-parse", "--show-toplevel"]));
    let common = PathBuf::from(git(&[
        "rev-parse",
        "--path-format=absolute",
        "--git-common-dir",
    ]));
    let git_dir = PathBuf::from(git(&["rev-parse", "--absolute-git-dir"]));
    for path in [
        root.join("Cargo.toml"),
        root.join("Cargo.lock"),
        root.join("crates"),
        root.join("benchmarks/arrow-pipelines/src"),
        PathBuf::from("Cargo.lock"),
        PathBuf::from("build.rs"),
        git_dir.join("HEAD"),
        git_dir.join("index"),
        common.join("refs"),
        common.join("packed-refs"),
    ] {
        println!("cargo:rerun-if-changed={}", path.display());
    }
    let commit = git(&["rev-parse", "HEAD"]);
    let suffix = if git(&["status", "--porcelain"]).is_empty() {
        ""
    } else {
        "-dirty"
    };
    println!("cargo:rustc-env=GRUST_PROFILE_SOURCE={commit}{suffix}");
}
