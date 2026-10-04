# Physical-output executor permission follow-up

Prepared only. This copies the reviewed v2 executor into a new source directory
and changes execution identity and new-directory permissions. It does not modify
v2, the failed execution, the physical verifier, producer outputs, the benchmark
runner or any configuration. Root owns staging and any later execution.

The retained [attempt01 outer receipt](../logging03-physical-execution/attempt01-evidence/outer-receipt.json)
shows an exited checker with code 2, no OOM, no physical report, and removal after
state capture. Its [stderr](../logging03-physical-execution/attempt01-evidence/11-logs.stderr)
could not open `/work/container_check.py` (`Errno 13`). The separate
[permission control](../logging03-physical-execution/permission-control.json)
records a host UID/GID of 501:20, a host-owned 0700 bundle, and an empty image
Config.User. Default container root with all capabilities dropped lacks DAC
override; these observations support the permission explanation. They do not
establish that the actual result files can be read by the new identity.

The request now pins host UID/GID 501:20 and `--user=501:20`. The supervisor
checks the created container's Config.User, and the reader checks its actual
UID/GID and records mounted ownership and mode. New bundles are explicitly 0755
and their files 0644, independently of umask. A newly created evidence directory
is 0700 and must be owned by UID 501. No evidence directory is world-writable.
Staging must preserve these modes; an incorrectly staged bundle is rejected
before Docker. The helper never repairs modes on an existing bundle or output.

All content hashes, boot/runtime/native pins, read-only input mounts, capability
removal, network prohibition, 1 CPU/2 GiB/zero-swap/PID64 limits, disk admission,
exited-state/OOM checks and state-before-removal behavior remain. A new request,
container name and evidence directory are required. The host launcher must use
`/usr/local/bin/python3`; the prior `/usr/bin/python3` 3.9 failure remains in the
execution evidence. The container still uses the original pinned reader venv.

The [frozen local control receipt](controls01-receipt.json) records 26 passing
controls: the prior negative lifecycle/integrity controls, wrong created user,
real local filesystem modes under umask 077, refusal to reuse/chmod old evidence,
and mocked in-container identity/mounted-mode checks. No Docker, second UID,
remote workload or result scan ran in these controls. The actual later checker
is still needed to verify Colima bind ownership mapping and result readability.
