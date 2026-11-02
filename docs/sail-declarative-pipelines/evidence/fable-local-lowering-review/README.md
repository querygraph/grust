# Local streaming range binding and declared-identity snapshot review

Independent candidates append only the same three fixtures to the offered
lower_tests.rs; all original implementation/tests are unchanged. The test bodies
are identical across the following immutable source bases:

| Base | Review candidate | Observed result |
| --- | --- | --- |
| 9dc1b1157 |15e39b1256623b99df8901668ee40d3561d51956 | exit101,0 passed/3 failed: graph placeholder/materialised relation takes precedence over local stream ranges; changed local versions have identical JSON snapshots |
| a19f2ba2f |84ceae417c2be29d5abbe7beaae8089cf88b3132 | exit101,2 passed/1 failed: both range cases close, nonempty identity map fails JSON serialization because Name is a sequence key |
| afb593d28 |4723302f95bdd0ae1203e82e8837054eaa072d00 | exit0,3 passed/0 failed: recorded rows [0,1,2,10,11] win over both graph relations; changed declared local version changes serialized snapshot |

The final candidate also passes all44 pure streaming component/regression tests
in the exact detached tree. Fable later imported the same fixtures as768e21123
and reports its own gate (CF-0164/0166). These results qualify the component's
range dispatch and declared snapshot representation, not actual provider range
authenticity/backend pinning/C0 durability, target effects, Iggy or cluster joins.
Static/local identities use typed ordered sequences; qualified name parts are
kept separate. The root gate was restored toddd83d815 after all terminal reviews.

CF-0167 authorizes a separate four-unit integration-preparation bundle based on
rootddd, preserving offered history. No component is integrated by this packet.
The bundle keeps execution guards/dry run and requires independent parent gates,
minimal GraphScope constructor/module declarations and a declared sha2 consumer
edge only with the lowerer. Mixed modes and multi-leaf local-view provenance are
tracked gaps, not permanent selected restrictions. See integration-scope.md.

SHA256.json covers packet files except itself. Original failures, warnings, exact
commands/logs/sources and later successes are retained separately. Review objects
are anchored under refs/sdp/reviews; replay into fresh outputs.
