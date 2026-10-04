# Morrobay disk cleanup

Recorded UTC: 2026-10-01T05:48:21.960620+00:00

The user authorized cleanup before the next WCC run. Only inventoried,
non-executable Cargo `.rlib`, `.rmeta`, `.o` and `.d` intermediates were
removed from selected `debug/deps` and `release/deps` trees. Five completed,
exited build containers were then removed without their mounted volumes.
Their metadata, filesystem-change lists and compressed stdout/stderr logs were
archived on the host before removal. No global Docker prune was used.

| Boundary | Before | After |
|---|---:|---:|
| Linux benchmark filesystem free space | 34.57 GiB | 91.02 GiB |
| macOS host free space around its cache prune | 64.33 GiB | 78.21 GiB |

The guest gained **56.46 GiB**. The host's observed increase was
**13.89 GiB**. These are different filesystem boundaries;
they must not be added as physical host space reclaimed. Shared extents can make
summed cache-file allocation differ from host free-space change; extent sharing
was not measured here.
Concurrent host activity can also affect free-space observations.

Removed file counts were 20,229 on macOS and 29,629 in the guest.
Metadata checks confirmed 1,199 non-selected files and top-level artifacts were
unchanged. The compact runtime, native library, scale-24/25 dataset manifests
and WCC helper hashes were checked before and after guest cleanup and matched.
Datasets, results, source, runtime images, wheels, virtual environments,
executables and shared libraries were retained. Removed Cargo intermediates
will need rebuilding if those historical targets are used again.

The first container-removal attempt stopped before removing anything because
Docker emitted the same filesystem-change entries in a different order. The
[control](docker-diff-order-control.json) established exact equality after sorting;
the next attempt compared those same status/path lines in stable order and
removed all five containers. Both attempts are retained.

[Summary and hashes](summary.json), [host removal](host-prune01.json),
[guest removal](volume-prune01.json),
[container removal](completed-build-container-removal02.json),
[final observation](final-observation01.json).
The complete large pre-removal inventory is losslessly compressed in
`completed-build-container-inventory01.json.gz`.

The proposed `/Volumes/Apo` storage with 6 TB free has not been mounted or used
by this cleanup. Verify its actual mount, VM access and I/O profile before
admitting new large runs there.
