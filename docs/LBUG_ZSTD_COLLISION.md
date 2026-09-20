# Restoring the whole-workspace build when lbug stops bundling zstd

Status: **waiting on an upstream release.** Recorded 2026-09-20.

`cargo test --workspace --all-features` cannot link `grust-ladybug`'s test
binary: LadybugDB's prebuilt static library bundles zstd, an all-features build
unifies features so that `zstd-sys` arrives through LanceDB and Arrow IPC
compression, and `rust-lld` rejects about twenty duplicate `ZSTD_*` symbols.
Built alone the crate never pulls `zstd-sys`, so it links and its tests run.

`.github/workflows/workspace.yml` therefore excludes the crate from the
workspace step and tests it in its own step. The comment there explains the
mechanism; this file exists for the part a comment should not carry — when and
how to undo it.

## What it cost while nobody noticed

The workspace job failed on every push from at least 2026-09-14 until the split
landed. The failure is at link time, so **no test in any crate ran during that
window**: a release, several book rebuilds and a series of executor and
resource-accounting changes all merged with no CI signal. A build that is always
red stops being read, which is the argument for fixing the signal even when the
underlying collision cannot be fixed yet.

## The trap

A `LBUG_LOCALIZE_BUNDLED_SYMBOLS=1` switch is described in the 2026-09-14 entry
of `codex-to-codex.md` as making the whole-workspace build link. That was
measured against a git pin of ladybug-rust PR #33, which **is in no published
release**. The newest crates.io version as of 2026-09-20 is `lbug 0.20.4`, whose
build script honours `LBUG_PRECOMPILED_*`, `LBUG_VERSION`,
`LBUG_GITHUB_REPOSITORY`, `LBUG_LINUX_VARIANT`, `LBUG_LIB_KIND`,
`LBUG_BUILD_FROM_SOURCE`, `LBUG_RUST_BUILD_FROM_SOURCE`, `LBUG_BUNDLED`,
`LBUG_INCLUDE_DIR`, `LBUG_LIBRARY_DIR`, `LBUG_PRECOMPILED_SOURCE` and
`LBUG_SHARED` — and nothing that controls symbol visibility.

Setting that variable against 0.20.4 changes nothing and the link still fails.
Confirm any such switch exists in the published crate before relying on it.

## Undoing the split

When a release can localise or omit the bundled zstd symbols:

1. Bump `lbug`, and confirm the capability is in the published crate rather than
   in a branch.
2. Enable whatever the release provides, in the workflow `env:` block if it is
   an environment switch or in the dependency if it is a feature.
3. Restore the workspace step to `cargo test --locked --workspace --all-features`
   and delete the separate Ladybug step and its comment.
4. Verify with a local `cargo test --workspace --all-features` first. The failure
   mode is a link error, so a green single-crate run proves nothing.
5. Delete this file.
