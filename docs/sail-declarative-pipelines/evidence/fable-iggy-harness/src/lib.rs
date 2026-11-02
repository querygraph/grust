//! Observation recording for the Fable Iggy harness. Every scenario appends a
//! JSON object to `observations/<scenario>.json`; the README is written from
//! those files, never by hand.

use std::path::PathBuf;

use serde::Serialize;

pub fn observations_dir() -> PathBuf {
    let dir = std::env::var("FABLE_IGGY_OBSERVATIONS")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("observations"));
    std::fs::create_dir_all(&dir).expect("observations directory");
    dir
}

pub fn record<T: Serialize>(scenario: &str, value: &T) {
    let path = observations_dir().join(format!("{scenario}.json"));
    let json = serde_json::to_string_pretty(value).expect("serialisable observation");
    std::fs::write(&path, json + "\n").expect("write observation");
    eprintln!("recorded {}", path.display());
}

/// The server binary the harness launches: built from the pinned worktree.
pub fn server_binary() -> String {
    std::env::var("FABLE_IGGY_SERVER")
        .unwrap_or_else(|_| "/Users/alexy/src/iggy-fable-pin-target/release/iggy-server".to_string())
}
