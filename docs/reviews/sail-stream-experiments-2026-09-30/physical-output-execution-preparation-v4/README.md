# Physical-output executor identity follow-up

Prepared only. This new version preserves v2, v3 and both actual failed checker
attempts. The physical verifier, benchmark outputs, benchmark runner and source
configuration remain unchanged. Root owns later staging and execution.

The [v2 attempt](../logging03-physical-execution/attempt01-evidence/outer-receipt.json)
exited 2 before reading the checker script because its host-owned 0700 bundle
was inaccessible to default root with all capabilities dropped. The
[v3 attempt](../logging03-physical-execution/attempt02/evidence/outer-receipt.json)
then failed before the checker could run: UID501 could not execute the private
volume interpreter. Both outcomes, including state and cleanup, remain retained.

Root's [actual control03](../logging03-physical-execution/target-permission-control03.json)
used UID0/GID20 with all capabilities dropped and read-only inputs. It launched
the exact reader venv, imported Python3.12.14/NumPy2.5.3/PyArrow21.0.0, wrote a new
probe JSON to a new 501:20 directory with mode0770, exited0 without OOM, and was
removed after state capture. Its resolved interpreter is under `/root/.local/`,
which explains the UID501 traversal limitation. OpenBLAS warnings are retained.
This control read no graph values and does not establish a physical-output pass.
The preceding control01 workdir failure and control02 metadata observations
are also retained.

The new request pins host UID/GID501:20 and container `--user=0:20`. The
supervisor checks Config.User, and the reader checks its actual UID/GID and
mounted permissions. New bundles remain0755 with files0644. A newly created
evidence directory explicitly receives GID20 and mode0770 and must remain owned
by UID501. Host and reader reject a wrong evidence group. Only new paths are
changed; existing evidence is neither chmodded nor reused. No capability is
added and no directory is world-writable.

All hash, boot, runtime/native, input-readonly, network, CPU/memory/swap/PID,
disk, exit/OOM and state-before-removal guards remain. Use explicit
`/usr/local/bin/python3` for host orchestration; the earlier host Python3.9
failure remains separate. Create a new sealed request and fresh staging/output
namespace. Wrong staging permissions fail before Docker.

The [frozen local gate](controls01-receipt.json) passes27 controls: previous
integrity/lifecycle cases, new-directory modes under umask077, no old-path
repair/reuse, wrong container user and wrong evidence group. These are local
filesystem and mocked Docker/identity checks. The later actual v4 run remains
necessary to validate all admission checks and scan the output values.
