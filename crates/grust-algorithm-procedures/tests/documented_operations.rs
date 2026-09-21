//! Every registered kernel appears in the book's operation table.
//!
//! The table and `docs/goals/graph-analytics-catalog.md` were reconciled by hand
//! once and immediately drifted: `articleRank` was registered and absent from the
//! table for a day, which a reader of the book could only discover by not finding
//! it. The registry is the authority — a kernel exists because it is registered —
//! so this compares the registry against the table rather than one document
//! against another.

use std::path::PathBuf;

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

/// Row keys of every `| \`name\` | ... |` line in the chapter's tables.
fn documented_operations(chapter: &str) -> Vec<String> {
    chapter
        .lines()
        .filter_map(|line| line.strip_prefix("| `"))
        .filter_map(|rest| rest.split('`').next())
        .map(str::to_string)
        .collect()
}

#[test]
fn every_registered_kernel_is_in_the_book_s_operation_table() {
    let path = repository_root()
        .join("docs")
        .join("book")
        .join("chapters")
        .join("generalized-algorithms.md");
    let chapter = std::fs::read_to_string(&path)
        .unwrap_or_else(|error| panic!("read {}: {error}", path.display()));
    let documented = documented_operations(&chapter);
    assert!(
        documented.len() > 20,
        "only {} operations parsed from {} — the table's shape has changed and this \
         test is no longer reading it",
        documented.len(),
        path.display()
    );

    let missing: Vec<&str> = grust_algorithm_procedures::projection_kernel_names()
        .into_iter()
        .filter(|name| !documented.iter().any(|row| row == name))
        .collect();
    assert!(
        missing.is_empty(),
        "registered kernels absent from the book's operation table: {missing:?}"
    );
}
