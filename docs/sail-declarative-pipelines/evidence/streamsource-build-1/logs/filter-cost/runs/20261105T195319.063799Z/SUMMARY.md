# Exploratory filter cost comparison

Shared-host ratios only. Candidate time divided by baseline time: above one means more elapsed time.
Raw samples include every cell and both execution orders. No production throughput or memory ceiling is established.
Read receipt.json for the actual profile, compiler command, source hashes and host limitations.

| Rows/batch | Markers | Data selected | Input batches | Output rows | Output batches baseline/candidate | Ratio median | Ratio min–max |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | none | 0% | 512 | 0 | 512/512 | 1.0866 | 1.0524–1.1000 |
| 128 | none | 50% | 512 | 32768 | 512/512 | 1.0377 | 1.0212–1.0527 |
| 128 | none | 100% | 512 | 65536 | 512/512 | 1.1074 | 1.0762–1.1308 |
| 128 | alternating | 0% | 512 | 32768 | 512/65536 | 28.5187 | 28.3744–28.9423 |
| 128 | alternating | 50% | 512 | 49152 | 512/65536 | 18.2915 | 14.6624–18.5264 |
| 128 | alternating | 100% | 512 | 65536 | 512/65536 | 44.1234 | 43.7620–45.2735 |
| 8192 | none | 0% | 8 | 0 | 8/8 | 1.0070 | 0.9963–1.0242 |
| 8192 | none | 50% | 8 | 32768 | 8/8 | 1.0000 | 0.9950–1.0066 |
| 8192 | none | 100% | 8 | 65536 | 8/8 | 1.0126 | 0.9832–1.0161 |
| 8192 | alternating | 0% | 8 | 32768 | 8/65536 | 43.5194 | 43.2533–44.3273 |
| 8192 | alternating | 50% | 8 | 49152 | 8/65536 | 27.0531 | 26.5634–27.2235 |
| 8192 | alternating | 100% | 8 | 65536 | 8/65536 | 143.7135 | 135.2326–146.7882 |

The fixture reuses input buffers and drains output immediately. It does not measure source I/O, planning, distributed execution, retained downstream output or allocator peak memory.
Alternating markers are an intentionally adverse batching case. Extra kernel calls preserve event ordering and must not be removed by moving data across markers.
An unoptimized test run is diagnostic only. Even an optimized run on this shared host remains exploratory; dedicated-host measurements are needed for publishable absolute performance claims.
