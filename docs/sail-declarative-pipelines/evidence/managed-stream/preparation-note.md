# Working-copy preparation failure

Before managed_stream_tests.rs existed, `cargo +nightly fmt -p
sail-common-datafusion` returned exit1 because it could not resolve the declared
test module. The compiler-style diagnostic named the missing test file and the
module declaration in managed_stream.rs. This was a working-copy formatting
attempt, not a detached candidate compilation/test. After the helper agent created
the test module, formatting and the first captured candidate gates passed. The
original tool output remains in the conversation; no raw on-disk log existed.
