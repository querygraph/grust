# Observed client Arrow bridge phases

All eight main and three separate tiny outputs passed the closed full physical WCC oracles. The original vertex domain and partitions match the retained references after minimum-original-member normalization. These are separate checks outside every timer; raw labels are not required to be canonical minima. All eight main Parquets were retained on Apo with matching full SHA.

| Dataset | Calls | Read | CSR/graph | Algorithm + Arrow | Write | Pipeline | Parent wait |
|---|---:|---:|---:|---:|---:|---:|---:|
| cit-Patents | 1 | 0.126 | 5.620 | 1.002 | 0.129 | 6.883 | 8.482 |
| cit-Patents | 3 | 0.128 | 5.476 | 2.951 | 0.349 | 8.909 | 10.596 |
| graph500-24 | 1 | 1.052 | 62.230 | 2.906 | 0.286 | 66.498 | 70.460 |
| graph500-24 | 3 | 1.059 | 62.325 | 8.134 | 0.793 | 72.317 | 76.585 |

Seconds shown solely to describe each observed phase boundary on this shared host; these are not dedicated-host benchmark results. Each condition has n=1 and standard deviation is null. CSR includes checkpoint/serialization/staging/projection work, algorithm includes full client transport, and three-call phases cover all three calls. Software pools are not an OS memory cap. This separately named profile is not compared with the prior native-Parquet baseline.
